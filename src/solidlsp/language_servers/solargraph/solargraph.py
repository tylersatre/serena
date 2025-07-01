"""
Provides Ruby specific instantiation of the LanguageServer class using Solargraph.
Contains various configurations and settings specific to Ruby.
"""

import json
import logging
import os
import pathlib
import stat
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class Solargraph(SolidLanguageServer):
    """
    Provides Ruby specific instantiation of the LanguageServer class using Solargraph.
    Contains various configurations and settings specific to Ruby.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a Solargraph instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        solargraph_executable_path = self.setup_runtime_dependencies(logger, config, repository_root_path)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{solargraph_executable_path} stdio", cwd=repository_root_path),
            "ruby",
        )
        self.server_ready = threading.Event()
        self.service_ready_event = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["vendor"]

    def setup_runtime_dependencies(self, logger: LanguageServerLogger, config: LanguageServerConfig, repository_root_path: str) -> str:
        """
        Setup runtime dependencies for Solargraph.
        """
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), encoding="utf-8") as f:
            d = json.load(f)
            del d["_description"]

        dependency = d["runtimeDependencies"][0]

        # Check if Ruby is installed
        try:
            result = subprocess.run(["ruby", "--version"], check=True, capture_output=True, cwd=repository_root_path)
            ruby_version = result.stdout.strip()
            logger.log(f"Ruby version: {ruby_version}", logging.INFO)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error checking for Ruby installation: {e.stderr}") from e
        except FileNotFoundError as e:
            raise RuntimeError("Ruby is not installed. Please install Ruby before continuing.") from e

        # Check if solargraph is installed
        try:
            result = subprocess.run(
                ["gem", "list", "^solargraph$", "-i"], check=False, capture_output=True, text=True, cwd=repository_root_path
            )
            if result.stdout.strip() == "false":
                logger.log("Installing Solargraph...", logging.INFO)
                subprocess.run(dependency["installCommand"].split(), check=True, capture_output=True, cwd=repository_root_path)

            # Get the gem executable path directly
            result = subprocess.run(["gem", "which", "solargraph"], check=True, capture_output=True, text=True, cwd=repository_root_path)
            gem_path = result.stdout.strip()
            bin_dir = os.path.join(os.path.dirname(os.path.dirname(gem_path)), "bin")
            executable_path = os.path.join(bin_dir, "solargraph")

            if not os.path.exists(executable_path):
                raise RuntimeError(f"Solargraph executable not found at {executable_path}")

            # Ensure the executable has the right permissions
            os.chmod(executable_path, os.stat(executable_path).st_mode | stat.S_IEXEC)

            return executable_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to check or install Solargraph. {e.stderr}") from e

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Solargraph Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), encoding="utf-8") as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    def _start_server(self):
        """
        Starts the Solargraph Language Server for Ruby
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params):
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        self.logger.log("Starting solargraph server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        self.logger.log(f"Sending init params: {json.dumps(initialize_params, indent=4)}", logging.INFO)
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received init response: {init_response}", logging.INFO)
        assert init_response["capabilities"]["textDocumentSync"] == 2
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "resolveProvider": True,
            "triggerCharacters": [".", ":", "@"],
        }
        self.server.notify.initialized({})
        self.completions_available.set()

        self.server_ready.set()
        self.server_ready.wait()
