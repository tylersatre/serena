"""
Vue Language Server implementation using @vue/language-server (Volar) with companion TypeScript LS.
Operates in hybrid mode: Vue LS handles .vue files, TypeScript LS handles .ts/.js files.
"""

import logging
import os
import pathlib
import shutil
import threading
from time import sleep
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler.lsp_types import ExecuteCommandParams, InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class VueTypeScriptServer(TypeScriptLanguageServer):
    """TypeScript LS configured with @vue/typescript-plugin for Vue file support.

    This server is used as a companion to the main Vue language server.
    The Vue plugin enables TypeScript to understand .vue files.

    IMPORTANT: This class uses the typescript-language-server that Vue already
    installed in its vue-lsp/ directory. It does NOT install its own dependencies.
    """

    VUE_LANGUAGE_SERVER_VERSION = "3.1.5"

    # Class variable to pass executable path from __init__ to _setup_runtime_dependencies
    _pending_ts_ls_executable: list[str] | None = None

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        """Return TYPESCRIPT since this is a TypeScript language server variant."""
        return Language.TYPESCRIPT

    @classmethod
    @override
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> list[str]:
        """Override to prevent installing dependencies - Vue already installed them.

        This method is called by TypeScriptLanguageServer.__init__, but we don't
        need to install anything because VueLanguageServer._setup_runtime_dependencies
        already installed typescript-language-server in vue-lsp/.

        Uses the class variable _pending_ts_ls_executable which is set by __init__
        before calling super().__init__().
        """
        if cls._pending_ts_ls_executable is not None:
            return cls._pending_ts_ls_executable
        # Fallback - should not happen in normal usage
        return ["typescript-language-server", "--stdio"]

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
        vue_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: list[str],
    ):
        self._vue_plugin_path = vue_plugin_path
        self._custom_tsdk_path = tsdk_path
        # Set class variable before super().__init__ calls _setup_runtime_dependencies
        VueTypeScriptServer._pending_ts_ls_executable = ts_ls_executable_path
        super().__init__(config, logger, repository_root_path, solidlsp_settings)
        # Clear the class variable after initialization
        VueTypeScriptServer._pending_ts_ls_executable = None

    @override
    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """Override to add Vue TypeScript plugin configuration."""
        # Get base params from TypeScript implementation
        params = super()._get_initialize_params(repository_absolute_path)

        # Add Vue-specific initialization options
        params["initializationOptions"] = {
            "plugins": [
                {
                    "name": "@vue/typescript-plugin",
                    "location": self._vue_plugin_path,
                    "languages": ["vue"],
                }
            ],
            "tsserver": {
                "path": self._custom_tsdk_path,
            },
        }

        # Add executeCommand capability for tsserver forwarding
        if "workspace" in params["capabilities"]:
            params["capabilities"]["workspace"]["executeCommand"] = {"dynamicRegistration": True}

        return params

    @override
    def _start_server(self) -> None:
        """Override to add workspace/configuration handler needed by Vue's TS plugin."""

        def workspace_configuration_handler(params: dict) -> list:
            """Handle workspace/configuration requests - return empty configs."""
            items = params.get("items", [])
            return [{} for _ in items]

        # Register workspace/configuration handler before calling parent's _start_server
        # Parent will register its own handlers and start the server
        self.server.on_request("workspace/configuration", workspace_configuration_handler)

        # Call parent implementation which handles all other setup
        super()._start_server()


class VueLanguageServer(SolidLanguageServer):
    """
    Language server for Vue Single File Components using @vue/language-server (Volar) with companion TypeScript LS for hybrid mode operation.
    """

    TS_SERVER_READY_TIMEOUT = 5.0
    VUE_SERVER_READY_TIMEOUT = 3.0
    VUE_INDEXING_WAIT_TIME = 2.0

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a VueLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        vue_lsp_executable_path, self.tsdk_path, self._ts_ls_cmd = self._setup_runtime_dependencies(logger, config, solidlsp_settings)
        self._vue_ls_dir = os.path.join(self.ls_resources_dir(solidlsp_settings), "vue-lsp")
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=vue_lsp_executable_path, cwd=repository_root_path),
            "vue",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self._ts_server: VueTypeScriptServer | None = None
        self._ts_server_started = False
        self._vue_files_indexed = False
        self._indexed_vue_file_uris: list[str] = []

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".nuxt",
            ".output",
        ]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """Return language ID based on file extension for Vue, TS, or JS files."""
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".vue":
            return "vue"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "vue"  # Default to vue for unknown extensions

    def _is_typescript_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

    def _find_all_vue_files(self) -> list[str]:
        from pathlib import Path

        vue_files = []
        repo_path = Path(self.repository_root_path)

        for vue_file in repo_path.rglob("*.vue"):
            try:
                relative_path = str(vue_file.relative_to(repo_path))
                if "node_modules" not in relative_path and not relative_path.startswith("."):
                    vue_files.append(relative_path)
            except Exception as e:
                self.logger.log(f"Error processing Vue file {vue_file}: {e}", logging.DEBUG)

        return vue_files

    def _ensure_vue_files_indexed_on_ts_server(self) -> None:
        """Open all .vue files on TypeScript server for cross-file references.

        Uses proper resource management by leveraging the ref_count mechanism in LSPFileBuffer.
        Files are opened normally, then ref_count is incremented to keep them alive until cleanup.
        """
        if self._vue_files_indexed or self._ts_server is None:
            if self._ts_server is None and not self._vue_files_indexed:
                self.logger.log("TypeScript server not available for Vue file indexing", logging.WARNING)
            return

        self.logger.log("Indexing .vue files on TypeScript server for cross-file references", logging.INFO)
        vue_files = self._find_all_vue_files()
        self.logger.log(f"Found {len(vue_files)} .vue files to index", logging.DEBUG)

        for vue_file in vue_files:
            try:
                # Open file with proper context manager to initialize it in the buffer
                with self._ts_server.open_file(vue_file) as file_buffer:
                    # Increment ref_count to keep the file open after context exits
                    file_buffer.ref_count += 1
                    # Store URI for cleanup
                    self._indexed_vue_file_uris.append(file_buffer.uri)
            except Exception as e:
                self.logger.log(f"Failed to open {vue_file} on TS server: {e}", logging.DEBUG)

        self._vue_files_indexed = True
        self.logger.log("Vue file indexing on TypeScript server complete", logging.INFO)

        sleep(self._get_vue_indexing_wait_time())
        self.logger.log("Wait period after Vue file indexing complete", logging.DEBUG)

    def _get_vue_indexing_wait_time(self) -> float:
        return self.VUE_INDEXING_WAIT_TIME

    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        from solidlsp.ls_utils import PathUtils

        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": False},
        }

        return self.server.send.references(request_params)  # type: ignore[arg-type]

    def _send_ts_references_request(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Request references from the companion TypeScript server.

        Uses includeDeclaration: True to get both definitions and references,
        which differs from the base class _send_references_request.
        """
        from pathlib import Path

        from solidlsp.ls_utils import PathUtils

        if self._ts_server is None:
            return []

        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": True},
        }

        # Open the file on TypeScript server and send the request
        with self._ts_server.open_file(relative_file_path):
            response = self._ts_server.handler.send.references(request_params)  # type: ignore[arg-type]

        # Convert raw LSP response to ls_types.Location format
        result: list[ls_types.Location] = []
        if response is not None:
            for item in response:
                abs_path = PathUtils.uri_to_path(item["uri"])
                if not Path(abs_path).is_relative_to(self.repository_root_path):
                    self.logger.log(f"Found reference outside repository: {abs_path}, skipping", logging.DEBUG)
                    continue

                rel_path = Path(abs_path).relative_to(self.repository_root_path)
                if self.is_ignored_path(str(rel_path)):
                    self.logger.log(f"Ignoring reference in {rel_path}", logging.DEBUG)
                    continue

                new_item: dict = {}
                new_item.update(item)  # type: ignore[arg-type]
                new_item["absolutePath"] = str(abs_path)
                new_item["relativePath"] = str(rel_path)
                result.append(ls_types.Location(**new_item))  # type: ignore

        return result

    def request_file_references(self, relative_file_path: str) -> list:
        """Find where a Vue component file is imported using volar/client/findFileReference."""
        from pathlib import Path

        from solidlsp.ls_types import Location
        from solidlsp.ls_utils import PathUtils

        if not self.server_started:
            self.logger.log(
                "request_file_references called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
        uri = PathUtils.path_to_uri(absolute_file_path)

        request_params = {"textDocument": {"uri": uri}}

        self.logger.log(f"Sending volar/client/findFileReference request for {relative_file_path}", logging.INFO)
        self.logger.log(f"Request URI: {uri}", logging.INFO)
        self.logger.log(f"Request params: {request_params}", logging.INFO)

        try:
            with self.open_file(relative_file_path):
                self.logger.log(f"Sending volar/client/findFileReference for {relative_file_path}", logging.DEBUG)
                self.logger.log(f"Request params: {request_params}", logging.DEBUG)

                response = self.server.send_request("volar/client/findFileReference", request_params)

                self.logger.log(f"Received response type: {type(response)}", logging.DEBUG)

            self.logger.log(f"Received file references response: {response}", logging.INFO)
            self.logger.log(f"Response type: {type(response)}", logging.INFO)

            if response is None:
                self.logger.log(f"No file references found for {relative_file_path}", logging.DEBUG)
                return []

            # Response should be an array of Location objects
            if not isinstance(response, list):
                self.logger.log(f"Unexpected response format from volar/client/findFileReference: {type(response)}", logging.WARNING)
                return []

            ret: list[Location] = []
            for item in response:
                if not isinstance(item, dict) or "uri" not in item:
                    self.logger.log(f"Skipping invalid location item: {item}", logging.DEBUG)
                    continue

                abs_path = PathUtils.uri_to_path(item["uri"])  # type: ignore[arg-type]
                if not Path(abs_path).is_relative_to(self.repository_root_path):
                    self.logger.log(
                        f"Found file reference outside repository: {abs_path}, skipping",
                        logging.WARNING,
                    )
                    continue

                rel_path = Path(abs_path).relative_to(self.repository_root_path)
                if self.is_ignored_path(str(rel_path)):
                    self.logger.log(f"Ignoring file reference in {rel_path}", logging.DEBUG)
                    continue

                new_item: dict = {}
                new_item.update(item)  # type: ignore[arg-type]
                new_item["absolutePath"] = str(abs_path)
                new_item["relativePath"] = str(rel_path)
                ret.append(Location(**new_item))  # type: ignore

            self.logger.log(f"Found {len(ret)} file references for {relative_file_path}", logging.DEBUG)
            return ret

        except Exception as e:
            self.logger.log(
                f"Error requesting file references for {relative_file_path}: {e}",
                logging.WARNING,
            )
            return []

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Request references using TypeScript LS (has @vue/typescript-plugin) or Vue LS as fallback."""
        from time import sleep

        if not self.server_started:
            self.logger.log(
                "request_references called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        if not self._has_waited_for_cross_file_references:
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

        if self._ts_server is not None:
            self._ensure_vue_files_indexed_on_ts_server()
            # VueTypeScriptServer.request_references handles file opening internally
            symbol_refs = self._send_ts_references_request(relative_file_path, line=line, column=column)
        else:
            # Fall back to Vue LS - use parent's request_references which handles file opening
            symbol_refs = super().request_references(relative_file_path, line, column)

        if relative_file_path.endswith(".vue"):
            self.logger.log(f"Attempting to find file-level references for Vue component {relative_file_path}", logging.INFO)
            file_refs = self.request_file_references(relative_file_path)
            self.logger.log(f"file_refs result: {len(file_refs)} references found", logging.INFO)

            seen = set()
            for ref in symbol_refs:
                key = (ref["uri"], ref["range"]["start"]["line"], ref["range"]["start"]["character"])
                seen.add(key)

            for file_ref in file_refs:
                key = (file_ref["uri"], file_ref["range"]["start"]["line"], file_ref["range"]["start"]["character"])
                if key not in seen:
                    symbol_refs.append(file_ref)
                    seen.add(key)

            self.logger.log(
                f"Total references for {relative_file_path}: {len(symbol_refs)} (symbol refs + file refs, deduplicated)",
                logging.INFO,
            )

        return symbol_refs

    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Request definition using TypeScript LS (has @vue/typescript-plugin) for better Vue file support.

        In hybrid mode, the Vue LS doesn't handle definition requests for script content.
        The TypeScript server with @vue/typescript-plugin can resolve imports and definitions
        properly in Vue files.
        """
        if not self.server_started:
            self.logger.log(
                "request_definition called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        # Use TypeScript server for definition if available
        if self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_definition(relative_file_path, line, column)

        # Fall back to Vue LS
        return super().request_definition(relative_file_path, line, column)

    @override
    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str) -> ls_types.WorkspaceEdit | None:
        """Request rename using TypeScript LS (has @vue/typescript-plugin) for better Vue file support.

        In hybrid mode, the Vue LS doesn't handle rename requests for script content.
        The TypeScript server with @vue/typescript-plugin can rename symbols
        properly in Vue files and across the codebase.
        """
        if not self.server_started:
            self.logger.log(
                "request_rename_symbol_edit called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        # Use TypeScript server for rename if available
        if self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_rename_symbol_edit(relative_file_path, line, column, new_name)

        # Fall back to Vue LS
        return super().request_rename_symbol_edit(relative_file_path, line, column, new_name)

    @classmethod
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> tuple[list[str], str, list[str]]:
        """
        Setup runtime dependencies for Vue Language Server and return the command to start the server
        along with the tsdk path and TypeScript LS command.
        """
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="vue-language-server",
                    description="Vue language server package (Volar)",
                    command=["npm", "install", "--prefix", "./", f"@vue/language-server@{VueTypeScriptServer.VUE_LANGUAGE_SERVER_VERSION}"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript",
                    description="TypeScript (required for tsdk)",
                    command=["npm", "install", "--prefix", "./", f"typescript@{TypeScriptLanguageServer.TYPESCRIPT_VERSION}"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript-language-server",
                    description="TypeScript language server (for Vue LS 3.x tsserver forwarding)",
                    command=[
                        "npm",
                        "install",
                        "--prefix",
                        "./",
                        f"typescript-language-server@{TypeScriptLanguageServer.TYPESCRIPT_LANGUAGE_SERVER_VERSION}",
                    ],
                    platform_id="any",
                ),
            ]
        )

        vue_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "vue-lsp")
        vue_executable_path = os.path.join(vue_ls_dir, "node_modules", ".bin", "vue-language-server")
        ts_ls_executable_path = os.path.join(vue_ls_dir, "node_modules", ".bin", "typescript-language-server")

        if os.name == "nt":
            vue_executable_path += ".cmd"
            ts_ls_executable_path += ".cmd"

        tsdk_path = os.path.join(vue_ls_dir, "node_modules", "typescript", "lib")

        if not os.path.exists(vue_executable_path) or not os.path.exists(ts_ls_executable_path):
            logger.log("Vue/TypeScript Language Server executables not found. Installing...", logging.INFO)
            deps.install(logger, vue_ls_dir)
            logger.log("Vue language server dependencies installed successfully", logging.INFO)

        if not os.path.exists(vue_executable_path):
            raise FileNotFoundError(
                f"vue-language-server executable not found at {vue_executable_path}, something went wrong with the installation."
            )

        if not os.path.exists(ts_ls_executable_path):
            raise FileNotFoundError(
                f"typescript-language-server executable not found at {ts_ls_executable_path}, something went wrong with the installation."
            )

        return [vue_executable_path, "--stdio"], tsdk_path, [ts_ls_executable_path, "--stdio"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Vue Language Server.

        NOTE: Instance method (not @staticmethod) because it needs self.tsdk_path set during _setup_runtime_dependencies().
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
            "initializationOptions": {
                "vue": {
                    # hybridMode: true (default in Vue LS 3.x)
                    # Vue LS handles .vue files, sends tsserver/request for cross-file features
                    # We forward these requests to our companion TypeScript LS
                    "hybridMode": True,
                },
                "typescript": {
                    # Provide path to TypeScript library
                    "tsdk": self.tsdk_path,
                },
            },
        }
        return initialize_params  # type: ignore

    def _start_typescript_server(self) -> None:
        """Start the companion TypeScript server configured with Vue plugin.

        Uses the typescript-language-server that was already installed in vue-lsp/
        by VueLanguageServer._setup_runtime_dependencies().
        """
        try:
            vue_ts_plugin_path = os.path.join(self._vue_ls_dir, "node_modules", "@vue", "typescript-plugin")

            # Create config for TypeScript server
            ts_config = LanguageServerConfig(
                code_language=Language.TYPESCRIPT,
                trace_lsp_communication=False,
            )

            self.logger.log("Creating companion VueTypeScriptServer", logging.INFO)
            self._ts_server = VueTypeScriptServer(
                config=ts_config,
                logger=self.logger,
                repository_root_path=self.repository_root_path,
                solidlsp_settings=self._solidlsp_settings,
                vue_plugin_path=vue_ts_plugin_path,
                tsdk_path=self.tsdk_path,
                ts_ls_executable_path=self._ts_ls_cmd,
            )

            self.logger.log("Starting companion TypeScript server", logging.INFO)
            self._ts_server.start()

            # Wait for TypeScript server to become ready
            self.logger.log("Waiting for companion TypeScript server to be ready...", logging.INFO)
            if not self._ts_server.server_ready.wait(timeout=self.TS_SERVER_READY_TIMEOUT):
                self.logger.log(
                    f"Timeout waiting for companion TypeScript server to be ready after {self.TS_SERVER_READY_TIMEOUT} seconds, proceeding anyway",
                    logging.WARNING,
                )
                self._ts_server.server_ready.set()

            self._ts_server_started = True
            self.logger.log("Companion TypeScript server ready", logging.INFO)
        except Exception as e:
            self.logger.log(f"Error starting TypeScript server: {e}", logging.ERROR)
            self._ts_server = None
            self._ts_server_started = False
            raise

    def _forward_tsserver_request(self, method: str, params: dict) -> Any:
        """Forward a tsserver/request to companion TypeScript LS via typescript.tsserverRequest command."""
        if self._ts_server is None:
            self.logger.log("Cannot forward tsserver request - TypeScript server not started", logging.ERROR)
            return None

        try:
            execute_params: ExecuteCommandParams = {
                "command": "typescript.tsserverRequest",
                "arguments": [method, params, {"isAsync": True, "lowPriority": True}],
            }
            # Access the underlying handler to send execute_command
            result = self._ts_server.handler.send.execute_command(execute_params)
            self.logger.log(f"TypeScript server raw response for {method}: {result}", logging.DEBUG)

            if isinstance(result, dict) and "body" in result:
                return result["body"]
            return result
        except Exception as e:
            self.logger.log(f"Error forwarding tsserver request {method}: {e}", logging.ERROR)
            return None

    def _cleanup_indexed_vue_files(self) -> None:
        """Clean up indexed Vue files by decrementing ref_counts and closing if needed.

        Properly releases resources by using the ref_count mechanism. When ref_count
        reaches 0, the file is closed via did_close_text_document notification.
        """
        if not self._indexed_vue_file_uris or self._ts_server is None:
            return

        self.logger.log(f"Cleaning up {len(self._indexed_vue_file_uris)} indexed Vue files", logging.DEBUG)
        for uri in self._indexed_vue_file_uris:
            try:
                # Access the file buffer directly
                if uri in self._ts_server.open_file_buffers:
                    file_buffer = self._ts_server.open_file_buffers[uri]
                    # Decrement ref_count (matching the increment in _ensure_vue_files_indexed_on_ts_server)
                    file_buffer.ref_count -= 1

                    # If ref_count reaches 0, close the file
                    if file_buffer.ref_count == 0:
                        self._ts_server.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                        del self._ts_server.open_file_buffers[uri]
                        self.logger.log(f"Closed indexed Vue file: {uri}", logging.DEBUG)
            except Exception as e:
                self.logger.log(f"Error closing indexed Vue file {uri}: {e}", logging.DEBUG)

        self._indexed_vue_file_uris.clear()

    def _stop_typescript_server(self) -> None:
        if self._ts_server is not None:
            try:
                self.logger.log("Stopping companion TypeScript server", logging.INFO)
                self._ts_server.stop()
            except Exception as e:
                self.logger.log(f"Error stopping TypeScript server: {e}", logging.WARNING)
            finally:
                self._ts_server = None
                self._ts_server_started = False

    @override
    def _start_server(self) -> None:
        self.logger.log("Starting companion TypeScript server for tsserver forwarding", logging.INFO)
        self._start_typescript_server()

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                self.logger.log("Vue language server ready signal detected", logging.INFO)
                self.server_ready.set()
                self.completions_available.set()

        def tsserver_request_notification_handler(params: list) -> None:
            try:
                if params and len(params) > 0 and len(params[0]) >= 2:
                    request_id = params[0][0]
                    method = params[0][1]
                    method_params = params[0][2] if len(params[0]) > 2 else {}
                    self.logger.log(f"Received tsserver/request: id={request_id}, method={method}", logging.DEBUG)

                    if method == "_vue:projectInfo":
                        file_path = method_params.get("file", "")
                        tsconfig_path = self._find_tsconfig_for_file(file_path)
                        if tsconfig_path:
                            result = {"configFileName": tsconfig_path}
                            response = [[request_id, result]]
                            self.server.notify.send_notification("tsserver/response", response)
                            self.logger.log(f"Sent tsserver/response for projectInfo: {tsconfig_path}", logging.DEBUG)
                        else:
                            response = [[request_id, None]]
                            self.server.notify.send_notification("tsserver/response", response)
                            self.logger.log(f"No tsconfig.json found for {file_path}", logging.DEBUG)
                    else:
                        result = self._forward_tsserver_request(method, method_params)
                        response = [[request_id, result]]
                        self.server.notify.send_notification("tsserver/response", response)
                        self.logger.log(f"Forwarded tsserver/response for {method}: {result}", logging.DEBUG)
                else:
                    self.logger.log(f"Unexpected tsserver/request params format: {params}", logging.WARNING)
            except Exception as e:
                self.logger.log(f"Error handling tsserver/request: {e}", logging.ERROR)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("tsserver/request", tsserver_request_notification_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Vue server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received initialize response from Vue server: {init_response}", logging.DEBUG)

        assert init_response["capabilities"]["textDocumentSync"] in [1, 2]

        if "documentSymbolProvider" in init_response["capabilities"]:
            self.logger.log("Vue server supports document symbols", logging.INFO)
        else:
            self.logger.log("Warning: Vue server does not report document symbol support", logging.WARNING)

        self.server.notify.initialized({})

        self.logger.log("Waiting for Vue language server to be ready...", logging.INFO)
        if not self.server_ready.wait(timeout=self.VUE_SERVER_READY_TIMEOUT):
            self.logger.log("Timeout waiting for Vue server ready signal, proceeding anyway", logging.INFO)
            self.server_ready.set()
            self.completions_available.set()
        else:
            self.logger.log("Vue server initialization complete", logging.INFO)

    def _find_tsconfig_for_file(self, file_path: str) -> str | None:
        if not file_path:
            tsconfig_path = os.path.join(self.repository_root_path, "tsconfig.json")
            return tsconfig_path if os.path.exists(tsconfig_path) else None

        current_dir = os.path.dirname(file_path)
        repo_root = os.path.abspath(self.repository_root_path)

        while current_dir and current_dir.startswith(repo_root):
            tsconfig_path = os.path.join(current_dir, "tsconfig.json")
            if os.path.exists(tsconfig_path):
                return tsconfig_path
            parent = os.path.dirname(current_dir)
            if parent == current_dir:
                break
            current_dir = parent

        tsconfig_path = os.path.join(repo_root, "tsconfig.json")
        return tsconfig_path if os.path.exists(tsconfig_path) else None

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5.0

    @override
    def stop(self, shutdown_timeout: float = 5.0) -> None:
        self._cleanup_indexed_vue_files()
        self._stop_typescript_server()
        super().stop(shutdown_timeout)
