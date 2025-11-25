import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.vue
class TestVueLanguageServer:
    """Test Vue Language Server integration with TypeScript LSP."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_files_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Verify all .vue files are recognized by TypeScript LSP."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "App"), "App not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorButton"), "CalculatorButton not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorInput"), "CalculatorInput not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorDisplay"), "CalculatorDisplay not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_script_setup_symbol_extraction(self, language_server: SolidLanguageServer) -> None:
        """Verify symbols extracted from <script setup> sections."""
        app_file = os.path.join("src", "App.vue")
        doc_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        symbol_names = [s.get("name") for s in doc_symbols[0]]

        # Ref declarations
        assert "appTitle" in symbol_names, "appTitle ref not found"
        # Computed properties
        assert "totalCalculations" in symbol_names, "totalCalculations computed not found"
        # Lifecycle hooks
        assert any("onmounted" in str(name).lower() for name in symbol_names), "onMounted callback not found"
        # Watch callbacks
        assert any("watch" in str(name).lower() for name in symbol_names), "watch callback not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_macros_defineprops_defineemits_defineexpose(self, language_server: SolidLanguageServer) -> None:
        """Verify Vue 3 compiler macros work."""
        button_file = os.path.join("src", "components", "CalculatorButton.vue")
        doc_symbols = language_server.request_document_symbols(button_file).get_all_symbols_and_roots()
        symbol_names = [s.get("name") for s in doc_symbols[0]]

        # defineProps interface and usage
        assert "Props" in symbol_names, "Props interface not found"
        assert "props" in symbol_names, "props const not found"
        # defineEmits interface and usage
        assert "Emits" in symbol_names, "Emits interface not found"
        assert "emit" in symbol_names, "emit const not found"
        # defineExpose members
        assert "pressCount" in symbol_names, "pressCount (exposed member) not found"
        assert "handleClick" in symbol_names, "handleClick (exposed as simulateClick) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_template_refs(self, language_server: SolidLanguageServer) -> None:
        """Verify template refs for HTML elements and component instances."""
        # HTML element ref
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        input_names = [s.get("name") for s in input_symbols[0]]
        assert "displayRef" in input_names, "displayRef (HTML element ref) not found"

        # Component instance ref
        assert "equalsButtonRef" in input_names, "equalsButtonRef (component instance ref) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_pinia_store_integration(self, language_server: SolidLanguageServer) -> None:
        """Verify Pinia store definitions and storeToRefs pattern."""
        # Store definition
        store_file = os.path.join("src", "stores", "calculator.ts")
        store_symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()
        store_names = [s.get("name") for s in store_symbols[0]]
        assert "useCalculatorStore" in store_names, "useCalculatorStore export not found"

        # storeToRefs destructuring in CalculatorDisplay.vue
        display_file = os.path.join("src", "components", "CalculatorDisplay.vue")
        display_symbols = language_server.request_document_symbols(display_file).get_all_symbols_and_roots()
        display_names = [s.get("name") for s in display_symbols[0]]
        assert "recentHistory" in display_names, "recentHistory (from storeToRefs) not found"
        assert "currentValue" in display_names, "currentValue (from storeToRefs) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_typescript_support_files(self, language_server: SolidLanguageServer) -> None:
        """Verify TypeScript types, composables, and cross-language integration."""
        # Type definitions
        types_file = os.path.join("src", "types", "index.ts")
        types_symbols = language_server.request_document_symbols(types_file).get_all_symbols_and_roots()
        types_names = [s.get("name") for s in types_symbols[0]]
        assert "Operation" in types_names, "Operation type not found"
        assert "HistoryEntry" in types_names, "HistoryEntry interface not found"

        # Composables
        formatter_file = os.path.join("src", "composables", "useFormatter.ts")
        formatter_symbols = language_server.request_document_symbols(formatter_file).get_all_symbols_and_roots()
        formatter_names = [s.get("name") for s in formatter_symbols[0]]
        assert "useFormatter" in formatter_names, "useFormatter composable not found"

        theme_file = os.path.join("src", "composables", "useTheme.ts")
        theme_symbols = language_server.request_document_symbols(theme_file).get_all_symbols_and_roots()
        theme_names = [s.get("name") for s in theme_symbols[0]]
        assert "useThemeProvider" in theme_names, "useThemeProvider composable not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_path_alias_resolution(self, language_server: SolidLanguageServer) -> None:
        """Verify @ path alias resolves correctly (tsconfig.json)."""
        # If @ alias works, App.vue should successfully parse with @ imports
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        assert len(app_symbols[0]) > 0, "App.vue should have symbols (proves @ imports resolved)"

        # Verify specific @ imports are resolved
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useCalculatorStore"), "Store import via @ alias failed"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Operation"), "Type import via @ alias failed"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useFormatter"), "Composable import via @ alias failed"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_component_imports(self, language_server: SolidLanguageServer) -> None:
        """Verify .vue file imports work with @ alias."""
        # Verify App.vue can parse successfully (contains component imports)
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        assert len(app_symbols[0]) > 0, "App.vue should parse successfully with component imports"

        # Verify imported components exist and have symbols
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorInput"), "CalculatorInput component not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorDisplay"), "CalculatorDisplay component not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorButton"), "CalculatorButton component not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_typescript_edge_cases(self, language_server: SolidLanguageServer) -> None:
        """Verify complex TypeScript patterns in Vue context."""
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        input_names = [s.get("name") for s in input_symbols[0]]

        # Generic type parameters: ref<Operation>(null), ref<string[]>([])
        assert "lastOperation" in input_names, "lastOperation (ref<Operation>) not found"
        assert "operationHistory" in input_names, "operationHistory (ref<string[]>) not found"

        # Union types in props
        button_file = os.path.join("src", "components", "CalculatorButton.vue")
        button_symbols = language_server.request_document_symbols(button_file).get_all_symbols_and_roots()
        button_names = [s.get("name") for s in button_symbols[0]]
        assert "Props" in button_names, "Props interface with union types not found"

        # Provide/inject pattern with InjectionKey
        theme_file = os.path.join("src", "composables", "useTheme.ts")
        theme_symbols = language_server.request_document_symbols(theme_file).get_all_symbols_and_roots()
        theme_names = [s.get("name") for s in theme_symbols[0]]
        assert "ThemeKey" in theme_names, "ThemeKey (InjectionKey) not found"
        assert "ThemeConfig" in theme_names, "ThemeConfig interface not found"

        # Computed returning function
        assert "getOperationClass" in input_names, "getOperationClass (computed returning function) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        """Verify basic cross-file reference functionality."""
        store_file = os.path.join("src", "stores", "calculator.ts")
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find useCalculatorStore function
        store_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "useCalculatorStore":
                store_symbol = sym
                break

        assert store_symbol is not None, "useCalculatorStore function not found"

        # Get references
        sel_start = store_symbol["selectionRange"]["start"]
        refs = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Should have at least one reference (definition itself or usage)
        assert len(refs) > 0, "useCalculatorStore should have references"
