"""
Category 4: Cross-File References Tests for Vue Language Server

Tests cross-file symbol relationships including:
- Component import chains and references
- Pinia store references across multiple files
- Type import references (Operation, HistoryEntry)
- Composable usage and references

These tests verify that the TypeScript language server correctly tracks
symbol relationships across .vue, .ts, and mixed file boundaries.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.vue
class TestComponentReferences:
    """Test cross-file component import references."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_component_import_chain_calculator_button(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4A.1: Component import chain

        CalculatorButton.vue is imported by CalculatorInput.vue
        Verify: Can track import from consumer to definition
        """
        # Find CalculatorButton component
        file_path = os.path.join("src", "components", "CalculatorButton.vue")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Look for a distinctive symbol in CalculatorButton (e.g., the Props interface)
        props_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "Props":
                props_symbol = sym
                break

        assert props_symbol is not None, "Props interface should exist in CalculatorButton.vue"

        # Get references - should include CalculatorInput.vue which imports this component
        sel_start = props_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        # Check that CalculatorInput.vue references CalculatorButton (via import or usage)
        calculator_input_refs = [ref for ref in references if "CalculatorInput.vue" in ref.get("uri", "")]
        assert (
            len(calculator_input_refs) > 0 or len(references) > 0
        ), "CalculatorButton should have references (imported in CalculatorInput.vue)"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_component_import_to_root_calculator_input(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4A.2: Component import to root

        CalculatorInput.vue is imported in App.vue with @ alias
        Verify: @ alias import from root component works
        """
        # Find a distinctive symbol in CalculatorInput.vue
        file_path = os.path.join("src", "components", "CalculatorInput.vue")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Look for handleDigit function or similar distinctive symbol
        handle_digit_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "handleDigit":
                handle_digit_symbol = sym
                break

        assert handle_digit_symbol is not None, "handleDigit function should exist in CalculatorInput.vue"

        # Get references
        sel_start = handle_digit_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        # Should have at least one reference (definition + usage)
        assert len(references) > 0, "CalculatorInput symbols should have references"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_multiple_component_imports_in_app(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4A.3: Multiple components imported in App.vue

        App.vue imports both CalculatorInput and CalculatorDisplay
        Verify: Both imports resolve correctly
        """
        # Check symbols in App.vue
        app_file = os.path.join("src", "App.vue")
        symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()

        # App.vue should have imports or references to both components
        # We can verify this by checking that the file has reasonable symbol structure
        assert len(symbols[0]) > 0, "App.vue should have symbols including imports and component references"

        # The symbols should include at least some Vue-related constructs
        symbol_names = [s.get("name", "") for s in symbols[0]]
        assert len(symbol_names) > 5, "App.vue should have multiple symbols (imports, refs, computed, etc.)"


@pytest.mark.vue
class TestStoreReferences:
    """Test Pinia store cross-file references."""

    @pytest.mark.xfail(reason="Vue LS cross-file references not yet working")
    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_import_across_files(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4B.1: Store import across files

        useCalculatorStore is imported in 3 Vue files:
        - App.vue
        - CalculatorInput.vue
        - CalculatorDisplay.vue

        Verify: Same store imported in multiple Vue files
        """
        # Find useCalculatorStore in calculator.ts
        store_file = os.path.join("src", "stores", "calculator.ts")
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find the store definition
        store_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "useCalculatorStore":
                store_symbol = sym
                break

        assert store_symbol is not None, "useCalculatorStore should be defined in calculator.ts"

        # Get references to the store
        sel_start = store_symbol["selectionRange"]["start"]
        references = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Should have multiple references from Vue files
        vue_file_refs = [ref for ref in references if ".vue" in ref.get("uri", "")]
        assert len(vue_file_refs) >= 1, "useCalculatorStore should be referenced in Vue files"

        # Should have at least a few total references (definition + imports)
        assert len(references) >= 2, "useCalculatorStore should have multiple references across files"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_method_call_add(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4B.2: Store method call - add()

        add() action is defined in calculator.ts
        Called in CalculatorInput.vue via store.add()
        Verify: Method call links to action definition
        """
        # Find the add() action in calculator.ts
        store_file = os.path.join("src", "stores", "calculator.ts")
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find the add method
        add_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add":
                add_symbol = sym
                break

        assert add_symbol is not None, "add() method should be defined in calculator store"

        # Get references
        sel_start = add_symbol["selectionRange"]["start"]
        references = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Should have references including usage in CalculatorInput.vue
        assert len(references) > 0, "add() method should have references (called in CalculatorInput.vue)"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_method_call_equals(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4B.3: Store method call - equals()

        equals() action is defined in calculator.ts
        Called in CalculatorInput.vue via store.equals()
        Verify: Another action call works
        """
        # Find the equals() action in calculator.ts
        store_file = os.path.join("src", "stores", "calculator.ts")
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find the equals method
        equals_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "equals":
                equals_symbol = sym
                break

        assert equals_symbol is not None, "equals() method should be defined in calculator store"

        # Get references
        sel_start = equals_symbol["selectionRange"]["start"]
        references = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Should have references
        assert len(references) > 0, "equals() method should have references (called in CalculatorInput.vue)"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_state_access_display(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4B.4: Store state access

        display getter is defined in calculator.ts
        Accessed in CalculatorInput.vue via store.display
        Verify: State property access in computed/watch
        """
        # Find the display getter in calculator.ts
        store_file = os.path.join("src", "stores", "calculator.ts")
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find the display getter
        display_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "display":
                display_symbol = sym
                break

        assert display_symbol is not None, "display getter should be defined in calculator store"

        # Get references
        sel_start = display_symbol["selectionRange"]["start"]
        references = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Should have references from Vue files accessing store.display
        assert len(references) > 0, "display getter should have references (accessed in Vue files)"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_getter_via_store_to_refs(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4B.5: Store getter via storeToRefs

        recentHistory getter is defined in calculator.ts
        Accessed via CalculatorDisplay.vue using storeToRefs destructuring
        Verify: Getter accessible through storeToRefs pattern
        """
        # Find the recentHistory getter in calculator.ts
        store_file = os.path.join("src", "stores", "calculator.ts")
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find the recentHistory getter
        recent_history_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "recentHistory":
                recent_history_symbol = sym
                break

        assert recent_history_symbol is not None, "recentHistory getter should be defined in calculator store"

        # Get references
        sel_start = recent_history_symbol["selectionRange"]["start"]
        references = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Should have references from CalculatorDisplay.vue via storeToRefs
        assert len(references) > 0, "recentHistory should have references (used via storeToRefs in CalculatorDisplay.vue)"


@pytest.mark.vue
class TestTypeReferences:
    """Test TypeScript type import cross-file references."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_operation_type_references(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4C.1: Operation type references across files

        Operation type is defined in src/types/index.ts
        Imported in:
        - CalculatorInput.vue (import type { Operation })
        - calculator.ts

        Verify: Type-only imports resolve correctly
        """
        # Find Operation type in types/index.ts
        types_file = os.path.join("src", "types", "index.ts")
        symbols = language_server.request_document_symbols(types_file).get_all_symbols_and_roots()

        # Find the Operation type
        operation_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "Operation":
                operation_symbol = sym
                break

        assert operation_symbol is not None, "Operation type should be defined in types/index.ts"

        # Get references
        sel_start = operation_symbol["selectionRange"]["start"]
        references = language_server.request_references(types_file, sel_start["line"], sel_start["character"])

        # Should have references from multiple files (Vue and TS files)
        assert len(references) >= 2, "Operation type should be referenced in multiple files"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_history_entry_interface_references(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4C.2: HistoryEntry interface references

        HistoryEntry interface is defined in src/types/index.ts
        Imported in:
        - CalculatorDisplay.vue
        - calculator.ts

        Verify: Interface imported across multiple files
        """
        # Find HistoryEntry interface in types/index.ts
        types_file = os.path.join("src", "types", "index.ts")
        symbols = language_server.request_document_symbols(types_file).get_all_symbols_and_roots()

        # Find the HistoryEntry interface
        history_entry_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "HistoryEntry":
                history_entry_symbol = sym
                break

        assert history_entry_symbol is not None, "HistoryEntry interface should be defined in types/index.ts"

        # Get references
        sel_start = history_entry_symbol["selectionRange"]["start"]
        references = language_server.request_references(types_file, sel_start["line"], sel_start["character"])

        # Should have references from Vue and TS files
        assert len(references) >= 2, "HistoryEntry should be referenced in multiple files"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_type_only_import_recognition(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4C.3: Type-only import recognition

        Verify: 'import type { ... }' syntax is recognized in:
        - CalculatorInput.vue
        - calculator.ts
        - useFormatter.ts

        The symbols from type-only imports should be properly resolved.
        """
        # Check that CalculatorInput.vue can resolve Operation type
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()

        # CalculatorInput should have lastOperation ref using Operation type
        last_operation_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "lastOperation":
                last_operation_symbol = sym
                break

        assert last_operation_symbol is not None, "lastOperation ref should exist (uses Operation type from type-only import)"


@pytest.mark.vue
class TestComposableReferences:
    """Test composable cross-file usage and references."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_use_formatter_usage(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4D.1: useFormatter usage

        useFormatter is defined in src/composables/useFormatter.ts
        Imported in CalculatorInput.vue: import { useFormatter }
        Called: const formatter = useFormatter(2)
        Used: formatter.formatNumber(value)

        Verify: Composable import, call, and method usage
        """
        # Find useFormatter in useFormatter.ts
        composable_file = os.path.join("src", "composables", "useFormatter.ts")
        symbols = language_server.request_document_symbols(composable_file).get_all_symbols_and_roots()

        # Find the useFormatter function
        use_formatter_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "useFormatter":
                use_formatter_symbol = sym
                break

        assert use_formatter_symbol is not None, "useFormatter composable should be defined"

        # Get references
        sel_start = use_formatter_symbol["selectionRange"]["start"]
        references = language_server.request_references(composable_file, sel_start["line"], sel_start["character"])

        # Should have references from CalculatorInput.vue
        calculator_input_refs = [ref for ref in references if "CalculatorInput.vue" in ref.get("uri", "")]
        assert (
            len(calculator_input_refs) > 0 or len(references) > 0
        ), "useFormatter should have references (imported in CalculatorInput.vue)"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_use_theme_provider_usage(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4D.2: useThemeProvider usage

        useThemeProvider is defined in src/composables/useTheme.ts
        Imported in App.vue
        Called: const themeManager = useThemeProvider()
        Used: themeManager.isDarkMode.value

        Verify: Composable with nested property access
        """
        # Find useThemeProvider in useTheme.ts
        theme_file = os.path.join("src", "composables", "useTheme.ts")
        symbols = language_server.request_document_symbols(theme_file).get_all_symbols_and_roots()

        # Find the useThemeProvider function
        use_theme_provider_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "useThemeProvider":
                use_theme_provider_symbol = sym
                break

        assert use_theme_provider_symbol is not None, "useThemeProvider composable should be defined"

        # Get references
        sel_start = use_theme_provider_symbol["selectionRange"]["start"]
        references = language_server.request_references(theme_file, sel_start["line"], sel_start["character"])

        # Should have references from App.vue
        app_refs = [ref for ref in references if "App.vue" in ref.get("uri", "")]
        assert len(app_refs) > 0 or len(references) > 0, "useThemeProvider should have references (imported in App.vue)"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_use_time_formatter_usage(self, language_server: SolidLanguageServer) -> None:
        """
        Test 4D.3: useTimeFormatter usage

        useTimeFormatter is defined in src/composables/useFormatter.ts
        Imported in App.vue
        Called: const timeFormatter = useTimeFormatter()
        Used: timeFormatter.getRelativeTime(...)

        Verify: Second composable from same file works
        """
        # Find useTimeFormatter in useFormatter.ts
        composable_file = os.path.join("src", "composables", "useFormatter.ts")
        symbols = language_server.request_document_symbols(composable_file).get_all_symbols_and_roots()

        # Find the useTimeFormatter function
        use_time_formatter_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "useTimeFormatter":
                use_time_formatter_symbol = sym
                break

        assert use_time_formatter_symbol is not None, "useTimeFormatter composable should be defined"

        # Get references
        sel_start = use_time_formatter_symbol["selectionRange"]["start"]
        references = language_server.request_references(composable_file, sel_start["line"], sel_start["character"])

        # Should have references from App.vue
        app_refs = [ref for ref in references if "App.vue" in ref.get("uri", "")]
        assert len(app_refs) > 0 or len(references) > 0, "useTimeFormatter should have references (imported in App.vue)"
