"""
Basic infrastructure tests for Vue Single File Component (.vue) parsing.

These tests verify that .vue files are properly recognized by the TypeScript LSP
and that symbols can be extracted from the <script setup> sections.

Category 1: Basic Infrastructure (4 tests)
- Test that .vue files appear in the symbol tree
- Test that document symbols can be extracted from .vue files
- Test that multi-section structure (<template>, <script>, <style>) doesn't break parsing
- Test that components in subdirectories are found alongside root components
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.vue
class TestVueInfrastructure:
    """Basic infrastructure tests for Vue file parsing.

    These tests verify that the TypeScript LSP can properly handle Vue Single File
    Components and extract symbols from their <script setup> sections.
    """

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_files_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Test 1.1: Verify all 4 .vue files appear in request_full_symbol_tree().

        This test confirms that the language server recognizes .vue files as valid
        source files and includes them in the full symbol tree. All four Vue components
        in the test repository should be discoverable.

        Files tested:
        - src/App.vue (root component)
        - src/components/CalculatorButton.vue
        - src/components/CalculatorInput.vue
        - src/components/CalculatorDisplay.vue
        """
        symbols = language_server.request_full_symbol_tree()

        # Verify all 4 .vue files are present in the symbol tree
        # Note: File symbols strip the extension (App.vue -> App)
        assert SymbolUtils.symbol_tree_contains_name(symbols, "App"), "App not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorButton"), "CalculatorButton not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorInput"), "CalculatorInput not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorDisplay"), "CalculatorDisplay not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_document_symbols_extraction(self, language_server: SolidLanguageServer) -> None:
        """Test 1.2: Call request_document_symbols() on .vue files and verify non-empty symbols.

        This test verifies that the language server can extract symbols from Vue files,
        testing both a simple component (CalculatorDisplay.vue) with fewer symbols
        and a complex component (App.vue) with more symbols.

        The symbols should include variables, functions, imports, and other declarations
        from the <script setup> section.
        """
        # Test simple component: CalculatorDisplay.vue (~8 symbols expected)
        simple_file = os.path.join("src", "components", "CalculatorDisplay.vue")
        simple_symbols = language_server.request_document_symbols(simple_file).get_all_symbols_and_roots()
        assert len(simple_symbols[0]) > 0, f"CalculatorDisplay.vue should have symbols, but got {len(simple_symbols[0])} symbols"

        # Test complex component: App.vue (~13 symbols expected)
        complex_file = os.path.join("src", "App.vue")
        complex_symbols = language_server.request_document_symbols(complex_file).get_all_symbols_and_roots()
        assert len(complex_symbols[0]) > 0, f"App.vue should have symbols, but got {len(complex_symbols[0])} symbols"

        # Note: We don't compare symbol counts between components because Vue LS includes
        # template elements and CSS selectors as symbols, making counts unpredictable.
        # Both files having symbols is sufficient to verify parsing works.

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_multi_section_handling(self, language_server: SolidLanguageServer) -> None:
        """Test 1.3: Verify <template>, <script setup>, and <style> sections don't break parsing.

        Vue Single File Components have three main sections: <template>, <script>, and <style>.
        This test verifies that the presence of all three sections doesn't prevent the
        language server from parsing the <script setup> section correctly.

        The parser should extract symbols from the script section despite the multi-section
        structure, which is a unique characteristic of .vue files compared to regular .ts files.
        """
        # Test with App.vue which has all three sections
        file_path = os.path.join("src", "App.vue")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Should have successfully extracted symbols from <script setup> section
        assert len(symbols[0]) > 0, "Should extract symbols from <script setup> despite multi-section structure"

        # Verify we can find specific symbols from the script section
        # (imports, variables, etc. should be discoverable)
        symbol_names = [sym.get("name") for sym in symbols[0]]
        assert len(symbol_names) > 0, "Should have named symbols from the script section"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_mixed_directory_handling(self, language_server: SolidLanguageServer) -> None:
        """Test 1.4: Verify components in subdirectory are found alongside root components.

        This test verifies that the language server correctly handles Vue components
        in different directory structures:
        - Root components (src/App.vue)
        - Subdirectory components (src/components/*.vue)

        Both should be discoverable in the symbol tree, which is essential for
        cross-file imports and references.
        """
        symbols = language_server.request_full_symbol_tree()

        # Root component should be found
        # Note: File symbols strip the extension (App.vue -> App)
        assert SymbolUtils.symbol_tree_contains_name(symbols, "App"), "Root component App should be in symbol tree"

        # Subdirectory components should also be found
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "CalculatorButton"
        ), "Component from src/components/ subdirectory (CalculatorButton) should be in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "CalculatorInput"
        ), "Component from src/components/ subdirectory (CalculatorInput) should be in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "CalculatorDisplay"
        ), "Component from src/components/ subdirectory (CalculatorDisplay) should be in symbol tree"

        # Verify we have at least 4 .vue files total (1 root + 3 in subdirectory)
        # This ensures the mixed directory structure works correctly
        vue_file_count = sum(
            1
            for name in ["App", "CalculatorButton", "CalculatorInput", "CalculatorDisplay"]
            if SymbolUtils.symbol_tree_contains_name(symbols, name)
        )

        assert vue_file_count == 4, f"Expected 4 .vue files in symbol tree (1 root + 3 in subdirectory), found {vue_file_count}"
