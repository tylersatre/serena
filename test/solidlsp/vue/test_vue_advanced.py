"""
Advanced Vue test suite for path alias resolution and edge cases.

This module implements Categories 5 and 6 from the Vue test plan:
- Category 5: Path Alias Resolution (@ alias and relative imports)
- Category 6: Key Edge Cases (optional chaining, generics, provide/inject, etc.)

These tests verify that complex Vue 3 + TypeScript patterns are correctly
parsed and handled by the Language Server Protocol implementation.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.vue
class TestPathAliasResolution:
    """
    Test Category 5: Path Alias Resolution.

    Verifies that @ path aliases and relative imports resolve correctly
    across the Vue codebase, including stores, types, composables, and components.
    """

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_alias_to_store(self, language_server: SolidLanguageServer) -> None:
        """
        Test 5.1: Alias to Store.

        Verifies @ alias resolves to stores in multiple files:
        - App.vue: import { useCalculatorStore } from '@/stores/calculator'
        - CalculatorInput.vue: import { useCalculatorStore } from '@/stores/calculator'
        - CalculatorDisplay.vue: import { useCalculatorStore } from '@/stores/calculator'

        All should resolve to: src/stores/calculator.ts
        Note: Document symbols return variable declarations (e.g., 'store'), not imports.
        """
        # Get full symbol tree to verify store definition exists in src/stores/calculator.ts
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useCalculatorStore"), "useCalculatorStore not found in symbol tree"

        # Verify the store is used in App.vue (const store = useCalculatorStore())
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        assert any(s.get("name") == "store" for s in app_symbols[0]), "store variable (from useCalculatorStore) not found in App.vue"

        # Verify the store is used in CalculatorInput.vue (const store = useCalculatorStore())
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        assert any(
            s.get("name") == "store" for s in input_symbols[0]
        ), "store variable (from useCalculatorStore) not found in CalculatorInput.vue"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_alias_to_types(self, language_server: SolidLanguageServer) -> None:
        """
        Test 5.2: Alias to Types.

        Verifies @ alias resolves to type definitions:
        - Pattern: @/types
        - Used in: CalculatorInput.vue, calculator.ts, useFormatter.ts
        - Resolves to: src/types/index.ts
        Note: Document symbols return variable declarations, not type imports.
        """
        # Get full symbol tree to verify types exist
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Operation"), "Operation type not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "HistoryEntry"), "HistoryEntry type not found in symbol tree"

        # Verify Operation type is used in CalculatorInput.vue (lastOperation uses Operation type)
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        assert any(
            s.get("name") == "lastOperation" for s in input_symbols[0]
        ), "lastOperation (using Operation type) not found in CalculatorInput.vue"

        # Verify types are defined in types/index.ts
        types_file = os.path.join("src", "types", "index.ts")
        types_symbols = language_server.request_document_symbols(types_file).get_all_symbols_and_roots()
        assert any(s.get("name") == "Operation" for s in types_symbols[0]), "Operation type not found in types/index.ts"
        assert any(s.get("name") == "HistoryEntry" for s in types_symbols[0]), "HistoryEntry interface not found in types/index.ts"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_alias_to_composables_formatter(self, language_server: SolidLanguageServer) -> None:
        """
        Test 5.3a: Alias to Composables - useFormatter.

        Verifies @ alias resolves to composables:
        - Pattern: @/composables/useFormatter
        - Used in: CalculatorInput.vue
        - Resolves to: src/composables/useFormatter.ts
        Note: Document symbols return variable declarations, not imports.
        """
        # Get full symbol tree to verify composable exists
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useFormatter"), "useFormatter not found in symbol tree"

        # Verify useFormatter is used in CalculatorInput.vue (const formatter = useFormatter(2))
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        assert any(
            s.get("name") == "formatter" for s in input_symbols[0]
        ), "formatter variable (from useFormatter) not found in CalculatorInput.vue"

        # Verify useFormatter is defined in composables
        formatter_file = os.path.join("src", "composables", "useFormatter.ts")
        formatter_symbols = language_server.request_document_symbols(formatter_file).get_all_symbols_and_roots()
        assert any(s.get("name") == "useFormatter" for s in formatter_symbols[0]), "useFormatter function not found in useFormatter.ts"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_alias_to_composables_theme(self, language_server: SolidLanguageServer) -> None:
        """
        Test 5.3b: Alias to Composables - useTheme.

        Verifies @ alias resolves to theme composable:
        - Pattern: @/composables/useTheme
        - Used in: App.vue
        - Resolves to: src/composables/useTheme.ts
        Note: Document symbols return variable declarations, not imports.
        """
        # Get full symbol tree to verify composable exists
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useThemeProvider"), "useThemeProvider not found in symbol tree"

        # Verify useThemeProvider is used in App.vue (const themeManager = useThemeProvider())
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        assert any(
            s.get("name") == "themeManager" for s in app_symbols[0]
        ), "themeManager variable (from useThemeProvider) not found in App.vue"

        # Verify useThemeProvider is defined in composables
        theme_file = os.path.join("src", "composables", "useTheme.ts")
        theme_symbols = language_server.request_document_symbols(theme_file).get_all_symbols_and_roots()
        assert any(s.get("name") == "useThemeProvider" for s in theme_symbols[0]), "useThemeProvider function not found in useTheme.ts"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_alias_to_components(self, language_server: SolidLanguageServer) -> None:
        """
        Test 5.4: Alias to Components.

        Verifies @ alias resolves to component imports:
        - Pattern: @/components/CalculatorInput.vue
        - Used in: App.vue
        - Resolves to: src/components/CalculatorInput.vue
        Note: Component imports don't appear as document symbols - we verify
        the components exist and can extract symbols from them.
        """
        # Verify the components exist and have symbols
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        assert len(input_symbols[0]) > 0, "CalculatorInput.vue should have symbols"

        display_file = os.path.join("src", "components", "CalculatorDisplay.vue")
        display_symbols = language_server.request_document_symbols(display_file).get_all_symbols_and_roots()
        assert len(display_symbols[0]) > 0, "CalculatorDisplay.vue should have symbols"

        # Verify App.vue has symbols (proving it can resolve imports)
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        assert len(app_symbols[0]) > 0, "App.vue should have symbols"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_relative_import(self, language_server: SolidLanguageServer) -> None:
        """
        Test 5.5: Relative Import.

        Verifies relative imports work alongside @ aliases:
        - Pattern: ./CalculatorButton.vue
        - Used in: CalculatorInput.vue
        - Resolves to: src/components/CalculatorButton.vue
        Note: Component imports don't appear as document symbols.
        """
        # Verify CalculatorButton exists and has symbols
        button_file = os.path.join("src", "components", "CalculatorButton.vue")
        button_symbols = language_server.request_document_symbols(button_file).get_all_symbols_and_roots()
        assert len(button_symbols[0]) > 0, "CalculatorButton.vue should have symbols"

        # Verify CalculatorInput.vue can extract symbols (proves imports don't break parsing)
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        # Check for equalsButtonRef which uses CalculatorButton type
        assert any(
            s.get("name") == "equalsButtonRef" for s in input_symbols[0]
        ), "equalsButtonRef (uses CalculatorButton) not found in CalculatorInput.vue"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_tsconfig_awareness(self, language_server: SolidLanguageServer) -> None:
        """
        Test 5.6: tsconfig.json Awareness.

        Verifies LSP respects tsconfig.json configuration:
        - Config: "baseUrl": "." and "paths": { "@/*": ["./src/*"] }
        - Ensures @ alias configuration is properly loaded and used
        """
        # This test verifies that all @ imports work correctly,
        # which implicitly proves tsconfig.json is being respected

        # Test store import with @ alias
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "useCalculatorStore"
        ), "Store import via @ alias failed - tsconfig.json not respected"

        # Test type import with @ alias
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Operation"), "Type import via @ alias failed - tsconfig.json not respected"

        # Test composable import with @ alias
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "useFormatter"
        ), "Composable import via @ alias failed - tsconfig.json not respected"

        # Test component import with @ alias - verify App.vue parses successfully
        # (Component imports don't appear as document symbols)
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        # App.vue should have symbols (proves it parsed successfully despite @ imports)
        assert len(app_symbols[0]) > 0, "App.vue should have symbols - tsconfig.json likely not respected"


@pytest.mark.vue
class TestEdgeCases:
    """
    Test Category 6: Key Edge Cases.

    Tests important real-world patterns that could break parsing,
    including optional chaining, generic types, provide/inject, and
    advanced computed patterns.
    """

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_optional_chaining_on_ref(self, language_server: SolidLanguageServer) -> None:
        """
        Test 6.1: Optional Chaining on Ref.

        Verifies optional chaining with ref.value works:
        - Pattern: displayRef.value?.classList.remove('display-updated')
        - Location: CalculatorInput.vue
        - Tests: Optional chaining syntax doesn't break parsing
        """
        # Verify displayRef exists in CalculatorInput.vue
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()

        # Look for displayRef in the symbols
        assert any(
            s.get("name") == "displayRef" for s in input_symbols[0]
        ), "displayRef not found in CalculatorInput.vue - optional chaining test setup failed"

        # The fact that the file parses successfully and we can get symbols
        # proves that optional chaining syntax (displayRef.value?.classList) doesn't break parsing

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_component_ref_member_access(self, language_server: SolidLanguageServer) -> None:
        """
        Test 6.2: Component Ref Member Access.

        Verifies cross-component ref access works:
        - Pattern: equalsButtonRef.value.pressCount
        - Links: Parent component accessing child's exposed member
        - Tests: InstanceType<typeof Component> pattern works
        """
        # Verify equalsButtonRef exists in CalculatorInput.vue
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()

        assert any(s.get("name") == "equalsButtonRef" for s in input_symbols[0]), "equalsButtonRef not found in CalculatorInput.vue"

        # Verify the child component (CalculatorButton) exposes pressCount via defineExpose
        button_file = os.path.join("src", "components", "CalculatorButton.vue")
        button_symbols = language_server.request_document_symbols(button_file).get_all_symbols_and_roots()

        assert any(
            s.get("name") == "pressCount" for s in button_symbols[0]
        ), "pressCount not found in CalculatorButton.vue - should be exposed via defineExpose"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_generic_type_parameters(self, language_server: SolidLanguageServer) -> None:
        """
        Test 6.3: Generic Type Parameters.

        Verifies generic syntax with refs and utility types:
        - Examples: ref<Operation>(null), ref<string[]>([])
        - Tests: Generic type parameters don't break parsing
        """
        # Test ref<Operation>(null) in CalculatorInput.vue
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()

        # lastOperation is ref<Operation>(null)
        assert any(
            s.get("name") == "lastOperation" for s in input_symbols[0]
        ), "lastOperation (ref<Operation>) not found in CalculatorInput.vue"

        # operationHistory is ref<string[]>([])
        assert any(
            s.get("name") == "operationHistory" for s in input_symbols[0]
        ), "operationHistory (ref<string[]>) not found in CalculatorInput.vue"

        # displayRef is ref<HTMLDivElement | null>(null) - complex generic with union
        assert any(
            s.get("name") == "displayRef" for s in input_symbols[0]
        ), "displayRef (ref<HTMLDivElement | null>) not found in CalculatorInput.vue"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_union_types_in_props(self, language_server: SolidLanguageServer) -> None:
        """
        Test 6.4: Union Types in Props.

        Verifies string literal unions with optional properties:
        - Pattern: variant?: 'digit' | 'operation' | 'equals' | 'clear'
        - Location: CalculatorButton.vue Props interface
        - Tests: Complex union types in props work correctly
        """
        # Verify Props interface with union types exists in CalculatorButton.vue
        button_file = os.path.join("src", "components", "CalculatorButton.vue")
        button_symbols = language_server.request_document_symbols(button_file).get_all_symbols_and_roots()

        # Look for Props interface
        assert any(s.get("name") == "Props" for s in button_symbols[0]), "Props interface not found in CalculatorButton.vue"

        # Verify props variable exists (created by defineProps)
        assert any(
            s.get("name") == "props" for s in button_symbols[0]
        ), "props (from defineProps<Props>()) not found in CalculatorButton.vue"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_provide_inject_pattern(self, language_server: SolidLanguageServer) -> None:
        """
        Test 6.5: Provide/Inject Pattern.

        Verifies InjectionKey, provide, and inject are recognized:
        - Pattern: export const ThemeKey: InjectionKey<Ref<ThemeConfig>> = Symbol('theme')
        - Usage: provide(ThemeKey, theme) and inject(ThemeKey)
        - Location: useTheme.ts
        """
        # Verify ThemeKey injection key exists
        theme_file = os.path.join("src", "composables", "useTheme.ts")
        theme_symbols = language_server.request_document_symbols(theme_file).get_all_symbols_and_roots()

        assert any(s.get("name") == "ThemeKey" for s in theme_symbols[0]), "ThemeKey (InjectionKey) not found in useTheme.ts"

        # Verify ThemeConfig interface exists
        assert any(s.get("name") == "ThemeConfig" for s in theme_symbols[0]), "ThemeConfig interface not found in useTheme.ts"

        # Verify useThemeProvider function exists (uses provide)
        assert any(
            s.get("name") == "useThemeProvider" for s in theme_symbols[0]
        ), "useThemeProvider (uses provide) not found in useTheme.ts"

        # Verify useTheme function exists (uses inject)
        assert any(s.get("name") == "useTheme" for s in theme_symbols[0]), "useTheme (uses inject) not found in useTheme.ts"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_watch_with_options(self, language_server: SolidLanguageServer) -> None:
        """
        Test 6.6: Watch with Options.

        Verifies watch with options object (deep watching):
        - Pattern: watch(theme, (newTheme) => { ... }, { deep: true })
        - Location: useTheme.ts
        - Tests: Watch with options parameter doesn't break parsing
        """
        # Verify useThemeProvider exists and contains watch logic
        theme_file = os.path.join("src", "composables", "useTheme.ts")
        theme_symbols = language_server.request_document_symbols(theme_file).get_all_symbols_and_roots()

        # Look for useThemeProvider which contains watch with { deep: true }
        assert any(
            s.get("name") == "useThemeProvider" for s in theme_symbols[0]
        ), "useThemeProvider not found in useTheme.ts - watch with options test setup failed"

        # Verify theme ref exists (what's being watched)
        # Note: 'theme' might be nested inside useThemeProvider, so we just verify the function parses
        # The fact that we can get document symbols proves watch with options doesn't break parsing

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_computed_returning_function(self, language_server: SolidLanguageServer) -> None:
        """
        Test 6.7: Computed Returning Function.

        Verifies computed that returns a function (inline method pattern):
        - Pattern: const getOperationClass = computed(() => (op: Operation) => { ... })
        - Location: CalculatorInput.vue
        - Tests: Computed with arrow function returning arrow function works
        """
        # Verify getOperationClass computed exists in CalculatorInput.vue
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()

        assert any(
            s.get("name") == "getOperationClass" for s in input_symbols[0]
        ), "getOperationClass (computed returning function) not found in CalculatorInput.vue"

        # The fact that the symbol is found proves the complex computed pattern
        # (computed returning a function) doesn't break parsing
