"""
Vue Language Server implementation using @vue/language-server (Volar) with companion TypeScript LS.
Operates in hybrid mode: Vue LS handles .vue files, TypeScript LS handles .ts/.js files.
"""

import logging
import os
import pathlib
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import PurePath
from time import sleep
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_handler import SolidLanguageServerHandler
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler.lsp_constants import LSPConstants
from solidlsp.lsp_protocol_handler.lsp_types import ExecuteCommandParams, InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


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
        self._ts_server: SolidLanguageServerHandler | None = None
        self._ts_server_ready = threading.Event()
        self._ts_open_file_buffers: dict[str, LSPFileBuffer] = {}
        self._vue_files_indexed = False
        self._indexed_vue_contexts: list = []

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

    def _get_language_id_for_file(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
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

    @contextmanager
    def _open_file_on_ts_server(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        if self._ts_server is None:
            raise SolidLSPException("TypeScript server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()
        language_id = self._get_language_id_for_file(relative_file_path)

        if uri in self._ts_open_file_buffers:
            self._ts_open_file_buffers[uri].ref_count += 1
            yield self._ts_open_file_buffers[uri]
            self._ts_open_file_buffers[uri].ref_count -= 1
        else:
            contents = FileUtils.read_file(absolute_file_path, self._encoding)
            version = 0
            self._ts_open_file_buffers[uri] = LSPFileBuffer(uri, contents, version, language_id, 1)

            self._ts_server.notify.did_open_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                        LSPConstants.LANGUAGE_ID: language_id,
                        LSPConstants.VERSION: 0,
                        LSPConstants.TEXT: contents,
                    }
                }
            )
            yield self._ts_open_file_buffers[uri]
            self._ts_open_file_buffers[uri].ref_count -= 1

        if self._ts_open_file_buffers[uri].ref_count == 0:
            self._ts_server.notify.did_close_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                    }
                }
            )
            del self._ts_open_file_buffers[uri]

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
        """Open all .vue files on TypeScript server for on-demand indexing."""
        if not self._vue_files_indexed:
            if self._ts_server is None:
                self.logger.log("TypeScript server not available for Vue file indexing", logging.WARNING)
                return

            self.logger.log("Indexing .vue files on TypeScript server for cross-file references", logging.INFO)
            vue_files = self._find_all_vue_files()
            self.logger.log(f"Found {len(vue_files)} .vue files to index", logging.DEBUG)

            for vue_file in vue_files:
                try:
                    ctx = self._open_file_on_ts_server(vue_file)
                    ctx.__enter__()
                    self._indexed_vue_contexts.append(ctx)
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

    def _send_ts_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        if self._ts_server is None:
            return None

        from solidlsp.ls_utils import PathUtils

        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": True},
        }

        return self._ts_server.send.references(request_params)  # type: ignore[arg-type]

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
        from pathlib import Path
        from time import sleep

        from solidlsp.ls_types import Location
        from solidlsp.ls_utils import PathUtils

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

            with self._open_file_on_ts_server(relative_file_path):
                response = self._send_ts_references_request(relative_file_path, line=line, column=column)
        else:
            with self.open_file(relative_file_path):
                response = self._send_references_request(relative_file_path, line=line, column=column)

        symbol_refs: list[Location] = []
        if response is not None:
            for item in response:
                abs_path = PathUtils.uri_to_path(item["uri"])  # type: ignore[arg-type]
                if not Path(abs_path).is_relative_to(self.repository_root_path):
                    self.logger.log(
                        f"Found reference outside repository: {abs_path}, skipping",
                        logging.WARNING,
                    )
                    continue

                rel_path = Path(abs_path).relative_to(self.repository_root_path)
                if self.is_ignored_path(str(rel_path)):
                    self.logger.log(f"Ignoring reference in {rel_path}", logging.DEBUG)
                    continue

                new_item: dict = {}
                new_item.update(item)  # type: ignore[arg-type]
                new_item["absolutePath"] = str(abs_path)
                new_item["relativePath"] = str(rel_path)
                symbol_refs.append(Location(**new_item))  # type: ignore

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

    @contextmanager
    @override
    def open_file(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        if not self.server_started:
            self.logger.log(
                "open_file called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()
        language_id = self._get_language_id_for_file(relative_file_path)

        if uri in self.open_file_buffers:
            assert self.open_file_buffers[uri].uri == uri
            assert self.open_file_buffers[uri].ref_count >= 1

            self.open_file_buffers[uri].ref_count += 1
            yield self.open_file_buffers[uri]
            self.open_file_buffers[uri].ref_count -= 1
        else:
            contents = FileUtils.read_file(absolute_file_path, self._encoding)

            version = 0
            self.open_file_buffers[uri] = LSPFileBuffer(uri, contents, version, language_id, 1)

            self.server.notify.did_open_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                        LSPConstants.LANGUAGE_ID: language_id,
                        LSPConstants.VERSION: 0,
                        LSPConstants.TEXT: contents,
                    }
                }
            )
            yield self.open_file_buffers[uri]
            self.open_file_buffers[uri].ref_count -= 1

        if self.open_file_buffers[uri].ref_count == 0:
            self.server.notify.did_close_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                    }
                }
            )
            del self.open_file_buffers[uri]

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
                    command=["npm", "install", "--prefix", "./", "@vue/language-server@3.1.5"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript",
                    description="TypeScript (required for tsdk)",
                    command=["npm", "install", "--prefix", "./", "typescript@5.5.4"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript-language-server",
                    description="TypeScript language server (for Vue LS 3.x tsserver forwarding)",
                    command=["npm", "install", "--prefix", "./", "typescript-language-server@4.4.0"],
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
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
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

    def _get_ts_initialize_params(self, repository_absolute_path: str) -> dict[str, Any]:
        """Returns the initialize params for the companion TypeScript Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        vue_ts_plugin_path = os.path.join(self._vue_ls_dir, "node_modules", "@vue", "typescript-plugin")

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
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
                "plugins": [
                    {
                        "name": "@vue/typescript-plugin",
                        "location": vue_ts_plugin_path,
                        "languages": ["vue"],
                    }
                ],
                "tsserver": {
                    "path": self.tsdk_path,
                },
            },
        }
        return initialize_params

    def _start_typescript_server(self) -> None:

        def ts_register_capability_handler(params: dict) -> None:
            return

        def ts_configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        def ts_do_nothing(params: dict) -> None:
            return

        def ts_window_log_message(msg: dict) -> None:
            self.logger.log(f"TS-LS: window/logMessage: {msg}", logging.DEBUG)
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                self._ts_server_ready.set()

        self._ts_server = SolidLanguageServerHandler(
            ProcessLaunchInfo(cmd=self._ts_ls_cmd, cwd=self.repository_root_path),
            language=Language.TYPESCRIPT,
            determine_log_level=self._determine_log_level,
            logger=None,  # Use default logging
            start_independent_lsp_process=False,
        )

        self._ts_server.on_request("client/registerCapability", ts_register_capability_handler)
        self._ts_server.on_request("workspace/configuration", ts_configuration_handler)
        self._ts_server.on_notification("window/logMessage", ts_window_log_message)
        self._ts_server.on_notification("$/progress", ts_do_nothing)
        self._ts_server.on_notification("textDocument/publishDiagnostics", ts_do_nothing)

        self.logger.log("Starting companion TypeScript server process", logging.INFO)
        self._ts_server.start()

        ts_init_params = self._get_ts_initialize_params(self.repository_root_path)
        self.logger.log("Sending initialize to companion TypeScript server", logging.INFO)
        # Cast to InitializeParams - the dict structure matches the protocol
        ts_init_response = self._ts_server.send.initialize(ts_init_params)  # type: ignore[arg-type]
        self.logger.log(f"TypeScript server initialized: {ts_init_response}", logging.DEBUG)

        self._ts_server.notify.initialized({})

        if not self._ts_server_ready.wait(timeout=self.TS_SERVER_READY_TIMEOUT):
            self.logger.log("TypeScript server ready signal timeout, proceeding anyway", logging.INFO)
            self._ts_server_ready.set()
        else:
            self.logger.log("TypeScript server ready", logging.INFO)

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
            result = self._ts_server.send.execute_command(execute_params)
            self.logger.log(f"TypeScript server raw response for {method}: {result}", logging.DEBUG)

            if isinstance(result, dict) and "body" in result:
                return result["body"]
            return result
        except Exception as e:
            self.logger.log(f"Error forwarding tsserver request {method}: {e}", logging.ERROR)
            return None

    def _cleanup_indexed_vue_files(self) -> None:
        if not self._indexed_vue_contexts:
            return

        self.logger.log(f"Cleaning up {len(self._indexed_vue_contexts)} indexed Vue file contexts", logging.DEBUG)
        for ctx in self._indexed_vue_contexts:
            try:
                ctx.__exit__(None, None, None)
            except Exception as e:
                self.logger.log(f"Error closing indexed Vue file context: {e}", logging.DEBUG)

        self._indexed_vue_contexts.clear()

    def _stop_typescript_server(self) -> None:
        if self._ts_server is not None:
            try:
                self.logger.log("Stopping companion TypeScript server", logging.INFO)
                self._ts_server.shutdown()
                self._ts_server.stop()
            except Exception as e:
                self.logger.log(f"Error stopping TypeScript server: {e}", logging.WARNING)
            finally:
                self._ts_server = None

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
