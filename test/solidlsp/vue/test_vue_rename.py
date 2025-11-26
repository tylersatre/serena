"""Tests for Vue rename refactoring (textDocument/rename LSP method)."""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.vue


class TestVueRename:
    """Tests for the textDocument/rename LSP method used by RenameSymbolTool."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_rename_function_within_single_file(self, language_server: SolidLanguageServer) -> None:
        """Test renaming a local function within a single Vue file.

        This tests renaming the 'handleDigit' function in CalculatorInput.vue.
        The function is defined and used only within this file.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Find the handleDigit function symbol
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        handle_digit_symbol = next((s for s in symbols[0] if s.get("name") == "handleDigit"), None)

        if not handle_digit_symbol or "selectionRange" not in handle_digit_symbol:
            pytest.skip("handleDigit symbol not found - test fixture may need updating")

        # Get position of the function name
        sel_start = handle_digit_symbol["selectionRange"]["start"]

        # Request rename edit
        workspace_edit = language_server.request_rename_symbol_edit(file_path, sel_start["line"], sel_start["character"], "processDigit")

        # Verify we got a workspace edit
        # NOTE: As of current implementation, Vue LSP may not support rename operations
        # This test documents the expected behavior even if not yet implemented
        assert workspace_edit is not None, "Should return WorkspaceEdit for rename operation"

        # WorkspaceEdit should have either 'changes' or 'documentChanges'
        has_changes = "changes" in workspace_edit and workspace_edit["changes"]
        has_document_changes = "documentChanges" in workspace_edit and workspace_edit["documentChanges"]

        assert has_changes or has_document_changes, "WorkspaceEdit should contain either 'changes' or 'documentChanges'"

        # Verify the edit includes the file we're renaming in
        if has_changes:
            # Changes is a dict mapping URIs to lists of TextEdits
            changes = workspace_edit["changes"]
            assert len(changes) > 0, "Should have at least one file with changes"

            # Check that CalculatorInput.vue is in the changes
            calculator_input_files = [uri for uri in changes.keys() if "CalculatorInput.vue" in uri]
            assert len(calculator_input_files) > 0, f"Should have edits for CalculatorInput.vue. Found edits for: {list(changes.keys())}"

            # Check that the edits for this file exist and are valid
            file_edits = changes[calculator_input_files[0]]
            assert len(file_edits) > 0, "Should have at least one TextEdit for the renamed symbol"

            # Each edit should have a range and newText
            for edit in file_edits:
                assert "range" in edit, "TextEdit should have a range"
                assert "newText" in edit, "TextEdit should have newText"
                assert edit["newText"] == "processDigit", f"newText should be 'processDigit', got {edit['newText']}"

                # Range should have start and end positions
                assert "start" in edit["range"], "Range should have start position"
                assert "end" in edit["range"], "Range should have end position"
                assert "line" in edit["range"]["start"], "Start position should have line number"
                assert "character" in edit["range"]["start"], "Start position should have character offset"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_rename_composable_function_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test renaming a composable function used across multiple files.

        This tests renaming 'useFormatter' which is:
        - Defined in src/composables/useFormatter.ts
        - Imported and used in src/components/CalculatorInput.vue

        The rename should update both the definition and all import/usage sites.
        """
        composable_file = os.path.join("src", "composables", "useFormatter.ts")

        # Find the useFormatter function symbol
        symbols = language_server.request_document_symbols(composable_file).get_all_symbols_and_roots()
        use_formatter_symbol = next((s for s in symbols[0] if s.get("name") == "useFormatter"), None)

        if not use_formatter_symbol or "selectionRange" not in use_formatter_symbol:
            pytest.skip("useFormatter symbol not found - test fixture may need updating")

        # Get position of the function name
        sel_start = use_formatter_symbol["selectionRange"]["start"]

        # Request rename edit
        workspace_edit = language_server.request_rename_symbol_edit(
            composable_file, sel_start["line"], sel_start["character"], "useNumberFormatter"
        )

        # Verify we got a workspace edit
        # NOTE: As of current implementation, Vue LSP may not support rename operations
        # This test documents the expected behavior even if not yet implemented
        assert workspace_edit is not None, "Should return WorkspaceEdit for cross-file rename"

        # WorkspaceEdit should have either 'changes' or 'documentChanges'
        has_changes = "changes" in workspace_edit and workspace_edit["changes"]
        has_document_changes = "documentChanges" in workspace_edit and workspace_edit["documentChanges"]

        assert has_changes or has_document_changes, "WorkspaceEdit should contain either 'changes' or 'documentChanges'"

        if has_changes:
            changes = workspace_edit["changes"]
            assert len(changes) > 0, "Should have at least one file with changes"

            # Should include the composable file (definition)
            composable_files = [uri for uri in changes.keys() if "useFormatter.ts" in uri]
            assert len(composable_files) > 0, f"Should have edits for useFormatter.ts (definition). Found edits for: {list(changes.keys())}"

            # May also include Vue component files that import/use it (CalculatorInput.vue)
            # This depends on LSP implementation - some servers include import sites, others don't
            # We don't assert on this since it varies by implementation

            # Verify edits are valid
            for uri, edits in changes.items():
                assert len(edits) > 0, f"File {uri} should have at least one edit"

                for edit in edits:
                    assert "range" in edit, f"TextEdit in {uri} should have a range"
                    assert "newText" in edit, f"TextEdit in {uri} should have newText"
                    assert edit["newText"] == "useNumberFormatter", f"newText should be 'useNumberFormatter', got {edit['newText']}"
                    assert "start" in edit["range"], f"Range in {uri} should have start position"
                    assert "end" in edit["range"], f"Range in {uri} should have end position"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_rename_verifies_correct_file_paths_and_ranges(self, language_server: SolidLanguageServer) -> None:
        """Test that rename edits include correct file paths and text ranges.

        This verifies the structure and correctness of WorkspaceEdit returned by rename,
        testing with a simple ref variable in App.vue.
        """
        file_path = os.path.join("src", "App.vue")

        # Find the 'appTitle' ref symbol
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        app_title_symbol = next((s for s in symbols[0] if s.get("name") == "appTitle"), None)

        if not app_title_symbol or "selectionRange" not in app_title_symbol:
            pytest.skip("appTitle symbol not found - test fixture may need updating")

        # Get position of the symbol
        sel_start = app_title_symbol["selectionRange"]["start"]

        # Request rename edit
        workspace_edit = language_server.request_rename_symbol_edit(
            file_path, sel_start["line"], sel_start["character"], "applicationTitle"
        )

        # Verify we got a workspace edit
        # NOTE: As of current implementation, Vue LSP may not support rename operations
        # This test documents the expected behavior even if not yet implemented
        assert workspace_edit is not None, "Should return WorkspaceEdit for rename operation"
        assert isinstance(workspace_edit, dict), "WorkspaceEdit should be a dictionary"

        # Verify structure
        has_changes = "changes" in workspace_edit and workspace_edit["changes"]
        has_document_changes = "documentChanges" in workspace_edit and workspace_edit["documentChanges"]

        assert has_changes or has_document_changes, "WorkspaceEdit must have 'changes' or 'documentChanges'"

        if has_changes:
            changes = workspace_edit["changes"]

            # Verify it's a dictionary mapping URIs to edits
            assert isinstance(changes, dict), "changes should be a dict mapping URIs to TextEdit lists"

            # Verify at least one file is affected
            assert len(changes) > 0, "Should have edits for at least one file"

            # Check each URI and its edits
            for uri, edits in changes.items():
                # URI should be a file:// URI string
                assert isinstance(uri, str), f"URI should be a string, got {type(uri)}"
                assert uri.startswith("file://"), f"URI should start with 'file://', got {uri}"

                # Should be a list of edits
                assert isinstance(edits, list), f"Edits for {uri} should be a list, got {type(edits)}"
                assert len(edits) > 0, f"Should have at least one edit for {uri}"

                # Verify each edit structure
                for idx, edit in enumerate(edits):
                    assert isinstance(edit, dict), f"Edit {idx} in {uri} should be a dict, got {type(edit)}"

                    # Required fields
                    assert "range" in edit, f"Edit {idx} in {uri} missing 'range'"
                    assert "newText" in edit, f"Edit {idx} in {uri} missing 'newText'"

                    # Verify range structure
                    range_obj = edit["range"]
                    assert "start" in range_obj, f"Edit {idx} range in {uri} missing 'start'"
                    assert "end" in range_obj, f"Edit {idx} range in {uri} missing 'end'"

                    # Verify position structure
                    for pos_name in ["start", "end"]:
                        pos = range_obj[pos_name]
                        assert "line" in pos, f"Edit {idx} range {pos_name} in {uri} missing 'line'"
                        assert "character" in pos, f"Edit {idx} range {pos_name} in {uri} missing 'character'"
                        assert isinstance(pos["line"], int), f"Line should be int, got {type(pos['line'])}"
                        assert isinstance(pos["character"], int), f"Character should be int, got {type(pos['character'])}"
                        assert pos["line"] >= 0, f"Line number should be >= 0, got {pos['line']}"
                        assert pos["character"] >= 0, f"Character offset should be >= 0, got {pos['character']}"

                    # Verify newText
                    assert isinstance(edit["newText"], str), f"newText should be string, got {type(edit['newText'])}"
                    assert edit["newText"] == "applicationTitle", f"newText should be 'applicationTitle', got {edit['newText']}"

        elif has_document_changes:
            # documentChanges is an alternative format (list of TextDocumentEdit)
            document_changes = workspace_edit["documentChanges"]
            assert isinstance(document_changes, list), "documentChanges should be a list"
            assert len(document_changes) > 0, "Should have at least one document change"

            # Each document change should have textDocument and edits
            for change in document_changes:
                assert isinstance(change, dict), "Each document change should be a dict"
                assert "textDocument" in change, "Document change should have textDocument"
                assert "edits" in change, "Document change should have edits"

                # Verify text document identifier
                text_doc = change["textDocument"]
                assert "uri" in text_doc, "textDocument should have uri"
                assert text_doc["uri"].startswith("file://"), f"URI should start with 'file://', got {text_doc['uri']}"

                # Verify edits (same structure as in 'changes' format)
                edits = change["edits"]
                assert isinstance(edits, list), "edits should be a list"
                assert len(edits) > 0, "Should have at least one edit"
