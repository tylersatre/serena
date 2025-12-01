"""Abstract base class for language servers that coordinate with companion servers.

This module provides the CompanionLanguageServer class, which is designed for
language servers that need to coordinate with one or more companion servers
to provide full LSP functionality. This pattern is common in modern web
frameworks like Vue, Svelte, and Astro, where a primary server handles the
domain-specific file format while companion servers (typically TypeScript)
handle cross-language operations like definitions, references, and rename.
"""

from __future__ import annotations

import logging
import os
from abc import abstractmethod
from fnmatch import fnmatch
from pathlib import Path
from time import sleep

from overrides import override

from solidlsp import ls_types
from solidlsp.embedded_language_config import EmbeddedLanguageConfig
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import PathUtils

log = logging.getLogger(__name__)


class CompanionLanguageServer(SolidLanguageServer):
    """
    Abstract base class for language servers that coordinate with companion server(s)
    for cross-language operations.

    Designed for scenarios where a primary file format (e.g., .vue, .svelte, .astro)
    contains or references code in other languages that require separate
    language server support for full functionality.

    This class manages the lifecycle of companion servers, delegates LSP operations
    to the appropriate companion, and handles cross-file indexing for reference
    support.

    Subclasses must implement:
        - _get_domain_file_extension(): Return primary file extension (e.g., ".vue")
        - _get_embedded_language_configs(): Define companion server configurations
        - _create_companion_server(): Create companion server instances

    Subclasses may override:
        - _get_domain_specific_references(): Add domain-specific reference finding
        - _setup_domain_protocol_handlers(): Register domain-specific LSP handlers
        - _on_companions_ready(): Hook called after companions start
        - _merge_references(): Customize reference merging logic
        - _get_preferred_definition(): Customize definition selection
    """

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        """Initialize the companion language server with tracking structures."""
        super().__init__(*args, **kwargs)

        # Companion server management
        self._companions: dict[str, SolidLanguageServer] = {}
        self._companion_configs: dict[str, EmbeddedLanguageConfig] = {}

        # Domain file indexing state
        self._domain_files_indexed: bool = False
        self._indexed_file_uris: list[str] = []

    # ==========================================================================
    # Abstract methods - MUST be implemented by subclasses
    # ==========================================================================

    @abstractmethod
    def _get_domain_file_extension(self) -> str:
        """
        Return the primary file extension for this language server.

        Examples: ".vue", ".svelte", ".astro"

        Returns:
            File extension including the leading dot.

        """

    @abstractmethod
    def _get_embedded_language_configs(self) -> list[EmbeddedLanguageConfig]:
        """
        Define the embedded languages and how they should be handled.

        Returns a list of configurations, one per companion server needed.
        Most implementations will return a single TypeScript config.

        Returns:
            List of EmbeddedLanguageConfig instances.

        """

    @abstractmethod
    def _create_companion_server(self, config: EmbeddedLanguageConfig) -> SolidLanguageServer:
        """
        Create a companion server for the given embedded language configuration.

        Override to provide language-specific companion server setup.
        For TypeScript companions, this typically involves configuring
        the TypeScript server with a framework-specific plugin.

        The returned server should be configured but NOT started - the base
        class will handle starting it.

        Args:
            config: The embedded language configuration.

        Returns:
            A configured but not-yet-started language server instance.

        """

    # ==========================================================================
    # Extension points - may be overridden by subclasses
    # ==========================================================================

    def _get_domain_specific_references(self, relative_file_path: str) -> list[ls_types.Location]:
        """
        Override to add domain-specific reference finding.

        Called during request_references() to get additional references
        that the companion server may not find.

        For Vue: Uses volar/client/findFileReference command
        For other languages: May return empty list or use different mechanism

        Args:
            relative_file_path: Path to the file relative to repository root.

        Returns:
            List of Location objects for domain-specific references.

        """
        return []

    def _setup_domain_protocol_handlers(self) -> None:
        """
        Override to register domain-specific LSP notification/request handlers.

        Called during server startup after companions are ready but before
        the primary server completes initialization.

        For Vue: Registers tsserver/request notification forwarding
        """

    def _on_companions_ready(self) -> None:
        """
        Hook called after all companion servers are started and ready.

        Override to perform additional setup that depends on companions.
        """

    def _merge_references(
        self,
        companion_refs: list[ls_types.Location],
        domain_refs: list[ls_types.Location],
    ) -> list[ls_types.Location]:
        """
        Merge references from companion server(s) with domain-specific references.

        Default implementation deduplicates by (uri, line, character).
        Override to customize deduplication or ordering logic.

        Args:
            companion_refs: References found by companion server(s).
            domain_refs: References found by domain-specific methods.

        Returns:
            Merged and deduplicated list of references.

        """
        seen: set[tuple[str, int, int]] = set()
        result: list[ls_types.Location] = []

        for ref in companion_refs + domain_refs:
            key = (
                ref["uri"],
                ref["range"]["start"]["line"],
                ref["range"]["start"]["character"],
            )
            if key not in seen:
                result.append(ref)
                seen.add(key)

        return result

    # ==========================================================================
    # Common implementation methods
    # ==========================================================================

    def _find_companion_for_operation(self, operation: str) -> SolidLanguageServer | None:
        """
        Find the best companion server to handle a given operation.

        Args:
            operation: One of "definitions", "references", "rename",
                "completions", "diagnostics"

        Returns:
            The highest-priority companion that handles this operation, or None.

        """
        candidates: list[tuple[int, str]] = []

        for lang_id, config in self._companion_configs.items():
            handles_attr = f"handles_{operation}"
            if getattr(config, handles_attr, False):
                candidates.append((config.priority, lang_id))

        if not candidates:
            return None

        # Sort by priority descending, return highest
        candidates.sort(reverse=True)
        return self._companions.get(candidates[0][1])

    def _find_all_domain_files(self) -> list[str]:
        """
        Find all files with the domain extension in the repository.

        Excludes files in ignored directories (node_modules, etc.).

        Returns:
            List of relative file paths.

        """
        ext = self._get_domain_file_extension()
        domain_files: list[str] = []
        repo_path = Path(self.repository_root_path)

        for file_path in repo_path.rglob(f"*{ext}"):
            try:
                relative_path = str(file_path.relative_to(repo_path))
                # Quick check for common ignored patterns before full check
                if "node_modules" not in relative_path and not relative_path.startswith("."):
                    domain_files.append(relative_path)
            except Exception as e:
                log.debug(f"Error processing file {file_path}: {e}")

        return domain_files

    def _ensure_domain_files_indexed(self) -> None:
        """
        Index domain files on companion servers that need them.

        Opens domain files on each companion server and keeps them open
        (via ref_count) so cross-file references work correctly.
        """
        if self._domain_files_indexed:
            return

        domain_files = self._find_all_domain_files()
        log.info(f"Indexing {len(domain_files)} domain files on companion servers")

        for lang_id, config in self._companion_configs.items():
            companion = self._companions.get(lang_id)
            if companion is None:
                continue

            for domain_file in domain_files:
                # Check if file matches any pattern for this companion
                matches = any(fnmatch(domain_file, pattern) for pattern in config.file_patterns)
                if not matches:
                    continue

                try:
                    with companion.open_file(domain_file) as file_buffer:
                        file_buffer.ref_count += 1  # Keep file open
                        self._indexed_file_uris.append(file_buffer.uri)
                except Exception as e:
                    log.debug(f"Failed to index {domain_file} on {lang_id} server: {e}")

        self._domain_files_indexed = True
        log.info("Domain file indexing complete")

    def _cleanup_indexed_files(self) -> None:
        """
        Clean up files that were indexed on companion servers.

        Decrements ref_count and closes files that are no longer needed.
        """
        if not self._indexed_file_uris:
            return

        log.debug(f"Cleaning up {len(self._indexed_file_uris)} indexed files")

        for uri in self._indexed_file_uris:
            for companion in self._companions.values():
                try:
                    if uri in companion.open_file_buffers:
                        file_buffer = companion.open_file_buffers[uri]
                        file_buffer.ref_count -= 1

                        if file_buffer.ref_count == 0:
                            companion.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                            del companion.open_file_buffers[uri]
                except Exception as e:
                    log.debug(f"Error cleaning up indexed file {uri}: {e}")

        self._indexed_file_uris.clear()

    def _send_companion_references_request(
        self,
        companion: SolidLanguageServer,
        relative_file_path: str,
        line: int,
        column: int,
    ) -> list[ls_types.Location]:
        """
        Send a references request to a companion server.

        Handles opening the file on the companion and filtering results
        to only include files within the repository.

        Args:
            companion: The companion server to query.
            relative_file_path: Path to file relative to repository root.
            line: Zero-based line number.
            column: Zero-based column number.

        Returns:
            List of Location objects within the repository.

        """
        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": True},
        }

        with companion.open_file(relative_file_path):
            response = companion.handler.send.references(request_params)  # type: ignore[arg-type]

        result: list[ls_types.Location] = []
        if response is None:
            return result

        for item in response:
            abs_path = PathUtils.uri_to_path(item["uri"])
            if not Path(abs_path).is_relative_to(self.repository_root_path):
                log.debug(f"Skipping reference outside repository: {abs_path}")
                continue

            rel_path = Path(abs_path).relative_to(self.repository_root_path)
            if self.is_ignored_path(str(rel_path)):
                log.debug(f"Skipping ignored reference: {rel_path}")
                continue

            new_item: dict = dict(item)  # type: ignore[arg-type]
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            result.append(ls_types.Location(**new_item))  # type: ignore[typeddict-item]

        return result

    # ==========================================================================
    # LSP operation overrides - delegation to companions
    # ==========================================================================

    @override
    def request_definition(
        self,
        relative_file_path: str,
        line: int,
        column: int,
    ) -> list[ls_types.Location]:
        """Request definition, delegating to companion if configured."""
        if not self.server_started:
            log.error("request_definition called before Language Server started")
            raise SolidLSPException("Language Server not started")

        companion = self._find_companion_for_operation("definitions")
        if companion:
            with companion.open_file(relative_file_path):
                return companion.request_definition(relative_file_path, line, column)

        return super().request_definition(relative_file_path, line, column)

    @override
    def request_references(
        self,
        relative_file_path: str,
        line: int,
        column: int,
    ) -> list[ls_types.Location]:
        """Request references, combining companion and domain-specific results."""
        if not self.server_started:
            log.error("request_references called before Language Server started")
            raise SolidLSPException("Language Server not started")

        # Wait for cross-file references if needed (inherited behavior)
        if not self._has_waited_for_cross_file_references:
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

        # Ensure domain files are indexed on companions
        self._ensure_domain_files_indexed()

        # Get references from companion
        companion_refs: list[ls_types.Location] = []
        companion = self._find_companion_for_operation("references")
        if companion:
            companion_refs = self._send_companion_references_request(companion, relative_file_path, line, column)

        # Get domain-specific references
        domain_refs = self._get_domain_specific_references(relative_file_path)

        # Merge and return
        return self._merge_references(companion_refs, domain_refs)

    @override
    def request_rename_symbol_edit(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        new_name: str,
    ) -> ls_types.WorkspaceEdit | None:
        """Request rename, delegating to companion if configured."""
        if not self.server_started:
            log.error("request_rename_symbol_edit called before Language Server started")
            raise SolidLSPException("Language Server not started")

        companion = self._find_companion_for_operation("rename")
        if companion:
            with companion.open_file(relative_file_path):
                return companion.request_rename_symbol_edit(relative_file_path, line, column, new_name)

        return super().request_rename_symbol_edit(relative_file_path, line, column, new_name)

    # ==========================================================================
    # Lifecycle management
    # ==========================================================================

    def _start_companions(self) -> None:
        """Create and start all companion servers."""
        for config in self._get_embedded_language_configs():
            log.info(f"Creating companion server for {config.language_id}")
            companion = self._create_companion_server(config)

            log.info(f"Starting companion server for {config.language_id}")
            companion.start()

            self._companions[config.language_id] = companion
            self._companion_configs[config.language_id] = config
            log.info(f"Companion server for {config.language_id} ready")

        # Call hook after companions ready
        self._on_companions_ready()

        # Setup domain-specific protocol handlers
        self._setup_domain_protocol_handlers()

    @override
    def stop(self, shutdown_timeout: float = 5.0) -> None:
        """Stop all servers - cleanup indexed files, stop companions, then primary."""
        # Cleanup indexed files first
        self._cleanup_indexed_files()

        # Stop all companion servers
        for lang_id, companion in self._companions.items():
            try:
                log.info(f"Stopping companion server for {lang_id}")
                companion.stop()
            except Exception as e:
                log.warning(f"Error stopping companion server {lang_id}: {e}")

        self._companions.clear()
        self._companion_configs.clear()
        self._domain_files_indexed = False

        # Stop primary server
        super().stop(shutdown_timeout)
