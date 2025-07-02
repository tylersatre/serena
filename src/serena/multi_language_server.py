import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from pathspec import PathSpec

from serena.text_utils import MatchedConsecutiveLines
from solidlsp.ls import LSPFileBuffer, ReferenceInSymbol
from solidlsp.ls import SolidLanguageServer as SyncLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import Position, UnifiedSymbolInformation

log = logging.getLogger(__name__)


class MultiLanguageServer:
    def __init__(self, servers: dict[Language, SyncLanguageServer]):
        self._servers = servers
        # assume all servers use same repo root
        self.repository_root_path = next(iter(servers.values())).repository_root_path
        log.info("Initialized MultiLanguageServer with %d language servers: %s", 
                 len(servers), ', '.join(lang.value for lang in servers.keys()))

    def start(self) -> None:
        log.info("Starting %d language servers", len(self._servers))
        for lang, server in self._servers.items():
            try:
                log.info("Starting language server for %s", lang.value)
                server.start()
                log.debug("Successfully started %s language server", lang.value)
            except Exception as e:
                log.exception("Failed to start %s language server: %s", lang.value, e)
                raise

    def stop(self) -> None:
        log.info("Stopping all language servers")
        for lang, server in self._servers.items():
            if server.is_running():
                try:
                    log.info("Stopping language server for %s", lang.value)
                    server.stop()
                    log.debug("Successfully stopped %s language server", lang.value)
                except Exception as e:
                    log.exception("Error stopping %s language server: %s", lang.value, e)
            else:
                log.debug("Language server for %s was not running", lang.value)

    def save_cache(self) -> None:
        log.debug("Saving cache for all language servers")
        for lang, server in self._servers.items():
            try:
                server.save_cache()
                log.debug("Saved cache for %s language server", lang.value)
            except Exception as e:
                log.error("Error saving cache for %s language server: %s", lang.value, e)

    def is_running(self) -> bool:
        running_status = all(server.is_running() for server in self._servers.values())
        if not running_status:
            not_running = [lang.value for lang, server in self._servers.items() if not server.is_running()]
            log.warning("Not all language servers are running. Not running: %s", ', '.join(not_running))
        return running_status

    def get_ignore_spec(self) -> PathSpec:
        return next(iter(self._servers.values())).get_ignore_spec()

    def get_server(self, language: Language) -> SyncLanguageServer:
        if language not in self._servers:
            log.error("Requested language server for %s not found. Available: %s", 
                     language.value, ', '.join(lang.value for lang in self._servers.keys()))
            raise KeyError(f"Language server for {language.value} not found")
        log.debug("Retrieved language server for %s", language.value)
        return self._servers[language]

    def _server_for_path(self, relative_path: str) -> SyncLanguageServer:
        filename = os.path.basename(relative_path)
        log.debug("Finding language server for file: %s", relative_path)
        
        for lang, server in self._servers.items():
            if lang.get_source_fn_matcher().is_relevant_filename(filename):
                log.debug("Matched %s to %s language server based on filename pattern", 
                         relative_path, lang.value)
                return server
        
        # Fallback to first available server
        fallback_lang = next(iter(self._servers.keys()))
        log.warning("No specific language server matched for %s, falling back to %s", 
                   relative_path, fallback_lang.value)
        return next(iter(self._servers.values()))

    def _language_for_path(self, relative_path: str) -> Language | None:
        filename = os.path.basename(relative_path)
        for lang, server in self._servers.items():
            if lang.get_source_fn_matcher().is_relevant_filename(filename):
                log.debug("File %s identified as %s language", relative_path, lang.value)
                return lang
        log.debug("No language identified for file %s", relative_path)
        return None

    @contextmanager
    def open_file(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        server = self._server_for_path(relative_file_path)
        lang = self._language_for_path(relative_file_path)
        log.info("Opening file %s with %s language server", 
                relative_file_path, lang.value if lang else 'fallback')
        with server.open_file(relative_file_path) as fb:
            yield fb

    # request methods
    def request_document_symbols(
        self, relative_file_path: str, include_body: bool = False
    ) -> tuple[list[UnifiedSymbolInformation], list[UnifiedSymbolInformation]]:
        server = self._server_for_path(relative_file_path)
        lang = self._language_for_path(relative_file_path)
        log.debug("Requesting document symbols for %s (language: %s, include_body: %s)", 
                 relative_file_path, lang.value if lang else 'unknown', include_body)
        result = server.request_document_symbols(relative_file_path, include_body)
        log.debug("Retrieved %d top-level and %d total symbols from %s", 
                 len(result[0]), len(result[1]), relative_file_path)
        return result

    def request_full_symbol_tree(
        self, within_relative_path: str | None = None, include_body: bool = False, language: Language | None = None
    ) -> list[UnifiedSymbolInformation]:
        log.debug("Requesting full symbol tree (path: %s, language: %s, include_body: %s)",
                 within_relative_path, language.value if language else 'all', include_body)
        
        if language is not None:
            log.info("Filtering symbol tree request to %s language only", language.value)
            server = self.get_server(language)
            result = server.request_full_symbol_tree(within_relative_path, include_body)
            log.debug("Retrieved %d symbols for %s language", len(result), language.value)
            return result
            
        if within_relative_path is not None:
            server = self._server_for_path(within_relative_path)
            lang = self._language_for_path(within_relative_path)
            log.debug("Using %s language server for path %s", 
                     lang.value if lang else 'fallback', within_relative_path)
            result = server.request_full_symbol_tree(within_relative_path, include_body)
            log.debug("Retrieved %d symbols from %s", len(result), within_relative_path)
            return result
            
        # Get symbols from all language servers
        log.info("Retrieving symbols from all %d language servers", len(self._servers))
        results = []
        for lang, server in self._servers.items():
            lang_results = server.request_full_symbol_tree(None, include_body)
            log.debug("Retrieved %d symbols from %s language server", len(lang_results), lang.value)
            results.extend(lang_results)
        log.info("Total symbols retrieved from all languages: %d", len(results))
        return results

    def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
        language: Language | None = None,
    ) -> list[ReferenceInSymbol]:
        server = self._server_for_path(relative_file_path)
        source_lang = self._language_for_path(relative_file_path)
        
        log.debug("Requesting references for symbol at %s:%d:%d (source language: %s, filter language: %s)",
                 relative_file_path, line, column, 
                 source_lang.value if source_lang else 'unknown',
                 language.value if language else 'none')
        
        references = server.request_referencing_symbols(
            relative_file_path=relative_file_path,
            line=line,
            column=column,
            include_imports=include_imports,
            include_self=include_self,
            include_body=include_body,
            include_file_symbols=include_file_symbols,
        )
        
        log.debug("Found %d total references", len(references))
        
        # Filter references by language if specified
        if language is not None:
            log.info("Filtering references to %s language only", language.value)
            filtered_references = []
            for ref in references:
                # Get the relative path of the referencing symbol
                ref_path = ref.symbol.get("location", {}).get("relativePath")
                if ref_path:
                    ref_lang = self._language_for_path(ref_path)
                    if ref_lang == language:
                        filtered_references.append(ref)
                        log.debug("Including reference from %s (%s)", ref_path, language.value)
                    else:
                        log.debug("Excluding reference from %s (language: %s)", 
                                 ref_path, ref_lang.value if ref_lang else 'unknown')
            log.info("Filtered references: %d/%d match %s language", 
                    len(filtered_references), len(references), language.value)
            return filtered_references
        
        return references

    def retrieve_full_file_content(self, relative_file_path: str) -> str:
        server = self._server_for_path(relative_file_path)
        lang = self._language_for_path(relative_file_path)
        log.debug("Retrieving full content of %s using %s language server", 
                 relative_file_path, lang.value if lang else 'fallback')
        return server.retrieve_full_file_content(relative_file_path)

    def insert_text_at_position(self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str) -> Position:
        server = self._server_for_path(relative_file_path)
        lang = self._language_for_path(relative_file_path)
        log.info("Inserting text at %s:%d:%d using %s language server (text length: %d)", 
                relative_file_path, line, column, lang.value if lang else 'fallback', len(text_to_be_inserted))
        return server.insert_text_at_position(relative_file_path, line, column, text_to_be_inserted)

    def delete_text_between_positions(self, relative_file_path: str, start: Position, end: Position) -> str:
        server = self._server_for_path(relative_file_path)
        lang = self._language_for_path(relative_file_path)
        log.info("Deleting text in %s from %d:%d to %d:%d using %s language server", 
                relative_file_path, start['line'], start['character'], end['line'], end['character'],
                lang.value if lang else 'fallback')
        return server.delete_text_between_positions(relative_file_path, start, end)

    def retrieve_content_around_line(
        self, relative_file_path: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0
    ) -> "MatchedConsecutiveLines":
        server = self._server_for_path(relative_file_path)
        lang = self._language_for_path(relative_file_path)
        log.debug("Retrieving content around line %d in %s (before: %d, after: %d) using %s language server",
                 line, relative_file_path, context_lines_before, context_lines_after,
                 lang.value if lang else 'fallback')
        return server.retrieve_content_around_line(relative_file_path, line, context_lines_before, context_lines_after)

    def search_files_for_pattern(
        self,
        pattern: str,
        relative_path: str = "",
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
        language: Language | None = None,
    ) -> list[MatchedConsecutiveLines]:
        log.info("Searching for pattern '%s' (path: %s, language: %s, include_glob: %s, exclude_glob: %s)",
                pattern[:50] + '...' if len(pattern) > 50 else pattern,
                relative_path or 'all', 
                language.value if language else 'all',
                paths_include_glob, paths_exclude_glob)
        
        results: list[MatchedConsecutiveLines] = []
        for lang, server in self._servers.items():
            if language is None or lang == language:
                log.debug("Searching in %s language server", lang.value)
                lang_results = server.search_files_for_pattern(
                    pattern,
                    relative_path,
                    context_lines_before,
                    context_lines_after,
                    paths_include_glob,
                    paths_exclude_glob,
                )
                log.debug("Found %d matches in %s files", len(lang_results), lang.value)
                results.extend(lang_results)
            else:
                log.debug("Skipping %s language server (not matching filter)", lang.value)
        
        log.info("Total pattern matches found: %d", len(results))
        return results

    def request_overview(self, within_relative_path: str, language: Language | None = None) -> dict:
        log.debug("Requesting overview for %s (language filter: %s)", 
                 within_relative_path, language.value if language else 'none')
        
        if os.path.isfile(os.path.join(self.repository_root_path, within_relative_path)):
            # Single file overview
            server = self._server_for_path(within_relative_path)
            file_lang = self._language_for_path(within_relative_path)
            if language is None or file_lang == language:
                log.debug("Getting overview for file %s using %s language server", 
                         within_relative_path, file_lang.value if file_lang else 'fallback')
                return server.request_overview(within_relative_path)
            else:
                log.debug("Skipping file %s (language %s doesn't match filter %s)", 
                         within_relative_path, file_lang.value if file_lang else 'unknown', language.value)
                return {}
        
        # Directory overview
        log.info("Getting overview for directory %s", within_relative_path)
        results = {}
        for lang, server in self._servers.items():
            if language is None or lang == language:
                log.debug("Getting overview from %s language server", lang.value)
                lang_results = server.request_overview(within_relative_path)
                log.debug("Got %d file overviews from %s language server", len(lang_results), lang.value)
                results.update(lang_results)
            else:
                log.debug("Skipping %s language server (not matching filter)", lang.value)
        
        log.info("Total files in overview: %d", len(results))
        return results
