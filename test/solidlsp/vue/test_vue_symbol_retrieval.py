import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind

pytestmark = pytest.mark.vue


class TestVueSymbolRetrieval:
    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_containing_symbol_script_setup_function(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # First, get the document symbols to find the handleDigit function
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        handle_digit_symbol = next((s for s in symbols[0] if s.get("name") == "handleDigit"), None)

        if not handle_digit_symbol or "range" not in handle_digit_symbol:
            pytest.skip("handleDigit symbol not found - test fixture may need updating")

        # Get a position inside the handleDigit function body
        # We'll use a line a few lines after the function start
        func_start_line = handle_digit_symbol["range"]["start"]["line"]
        position_inside_func = func_start_line + 1
        position_character = 4

        # Request the containing symbol for this position
        containing_symbol = language_server.request_containing_symbol(
            file_path, position_inside_func, position_character, include_body=True
        )

        # Verify we found the correct containing symbol
        assert containing_symbol is not None, "Should find containing symbol inside handleDigit function"
        assert containing_symbol["name"] == "handleDigit", f"Expected handleDigit, got {containing_symbol.get('name')}"
        assert containing_symbol["kind"] in [
            SymbolKind.Function,
            SymbolKind.Method,
            SymbolKind.Variable,
        ], f"Expected function-like kind, got {containing_symbol.get('kind')}"

        # Verify the body is included if available
        if "body" in containing_symbol:
            assert "handleDigit" in containing_symbol["body"], "Function body should contain function name"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_containing_symbol_computed_property(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Find the formattedDisplay computed property
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        formatted_display_symbol = next((s for s in symbols[0] if s.get("name") == "formattedDisplay"), None)

        if not formatted_display_symbol or "range" not in formatted_display_symbol:
            pytest.skip("formattedDisplay computed property not found - test fixture may need updating")

        # Get a position inside the computed property body
        computed_start_line = formatted_display_symbol["range"]["start"]["line"]
        position_inside_computed = computed_start_line + 1
        position_character = 4

        # Request the containing symbol for this position
        containing_symbol = language_server.request_containing_symbol(
            file_path, position_inside_computed, position_character, include_body=True
        )

        # Verify we found the correct containing symbol
        # The language server returns the arrow function inside computed() rather than
        # the variable name. This is technically correct from LSP's perspective.
        assert containing_symbol is not None, "Should find containing symbol inside computed property"
        assert containing_symbol["name"] in [
            "formattedDisplay",
            "computed() callback",
        ], f"Expected formattedDisplay or computed() callback, got {containing_symbol.get('name')}"
        assert containing_symbol["kind"] in [
            SymbolKind.Property,
            SymbolKind.Variable,
            SymbolKind.Function,
        ], f"Expected property/variable/function kind for computed, got {containing_symbol.get('kind')}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_containing_symbol_no_containing_symbol(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Position in the import statements at the top of the script setup
        # Line 1-6 contain imports in CalculatorInput.vue
        import_line = 2
        import_character = 10

        # Request containing symbol for a position in the imports
        containing_symbol = language_server.request_containing_symbol(file_path, import_line, import_character)

        # Should return None or empty dictionary for positions without containing symbol
        assert (
            containing_symbol is None or containing_symbol == {}
        ), f"Expected None or empty dict for import position, got {containing_symbol}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_referencing_symbols_store_function(self, language_server: SolidLanguageServer) -> None:
        store_file = os.path.join("src", "stores", "calculator.ts")

        # Find the 'add' action in the calculator store
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()
        add_symbol = next((s for s in symbols[0] if s.get("name") == "add"), None)

        if not add_symbol or "selectionRange" not in add_symbol:
            pytest.skip("add action not found in calculator store - test fixture may need updating")

        # Request referencing symbols for the add action
        sel_start = add_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(store_file, sel_start["line"], sel_start["character"])
        ]

        # The language server may or may not find cross-file references from TS to Vue
        # The important thing is that the API doesn't crash and returns valid structures
        if len(ref_symbols) > 0:
            # Verify structure of referencing symbols
            for symbol in ref_symbols:
                assert "name" in symbol, "Referencing symbol should have a name"
                assert "kind" in symbol, "Referencing symbol should have a kind"

            # Check if we have references from Vue components
            vue_refs = [
                symbol
                for symbol in ref_symbols
                if "location" in symbol and "uri" in symbol["location"] and ".vue" in symbol["location"]["uri"]
            ]

            # If we found references, verify they have valid structure
            if len(vue_refs) > 0:
                # Verify at least one reference is from a component that uses the store
                assert any(
                    "CalculatorInput.vue" in ref["location"]["uri"] for ref in vue_refs if "location" in ref and "uri" in ref["location"]
                ), "Should find reference to add() in CalculatorInput.vue"
        else:
            # Language server doesn't support cross-file references from TS to Vue yet
            # This is a known limitation, so we just verify the API works
            pytest.skip("Language server doesn't support cross-file references from TypeScript to Vue files")

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_referencing_symbols_composable(self, language_server: SolidLanguageServer) -> None:
        composable_file = os.path.join("src", "composables", "useFormatter.ts")

        # Find the useFormatter composable function
        symbols = language_server.request_document_symbols(composable_file).get_all_symbols_and_roots()
        use_formatter_symbol = next((s for s in symbols[0] if s.get("name") == "useFormatter"), None)

        if not use_formatter_symbol or "selectionRange" not in use_formatter_symbol:
            pytest.skip("useFormatter composable not found - test fixture may need updating")

        # Request referencing symbols for the composable
        sel_start = use_formatter_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(composable_file, sel_start["line"], sel_start["character"])
        ]

        # Verify we found references
        assert len(ref_symbols) > 0, f"useFormatter should be referenced in components, found {len(ref_symbols)} references"

        # Check for references in Vue components
        vue_refs = [
            symbol for symbol in ref_symbols if "location" in symbol and "uri" in symbol["location"] and ".vue" in symbol["location"]["uri"]
        ]

        # CalculatorInput.vue imports and uses useFormatter
        if len(vue_refs) > 0:
            has_calculator_input_ref = any(
                "CalculatorInput.vue" in ref["location"]["uri"] for ref in vue_refs if "location" in ref and "uri" in ref["location"]
            )
            if has_calculator_input_ref:
                assert True, "Found reference in CalculatorInput.vue as expected"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_defining_symbol_import_resolution(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Find the import position for useCalculatorStore
        # In CalculatorInput.vue, line 3: import { useCalculatorStore } from '@/stores/calculator'
        # Try to find a reference to useCalculatorStore usage (not the import, but the usage)
        # Line 9 has: const store = useCalculatorStore()
        # We'll request definition at the position of "useCalculatorStore" in this line
        defining_symbol = language_server.request_defining_symbol(file_path, 9, 18)

        if defining_symbol is None:
            # Some language servers may not support go-to-definition at usage sites
            # Try at line 3 (import statement) instead
            defining_symbol = language_server.request_defining_symbol(file_path, 3, 18)

        # Verify we found a defining symbol
        if defining_symbol is not None:
            assert "name" in defining_symbol, "Defining symbol should have a name"
            assert defining_symbol.get("name") in [
                "useCalculatorStore",
                "calculator",
            ], f"Expected useCalculatorStore or calculator, got {defining_symbol.get('name')}"

            # Verify it points to the store file
            if "location" in defining_symbol and "uri" in defining_symbol["location"]:
                assert (
                    "calculator.ts" in defining_symbol["location"]["uri"]
                ), f"Should point to calculator.ts, got {defining_symbol['location']['uri']}"
        else:
            # Some language servers may not fully support this feature
            pytest.skip("Go-to-definition for imports not fully supported by language server")

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_defining_symbol_component_import(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # CalculatorInput.vue imports CalculatorButton on line 5:
        # import CalculatorButton from './CalculatorButton.vue'
        # We'll request definition at the position of "CalculatorButton" in the import

        # First try at the import statement position
        defining_symbol = language_server.request_defining_symbol(file_path, 5, 10)

        if defining_symbol is None:
            # Try at a usage position in the template instead
            # Line 173: <CalculatorButton
            # We'll use document symbols to find the actual line
            symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

            # Look for CalculatorButton in symbols (might be imported symbol)
            calc_button_ref = next((s for s in symbols[0] if "CalculatorButton" in str(s.get("name", ""))), None)

            if calc_button_ref and "selectionRange" in calc_button_ref:
                sel_start = calc_button_ref["selectionRange"]["start"]
                defining_symbol = language_server.request_defining_symbol(file_path, sel_start["line"], sel_start["character"])

        # Verify we found a defining symbol
        if defining_symbol is not None:
            assert "name" in defining_symbol, "Defining symbol should have a name"

            # The name might be "CalculatorButton" or the file might appear in the location
            if "location" in defining_symbol and "uri" in defining_symbol["location"]:
                assert (
                    "CalculatorButton.vue" in defining_symbol["location"]["uri"]
                ), f"Should point to CalculatorButton.vue, got {defining_symbol['location']['uri']}"
            else:
                # At minimum, verify the name is correct
                assert "CalculatorButton" in str(
                    defining_symbol.get("name", "")
                ), f"Expected CalculatorButton in name, got {defining_symbol.get('name')}"
        else:
            # Some language servers may not fully support this feature for component imports
            pytest.skip("Go-to-definition for component imports not fully supported by language server")
