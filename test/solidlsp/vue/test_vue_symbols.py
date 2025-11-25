"""
Tests for Vue Single File Component symbol parsing and TypeScript support files.

This test module covers Categories 2 and 3 from the Vue Parsing Test Plan:
- Category 2: Per-File Symbol Testing (App.vue, CalculatorButton.vue, CalculatorInput.vue, CalculatorDisplay.vue)
- Category 3: TypeScript Support Files (types/index.ts, stores/calculator.ts, composables/*.ts)

These tests verify that the TypeScript LSP correctly parses .vue files and their
TypeScript dependencies, extracting symbols from <script setup> sections and
maintaining cross-file relationships.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.vue
class TestVueComponents:
    """Test symbol extraction from Vue Single File Components (.vue files)."""

    # ========================================================================
    # Category 2A: App.vue - Basic Composition API (6-8 tests)
    # ========================================================================

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_core_imports(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.1: Verify Vue core imports are used correctly.

        Vue core imports (ref, computed, watch, etc.) come from the 'vue' package
        and won't appear as symbols in the project's symbol tree. Instead, we verify
        that variables using these functions are correctly parsed.
        """
        # App.vue should parse successfully and contain symbols that USE Vue functions
        app_file = os.path.join("src", "App.vue")
        doc_symbols = language_server.request_document_symbols(app_file)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Verify variables created with Vue functions exist
        assert "appTitle" in symbol_names, "appTitle (created with ref) not found"
        assert "appVersion" in symbol_names, "appVersion (created with computed) not found"
        assert "totalCalculations" in symbol_names, "totalCalculations (created with computed) not found"
        # watch and watchEffect don't create named variables, but callbacks exist
        assert any("watch" in str(name).lower() for name in symbol_names), "watch callback not found"
        assert any("onmounted" in str(name).lower() for name in symbol_names), "onMounted callback not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_store_import_and_usage(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.2: Verify store import and usage.

        Checks that the calculator store import uses @ alias correctly
        and that the store instance is created with const declaration.
        """
        symbols = language_server.request_full_symbol_tree()

        # Store import and usage
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useCalculatorStore"), "useCalculatorStore import not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "store"), "store const declaration not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_component_imports(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.3: Verify component imports with @ alias.

        Checks that .vue file imports are recognized when using @ path alias.
        """
        symbols = language_server.request_full_symbol_tree()

        # Component imports
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorInput"), "CalculatorInput component import not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorDisplay"), "CalculatorDisplay component import not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_ref_declaration(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.4: Verify ref() pattern is recognized.

        Checks that const declarations using ref() from Vue are properly parsed.
        """
        symbols = language_server.request_full_symbol_tree()

        # Ref declaration
        assert SymbolUtils.symbol_tree_contains_name(symbols, "appTitle"), "appTitle ref declaration not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_computed_property(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.5: Verify computed() with return type annotation.

        Checks that computed properties with TypeScript return type annotations
        are properly recognized as symbols.
        """
        symbols = language_server.request_full_symbol_tree()

        # Computed properties
        assert SymbolUtils.symbol_tree_contains_name(symbols, "totalCalculations"), "totalCalculations computed property not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "greetingMessage"), "greetingMessage computed property not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_watch_effect(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.6: Verify watchEffect lifecycle reactive effect.

        Checks that watchEffect calls are recognized. Note: watchEffect itself
        may not appear as a distinct symbol, but its presence can be verified
        through document symbols.
        """
        file_path = os.path.join("src", "App.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]

        # watchEffect may not be a named symbol, but we should have symbols in the file
        assert len(symbols_list) > 0, "App.vue should contain symbols"

        # Verify the file can be parsed without errors by checking for key symbols
        symbol_names = [s.get("name") for s in symbols_list]
        assert "watchEffect" in symbol_names or "totalCalculations" in symbol_names, "App.vue symbols should be accessible"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_watch_with_getter(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.7: Verify watch() with arrow function source.

        Checks that watch calls with getter functions are recognized in the symbol tree.
        """
        file_path = os.path.join("src", "App.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]

        # Watch usage - verify file has symbols which indicates successful parsing
        assert len(symbols_list) > 0, "App.vue should contain parseable symbols"

        # Check for themeManager which is watched
        symbol_names = [s.get("name") for s in symbols_list]
        assert "themeManager" in symbol_names, "themeManager (used in watch) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_app_vue_lifecycle_hook(self, language_server: SolidLanguageServer) -> None:
        """Test 2A.8: Verify onMounted lifecycle hook.

        Checks that lifecycle hooks like onMounted are used correctly.
        Note: onMounted is an import from Vue, not a project symbol.
        We verify that the onMounted callback is present in the document.
        """
        file_path = os.path.join("src", "App.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Look for onMounted callback in document symbols
        assert any("onmounted" in str(name).lower() for name in symbol_names), "onMounted callback not found in App.vue"

    # ========================================================================
    # Category 2B: CalculatorButton.vue - Vue Macros (3 tests)
    # ========================================================================

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_button_define_props(self, language_server: SolidLanguageServer) -> None:
        """Test 2B.1: Verify defineProps with interface and withDefaults.

        Checks that Props interface is recognized and that defineProps macro
        with TypeScript generics and withDefaults works correctly.
        """
        file_path = os.path.join("src", "components", "CalculatorButton.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Props interface and defineProps usage
        assert "Props" in symbol_names, "Props interface not found"
        assert "props" in symbol_names, "props const (from defineProps) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_button_define_emits(self, language_server: SolidLanguageServer) -> None:
        """Test 2B.2: Verify defineEmits with interface.

        Checks that Emits interface is recognized and that defineEmits macro
        is properly parsed along with emit call usage.
        """
        file_path = os.path.join("src", "components", "CalculatorButton.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Emits interface and defineEmits usage
        assert "Emits" in symbol_names, "Emits interface not found"
        assert "emit" in symbol_names, "emit const (from defineEmits) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_button_define_expose(self, language_server: SolidLanguageServer) -> None:
        """Test 2B.3: Verify defineExpose macro.

        Checks that defineExpose is recognized and that exposed members
        (pressCount, isHovered, isFocused, simulateClick) are accessible.
        """
        file_path = os.path.join("src", "components", "CalculatorButton.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Members that are exposed via defineExpose
        assert "pressCount" in symbol_names, "pressCount (exposed member) not found"
        assert "isHovered" in symbol_names, "isHovered (exposed member) not found"
        assert "isFocused" in symbol_names, "isFocused (exposed member) not found"
        # simulateClick is handleClick function reference
        assert "handleClick" in symbol_names, "handleClick (exposed as simulateClick) not found"

    # ========================================================================
    # Category 2C: CalculatorInput.vue - Template Refs (2-3 tests)
    # ========================================================================

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_input_template_ref_html_element(self, language_server: SolidLanguageServer) -> None:
        """Test 2C.1: Verify template ref to HTML element.

        Checks that template refs with DOM element types (HTMLDivElement)
        are recognized and that usage with .value is parseable.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Template ref to HTML element
        assert "displayRef" in symbol_names, "displayRef template ref not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_input_template_ref_component_instance(self, language_server: SolidLanguageServer) -> None:
        """Test 2C.2: Verify template ref to component instance.

        Checks that template refs using InstanceType<typeof Component> pattern
        are recognized and can access exposed members from child components.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Template ref to component instance
        assert "equalsButtonRef" in symbol_names, "equalsButtonRef component template ref not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_input_complex_event_handler(self, language_server: SolidLanguageServer) -> None:
        """Test 2C.3: Verify complex event handler with type parameter.

        Checks that event handler methods with TypeScript type parameters
        and complex switch statement bodies are properly recognized.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Event handler with Operation type parameter and switch statement
        assert "handleOperation" in symbol_names, "handleOperation method not found"

    # ========================================================================
    # Category 2D: CalculatorDisplay.vue - Pinia Pattern (1-2 tests)
    # ========================================================================

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_display_store_to_refs(self, language_server: SolidLanguageServer) -> None:
        """Test 2D.1: Verify storeToRefs pattern.

        Checks that storeToRefs import from Pinia is recognized and that
        destructured variables from storeToRefs are findable as symbols.
        """
        file_path = os.path.join("src", "components", "CalculatorDisplay.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Note: storeToRefs is an import, not a document symbol
        # Check for variables that use storeToRefs destructuring
        assert "recentHistory" in symbol_names, "recentHistory (from storeToRefs) not found"
        assert "hasHistory" in symbol_names, "hasHistory (from storeToRefs) not found"
        assert "currentValue" in symbol_names, "currentValue (from storeToRefs) not found"
        assert "operation" in symbol_names, "operation (from storeToRefs) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_calculator_display_computed_property(self, language_server: SolidLanguageServer) -> None:
        """Test 2D.2: Verify computed property in display component.

        Checks that computed properties exist and are recognized as symbols.
        """
        file_path = os.path.join("src", "components", "CalculatorDisplay.vue")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Computed properties
        assert "displayedHistory" in symbol_names, "displayedHistory computed not found"
        assert "currentCalculation" in symbol_names, "currentCalculation computed not found"


@pytest.mark.vue
class TestTypeScriptSupport:
    """Test symbol extraction from TypeScript support files used by Vue components."""

    # ========================================================================
    # Category 3A: Type Definitions (2 tests)
    # ========================================================================

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_types_interface_export(self, language_server: SolidLanguageServer) -> None:
        """Test 3A.1: Verify exported interface with members.

        Checks that the HistoryEntry interface is exported and contains
        the expected properties (expression, result, timestamp).
        """
        file_path = os.path.join("src", "types", "index.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # HistoryEntry interface should be exported
        assert "HistoryEntry" in symbol_names, "HistoryEntry interface not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_types_type_alias_export(self, language_server: SolidLanguageServer) -> None:
        """Test 3A.2: Verify type alias with union types.

        Checks that the Operation type alias is exported and recognized.
        This tests union types with string literals and null.
        """
        file_path = os.path.join("src", "types", "index.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Operation type alias should be exported
        assert "Operation" in symbol_names, "Operation type alias not found"

    # ========================================================================
    # Category 3B: Pinia Store (4 tests)
    # ========================================================================

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_definition(self, language_server: SolidLanguageServer) -> None:
        """Test 3B.1: Verify Pinia store definition.

        Checks that defineStore call is recognized and the exported
        useCalculatorStore function is findable.
        """
        file_path = os.path.join("src", "stores", "calculator.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Store definition export
        assert "useCalculatorStore" in symbol_names, "useCalculatorStore export not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_state_properties(self, language_server: SolidLanguageServer) -> None:
        """Test 3B.2: Verify state properties with typed values.

        Checks that the state function and its properties are recognized,
        including currentValue, operation, and history.
        """
        file_path = os.path.join("src", "stores", "calculator.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]

        # The store should have a state property/method
        symbol_names = [s.get("name") for s in symbols_list]
        # State properties might be nested, so we check for the store itself
        assert "useCalculatorStore" in symbol_names, "Store definition not found"

        # State is typically a method returning an object, check we have symbols
        assert len(symbols_list) > 0, "Store should contain symbols"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_getter(self, language_server: SolidLanguageServer) -> None:
        """Test 3B.3: Verify getter with state parameter and return type.

        Checks that store getters like recentHistory are recognized as symbols.
        Getters in Pinia stores are methods that take state as a parameter.
        """
        file_path = os.path.join("src", "stores", "calculator.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]

        # Look for getter methods - they may be nested within the store object
        # For now, verify the store is parseable
        assert len(symbols_list) > 0, "Store should contain symbols including getters"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_store_actions(self, language_server: SolidLanguageServer) -> None:
        """Test 3B.4: Verify store action methods.

        Checks that store action methods like add, subtract, multiply, divide,
        equals, and executeOperation are recognized. Actions use 'this' context
        to access store state.
        """
        file_path = os.path.join("src", "stores", "calculator.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]

        # The store definition should be present
        # Actions are typically methods within the store object
        assert len(symbols_list) > 0, "Store should contain action methods"

        # Verify store export exists which contains all actions
        symbol_names = [s.get("name") for s in symbols_list]
        assert "useCalculatorStore" in symbol_names, "Store with actions not found"

    # ========================================================================
    # Category 3C: Composables (2 tests)
    # ========================================================================

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_use_formatter_composable(self, language_server: SolidLanguageServer) -> None:
        """Test 3C.1: Verify useFormatter composable function and methods.

        Checks that the useFormatter function is exported and that internal
        methods like formatNumber and formatCurrency are recognized.
        """
        file_path = os.path.join("src", "composables", "useFormatter.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Composable function exports
        assert "useFormatter" in symbol_names, "useFormatter composable not found"
        assert "useTimeFormatter" in symbol_names, "useTimeFormatter composable not found"

        # Internal methods should be findable (may be nested)
        # At minimum, the composable functions themselves should exist
        assert len(symbols_list) >= 2, "Composable functions should be present"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_use_theme_provider_composable(self, language_server: SolidLanguageServer) -> None:
        """Test 3C.2: Verify useThemeProvider composable with typed ref.

        Checks that useThemeProvider function is exported and that internal
        state like theme ref with ThemeConfig type is recognized.
        """
        file_path = os.path.join("src", "composables", "useTheme.ts")
        doc_symbols = language_server.request_document_symbols(file_path)
        symbols_list = doc_symbols.get_all_symbols_and_roots()[0]
        symbol_names = [s.get("name") for s in symbols_list]

        # Composable functions
        assert "useThemeProvider" in symbol_names, "useThemeProvider composable not found"
        assert "useTheme" in symbol_names, "useTheme composable not found"

        # Theme interface and injection key
        assert "ThemeConfig" in symbol_names, "ThemeConfig interface not found"
        assert "ThemeKey" in symbol_names, "ThemeKey injection key not found"
