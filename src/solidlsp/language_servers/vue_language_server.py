"""
Vue Language Server implementation using @vue/language-server (Volar) with companion TypeScript LS.
Operates in hybrid mode: Vue LS handles .vue files, TypeScript LS handles .ts/.js files.
"""

import logging
import os
import pathlib
import shutil
import threading
from pathlib import Path
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.companion_ls import CompanionLanguageServer
from solidlsp.embedded_language_config import EmbeddedLanguageConfig
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import Location
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import ExecuteCommandParams, InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from solidlsp.typescript_companion import (
    create_typescript_companion_config,
    prefer_non_node_modules_definition,
)

log = logging.getLogger(__name__)


class VueTypeScriptServer(TypeScriptLanguageServer):
    """TypeScript LS configured with @vue/typescript-plugin for Vue file support."""

    _pending_ts_ls_executable: list[str] | None = None

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        """Return TYPESCRIPT since this is a TypeScript language server variant.

        Note: VueTypeScriptServer is a companion server that uses TypeScript's language server
        with the Vue TypeScript plugin. It reports as TYPESCRIPT to maintain compatibility
        with the TypeScript language server infrastructure.
        """
        return Language.TYPESCRIPT

    @classmethod
    @override
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> list[str]:
        if cls._pending_ts_ls_executable is not None:
            return cls._pending_ts_ls_executable
        return ["typescript-language-server", "--stdio"]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """Return the correct language ID for files.

        Vue files must be opened with language ID "vue" for the @vue/typescript-plugin
        to process them correctly. The plugin is configured with "languages": ["vue"]
        in the initialization options.
        """
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".vue":
            return "vue"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "typescript"

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
        vue_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: list[str],
    ):
        self._vue_plugin_path = vue_plugin_path
        self._custom_tsdk_path = tsdk_path
        VueTypeScriptServer._pending_ts_ls_executable = ts_ls_executable_path
        super().__init__(config, repository_root_path, solidlsp_settings)
        VueTypeScriptServer._pending_ts_ls_executable = None

    @override
    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        params = super()._get_initialize_params(repository_absolute_path)

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

        if "workspace" in params["capabilities"]:
            params["capabilities"]["workspace"]["executeCommand"] = {"dynamicRegistration": True}

        return params

    @override
    def _start_server(self) -> None:
        def workspace_configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        super()._start_server()


class VueLanguageServer(CompanionLanguageServer):
    """
    Language server for Vue Single File Components using @vue/language-server (Volar) with companion TypeScript LS.

    You can pass the following entries in ls_specific_settings["vue"]:
        - vue_language_server_version: Version of @vue/language-server to install (default: "3.1.5")

    Note: TypeScript versions are configured via ls_specific_settings["typescript"]:
        - typescript_version: Version of TypeScript to install (default: "5.9.3")
        - typescript_language_server_version: Version of typescript-language-server to install (default: "5.1.3")
    """

    TS_SERVER_READY_TIMEOUT = 5.0
    VUE_SERVER_READY_TIMEOUT = 3.0
    # Windows requires more time due to slower I/O and process operations.
    VUE_INDEXING_WAIT_TIME = 4.0 if os.name == "nt" else 2.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        vue_lsp_executable_path, self.tsdk_path, self._ts_ls_cmd = self._setup_runtime_dependencies(config, solidlsp_settings)
        self._vue_ls_dir = os.path.join(self.ls_resources_dir(solidlsp_settings), "vue-lsp")
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=vue_lsp_executable_path, cwd=repository_root_path),
            "vue",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        # Note: _ts_server property provides access to _companions["typescript"]
        # These instance variables are now managed by the base class:
        # - _domain_files_indexed (was _vue_files_indexed)
        # - _indexed_file_uris (was _indexed_vue_file_uris)

    # ==========================================================================
    # Property for backward compatibility
    # ==========================================================================

    @property
    def _ts_server(self) -> VueTypeScriptServer | None:
        """Get the TypeScript companion server for backward compatibility."""
        companion = self._companions.get("typescript")
        return companion if isinstance(companion, VueTypeScriptServer) else None

    # ==========================================================================
    # Required abstract method implementations (from CompanionLanguageServer)
    # ==========================================================================

    @override
    def _get_domain_file_extension(self) -> str:
        """Return the primary file extension for Vue files."""
        return ".vue"

    @override
    def _get_embedded_language_configs(self) -> list[EmbeddedLanguageConfig]:
        """Define TypeScript as the embedded language for Vue files."""
        return [
            create_typescript_companion_config(
                file_patterns=["*.vue"],
                handles_definitions=True,
                handles_references=True,
                handles_rename=True,
            )
        ]

    @override
    def _create_companion_server(self, config: EmbeddedLanguageConfig) -> SolidLanguageServer:
        """Create the companion TypeScript server for Vue files."""
        if config.language_id != "typescript":
            raise ValueError(f"VueLanguageServer only supports TypeScript companion, got: {config.language_id}")

        vue_ts_plugin_path = os.path.join(self._vue_ls_dir, "node_modules", "@vue", "typescript-plugin")

        ts_config = LanguageServerConfig(
            code_language=Language.TYPESCRIPT,
            trace_lsp_communication=False,
        )

        log.info("Creating companion VueTypeScriptServer")
        return VueTypeScriptServer(
            config=ts_config,
            repository_root_path=self.repository_root_path,
            solidlsp_settings=self._solidlsp_settings,
            vue_plugin_path=vue_ts_plugin_path,
            tsdk_path=self.tsdk_path,
            ts_ls_executable_path=self._ts_ls_cmd,
        )

    # ==========================================================================
    # Extension point implementations (from CompanionLanguageServer)
    # ==========================================================================

    @override
    def _ensure_domain_files_indexed(self) -> None:
        """Index Vue files on companion servers with additional wait time for TS server processing."""
        from time import sleep

        if self._domain_files_indexed:
            return

        # Call base implementation to do the actual indexing
        super()._ensure_domain_files_indexed()

        # Additional wait time for TypeScript server to process indexed Vue files
        sleep(self.VUE_INDEXING_WAIT_TIME)
        log.debug("Wait period after Vue file indexing complete")

    @override
    def _get_domain_specific_references(self, relative_file_path: str) -> list[ls_types.Location]:
        """Get Vue-specific file references using volar/client/findFileReference."""
        if relative_file_path.endswith(".vue"):
            return self.request_file_references(relative_file_path)
        return []

    @override
    def _setup_domain_protocol_handlers(self) -> None:
        """Register the tsserver/request notification handler for Volar protocol."""

        def tsserver_request_notification_handler(params: list) -> None:
            try:
                if params and len(params) > 0 and len(params[0]) >= 2:
                    request_id = params[0][0]
                    method = params[0][1]
                    method_params = params[0][2] if len(params[0]) > 2 else {}
                    log.debug(f"Received tsserver/request: id={request_id}, method={method}")

                    if method == "_vue:projectInfo":
                        file_path = method_params.get("file", "")
                        tsconfig_path = self._find_tsconfig_for_file(file_path)
                        result = {"configFileName": tsconfig_path} if tsconfig_path else None
                        response = [[request_id, result]]
                        self.server.notify.send_notification("tsserver/response", response)
                        log.debug(f"Sent tsserver/response for projectInfo: {tsconfig_path}")
                    else:
                        result = self._forward_tsserver_request(method, method_params)
                        response = [[request_id, result]]
                        self.server.notify.send_notification("tsserver/response", response)
                        log.debug(f"Forwarded tsserver/response for {method}: {result}")
                else:
                    log.warning(f"Unexpected tsserver/request params format: {params}")
            except Exception as e:
                log.error(f"Error handling tsserver/request: {e}")

        self.server.on_notification("tsserver/request", tsserver_request_notification_handler)

    @override
    def _on_companions_ready(self) -> None:
        """Wait for TypeScript companion server to be fully ready."""
        ts_server = self._ts_server
        if ts_server is not None:
            log.info("Waiting for companion TypeScript server to be ready...")
            if not ts_server.server_ready.wait(timeout=self.TS_SERVER_READY_TIMEOUT):
                log.warning(
                    f"Timeout waiting for companion TypeScript server to be ready after {self.TS_SERVER_READY_TIMEOUT} seconds, proceeding anyway"
                )
                ts_server.server_ready.set()
            log.info("Companion TypeScript server ready")

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        """Prefer definitions not in node_modules."""
        return prefer_non_node_modules_definition(definitions)

    # ==========================================================================
    # Standard method overrides
    # ==========================================================================

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
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".vue":
            return "vue"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "vue"

    # ==========================================================================
    # Vue-specific methods
    # ==========================================================================

    def request_file_references(self, relative_file_path: str) -> list[ls_types.Location]:
        if not self.server_started:
            log.error("request_file_references called before Language Server started")
            raise SolidLSPException("Language Server not started")

        absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
        uri = PathUtils.path_to_uri(absolute_file_path)

        request_params = {"textDocument": {"uri": uri}}

        log.info(f"Sending volar/client/findFileReference request for {relative_file_path}")
        log.info(f"Request URI: {uri}")
        log.info(f"Request params: {request_params}")

        try:
            with self.open_file(relative_file_path):
                log.debug(f"Sending volar/client/findFileReference for {relative_file_path}")
                log.debug(f"Request params: {request_params}")

                response = self.server.send_request("volar/client/findFileReference", request_params)

                log.debug(f"Received response type: {type(response)}")

            log.info(f"Received file references response: {response}")
            log.info(f"Response type: {type(response)}")

            if response is None:
                log.debug(f"No file references found for {relative_file_path}")
                return []

            # Response should be an array of Location objects
            if not isinstance(response, list):
                log.warning(f"Unexpected response format from volar/client/findFileReference: {type(response)}")
                return []

            ret: list[Location] = []
            for item in response:
                if not isinstance(item, dict) or "uri" not in item:
                    log.debug(f"Skipping invalid location item: {item}")
                    continue

                abs_path = PathUtils.uri_to_path(item["uri"])  # type: ignore[arg-type]
                if not Path(abs_path).is_relative_to(self.repository_root_path):
                    log.warning(f"Found file reference outside repository: {abs_path}, skipping")
                    continue

                rel_path = Path(abs_path).relative_to(self.repository_root_path)
                if self.is_ignored_path(str(rel_path)):
                    log.debug(f"Ignoring file reference in {rel_path}")
                    continue

                new_item: dict = {}
                new_item.update(item)  # type: ignore[arg-type]
                new_item["absolutePath"] = str(abs_path)
                new_item["relativePath"] = str(rel_path)
                ret.append(Location(**new_item))  # type: ignore

            log.debug(f"Found {len(ret)} file references for {relative_file_path}")
            return ret

        except SolidLSPException as e:
            log.warning(f"LSP error requesting file references for {relative_file_path}: {e}")
            return []
        except Exception as e:
            log.error(f"Unexpected error requesting file references for {relative_file_path}: {e}")
            raise

    @classmethod
    def _setup_runtime_dependencies(
        cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> tuple[list[str], str, list[str]]:
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # Get TypeScript version settings from TypeScript language server settings
        typescript_config = solidlsp_settings.get_ls_specific_settings(Language.TYPESCRIPT)
        typescript_version = typescript_config.get("typescript_version", "5.9.3")
        typescript_language_server_version = typescript_config.get("typescript_language_server_version", "5.1.3")
        vue_config = solidlsp_settings.get_ls_specific_settings(Language.VUE)
        vue_language_server_version = vue_config.get("vue_language_server_version", "3.1.5")

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="vue-language-server",
                    description="Vue language server package (Volar)",
                    command=["npm", "install", "--prefix", "./", f"@vue/language-server@{vue_language_server_version}"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript",
                    description="TypeScript (required for tsdk)",
                    command=["npm", "install", "--prefix", "./", f"typescript@{typescript_version}"],
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
                        f"typescript-language-server@{typescript_language_server_version}",
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

        # Check if installation is needed based on executables AND version
        version_file = os.path.join(vue_ls_dir, ".installed_version")
        expected_version = f"{vue_language_server_version}_{typescript_version}_{typescript_language_server_version}"

        needs_install = False
        if not os.path.exists(vue_executable_path) or not os.path.exists(ts_ls_executable_path):
            log.info("Vue/TypeScript Language Server executables not found.")
            needs_install = True
        elif os.path.exists(version_file):
            with open(version_file) as f:
                installed_version = f.read().strip()
            if installed_version != expected_version:
                log.info(
                    f"Vue Language Server version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling..."
                )
                needs_install = True
        else:
            # No version file exists, assume old installation needs refresh
            log.info("Vue Language Server version file not found. Reinstalling to ensure correct version...")
            needs_install = True

        if needs_install:
            log.info("Installing Vue/TypeScript Language Server dependencies...")
            deps.install(vue_ls_dir)
            # Write version marker file
            with open(version_file, "w") as f:
                f.write(expected_version)
            log.info("Vue language server dependencies installed successfully")

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
                    "hybridMode": True,
                },
                "typescript": {
                    "tsdk": self.tsdk_path,
                },
            },
        }
        return initialize_params  # type: ignore

    def _forward_tsserver_request(self, method: str, params: dict) -> Any:
        if self._ts_server is None:
            log.error("Cannot forward tsserver request - TypeScript server not started")
            return None

        try:
            execute_params: ExecuteCommandParams = {
                "command": "typescript.tsserverRequest",
                "arguments": [method, params, {"isAsync": True, "lowPriority": True}],
            }
            result = self._ts_server.handler.send.execute_command(execute_params)
            log.debug(f"TypeScript server raw response for {method}: {result}")

            if isinstance(result, dict) and "body" in result:
                return result["body"]
            return result
        except Exception as e:
            log.error(f"Error forwarding tsserver request {method}: {e}")
            return None

    # ==========================================================================
    # Lifecycle overrides
    # ==========================================================================

    @override
    def _start_server(self) -> None:
        # Start companion servers (TypeScript) first
        # This calls _create_companion_server, starts them, and calls _on_companions_ready
        # and _setup_domain_protocol_handlers
        self._start_companions()

        # Set up Vue-specific request handlers (not tsserver/request - that's in _setup_domain_protocol_handlers)
        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        def do_nothing(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("Vue language server ready signal detected")
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Vue server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Vue server: {init_response}")

        assert init_response["capabilities"]["textDocumentSync"] in [1, 2]

        self.server.notify.initialized({})

        log.info("Waiting for Vue language server to be ready...")
        if not self.server_ready.wait(timeout=self.VUE_SERVER_READY_TIMEOUT):
            log.info("Timeout waiting for Vue server ready signal, proceeding anyway")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("Vue server initialization complete")

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
        # Base class handles cleanup of indexed files and stopping companions
        super().stop(shutdown_timeout)
