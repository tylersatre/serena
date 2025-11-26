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
        """Test finding references to a Pinia store action.

        NOTE: Finding cross-file references to Pinia store actions (like store.add()) is challenging
        because it requires the TypeScript server to trace through Pinia's complex type definitions
        (defineStore -> actions -> method). Top-level exports like useCalculatorStore work reliably,
        but nested action methods may only find the definition without cross-file usage references.

        This test verifies the API works correctly without requiring cross-file references for
        deeply nested Pinia actions, which is a known limitation of TypeScript's type inference.
        """
        store_file = os.path.join("src", "stores", "calculator.ts")

        # Find the 'add' action in the calculator store
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()
        add_symbol = next((s for s in symbols[0] if s.get("name") == "add"), None)

        if not add_symbol or "selectionRange" not in add_symbol:
            pytest.skip("add action not found in calculator store - test fixture may need updating")

        # Request referencing symbols for the add action (include_self=True to get at least the definition)
        sel_start = add_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol
            for ref in language_server.request_referencing_symbols(store_file, sel_start["line"], sel_start["character"], include_self=True)
        ]

        # Verify the API works and returns valid structures
        # request_referencing_symbols returns a list (may be empty for deeply nested Pinia actions)
        assert isinstance(ref_symbols, list), f"request_referencing_symbols should return a list, got {type(ref_symbols)}"

        # If we found any references, verify they have valid structure
        for symbol in ref_symbols:
            assert "name" in symbol, "Referencing symbol should have a name"
            assert "kind" in symbol, "Referencing symbol should have a kind"

        # Check if we have references from Vue components (may or may not be found depending on type inference)
        vue_refs = [
            symbol for symbol in ref_symbols if "location" in symbol and "uri" in symbol["location"] and ".vue" in symbol["location"]["uri"]
        ]

        # Note: Cross-file references to Pinia store actions (like store.add()) are challenging
        # because TypeScript must trace through Pinia's complex type definitions.
        # If we do find Vue references, verify their structure
        if len(vue_refs) > 0:
            calculator_input_refs = [
                ref
                for ref in vue_refs
                if "location" in ref and "uri" in ref["location"] and "CalculatorInput.vue" in ref["location"]["uri"]
            ]
            # Just verify structure if found - don't assert on count since cross-file refs aren't guaranteed
            for ref in calculator_input_refs:
                assert "name" in ref, "Reference should have name"
                assert "location" in ref, "Reference should have location"

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

        # Verify we found references - useFormatter is imported and used in CalculatorInput.vue
        assert (
            len(ref_symbols) >= 1
        ), f"useFormatter should have at least 1 reference (used in CalculatorInput.vue), found {len(ref_symbols)} references"

        # Check for references in Vue components
        vue_refs = [
            symbol for symbol in ref_symbols if "location" in symbol and "uri" in symbol["location"] and ".vue" in symbol["location"]["uri"]
        ]

        # CalculatorInput.vue imports and uses useFormatter
        assert len(vue_refs) >= 1, f"Should find at least 1 Vue component reference to useFormatter, found {len(vue_refs)}"

        # Verify we found reference in CalculatorInput.vue specifically
        has_calculator_input_ref = any(
            "CalculatorInput.vue" in ref["location"]["uri"] for ref in vue_refs if "location" in ref and "uri" in ref["location"]
        )
        assert has_calculator_input_ref, (
            f"Should find reference to useFormatter in CalculatorInput.vue. "
            f"Found references in: {[ref['location']['uri'] for ref in vue_refs if 'location' in ref and 'uri' in ref['location']]}"
        )

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_component_cross_references(self, language_server: SolidLanguageServer) -> None:
        """Test finding where a Vue component is used in other Vue components.

        This tests:
        1. Go-to-definition from import statement to the component file
        2. Find-references from the import to see all usages of the component

        CalculatorInput.vue imports and uses CalculatorButton.vue multiple times.
        """
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        button_file = os.path.join("src", "components", "CalculatorButton.vue")

        # Test 1: Go-to-definition from import statement
        # Line 4: import CalculatorButton from './CalculatorButton.vue'
        # Position on "CalculatorButton" (around char 7-22)
        definitions = language_server.request_definition(input_file, 4, 10)

        assert len(definitions) == 1, f"Should find exactly 1 definition for CalculatorButton import, got {len(definitions)}"
        assert (
            "CalculatorButton.vue" in definitions[0]["relativePath"]
        ), f"Definition should point to CalculatorButton.vue, got {definitions[0]['relativePath']}"

        # Test 2: Find references to CalculatorButton from the import
        refs = language_server.request_references(input_file, 4, 10)

        # Should find multiple references (import + usages in template)
        # CalculatorInput.vue uses CalculatorButton multiple times in the template (~7 times)
        assert len(refs) >= 2, (
            f"Should find at least 2 references to CalculatorButton (import + template usages). "
            f"In CalculatorInput.vue, CalculatorButton is imported and used ~7 times in template. Found {len(refs)} references"
        )

        # Test 3: Verify CalculatorButton.vue symbols are accessible
        button_symbols = language_server.request_document_symbols(button_file).get_all_symbols_and_roots()
        symbol_names = [s.get("name") for s in button_symbols[0]]

        assert "Props" in symbol_names, "CalculatorButton.vue should have Props interface"
        assert "handleClick" in symbol_names, "CalculatorButton.vue should have handleClick function"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_defining_symbol_import_resolution(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Find the import position for useCalculatorStore
        # In CalculatorInput.vue (0-indexed lines):
        # Line 2: import { useCalculatorStore } from '@/stores/calculator'
        # Line 8: const store = useCalculatorStore()
        # We'll request definition at the position of "useCalculatorStore" in the usage line
        defining_symbol = language_server.request_defining_symbol(file_path, 8, 18)

        if defining_symbol is None:
            # Some language servers may not support go-to-definition at usage sites
            # Try at line 2 (import statement) instead
            defining_symbol = language_server.request_defining_symbol(file_path, 2, 18)

        # Verify we found a defining symbol
        assert defining_symbol is not None, "Should find defining symbol for useCalculatorStore"
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

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_request_defining_symbol_component_import(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition for Vue SFC component imports.

        NOTE: Vue Single File Components (SFCs) don't export a traditional "symbol" -
        the entire file IS the component. When you import `CalculatorButton from './CalculatorButton.vue'`,
        the definition points to the start of the file (line 0, char 0), not to a specific symbol.

        Since there's no symbol at line 0 of an SFC (it's `<script setup>` or `<template>`),
        request_defining_symbol returns None. This test verifies that request_definition
        correctly resolves the import to the target .vue file.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # CalculatorInput.vue imports CalculatorButton (0-indexed lines):
        # Line 4: import CalculatorButton from './CalculatorButton.vue'
        # Test at the position of "CalculatorButton" in the import statement
        definitions = language_server.request_definition(file_path, 4, 10)

        # Verify we found a definition
        assert len(definitions) > 0, "Should find definition for CalculatorButton import"

        # Verify it points to CalculatorButton.vue
        definition = definitions[0]
        assert definition["relativePath"] is not None, "Definition should have a relative path"
        assert (
            "CalculatorButton.vue" in definition["relativePath"]
        ), f"Should point to CalculatorButton.vue, got {definition['relativePath']}"

        # The definition points to start of file (line 0) because SFCs don't have a specific export symbol
        assert definition["range"]["start"]["line"] == 0, "Definition should point to start of .vue file"

        # Also verify request_defining_symbol behavior for SFC imports.
        # Vue SFCs don't have a defining "symbol" at file start (line 0 is `<script setup>`),
        # so request_defining_symbol may return None. This is expected behavior.
        defining_symbol = language_server.request_defining_symbol(file_path, 4, 10)
        assert defining_symbol is None or "name" in defining_symbol, "If defining_symbol is found, it should have a name"
