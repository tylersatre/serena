import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.vue
class TestVueLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_files_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "App"), "App not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorButton"), "CalculatorButton not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorInput"), "CalculatorInput not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorDisplay"), "CalculatorDisplay not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_script_setup_symbol_extraction(self, language_server: SolidLanguageServer) -> None:
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
        # HTML element ref
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        input_names = [s.get("name") for s in input_symbols[0]]
        assert "displayRef" in input_names, "displayRef (HTML element ref) not found"

        # Component instance ref
        assert "equalsButtonRef" in input_names, "equalsButtonRef (component instance ref) not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_pinia_store_integration(self, language_server: SolidLanguageServer) -> None:
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
        # If @ alias works, App.vue should successfully parse with @ imports
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        assert len(app_symbols[0]) >= 15, f"App.vue should have at least 15 symbols (proves @ imports resolved), got {len(app_symbols[0])}"

        # Verify specific @ imports are resolved
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useCalculatorStore"), "Store import via @ alias failed"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Operation"), "Type import via @ alias failed"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "useFormatter"), "Composable import via @ alias failed"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_component_imports(self, language_server: SolidLanguageServer) -> None:
        # Verify App.vue can parse successfully (contains component imports)
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        assert len(app_symbols[0]) >= 15, f"App.vue should have at least 15 symbols (refs, computed, etc.), got {len(app_symbols[0])}"

        # Verify imported components exist and have symbols
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorInput"), "CalculatorInput component not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorDisplay"), "CalculatorDisplay component not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorButton"), "CalculatorButton component not found"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_typescript_edge_cases(self, language_server: SolidLanguageServer) -> None:
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

        # Should have multiple references: definition + usage in App.vue, CalculatorInput.vue, CalculatorDisplay.vue
        assert len(refs) >= 4, f"useCalculatorStore should have at least 4 references (definition + 3 usages), got {len(refs)}"

        # Verify we have references from .vue files
        vue_refs = [ref for ref in refs if ".vue" in ref.get("relativePath", "")]
        assert len(vue_refs) >= 3, f"Should have at least 3 Vue component references, got {len(vue_refs)}"


@pytest.mark.vue
class TestVueDualLspArchitecture:
    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_typescript_server_coordination(self, language_server: SolidLanguageServer) -> None:
        ts_file = os.path.join("src", "stores", "calculator.ts")
        ts_symbols = language_server.request_document_symbols(ts_file).get_all_symbols_and_roots()
        ts_symbol_names = [s.get("name") for s in ts_symbols[0]]

        assert len(ts_symbols[0]) >= 5, f"TypeScript server should return multiple symbols for calculator.ts, got {len(ts_symbols[0])}"
        assert "useCalculatorStore" in ts_symbol_names, "TypeScript server should extract store function"

        # Verify Vue server can parse .vue files
        vue_file = os.path.join("src", "App.vue")
        vue_symbols = language_server.request_document_symbols(vue_file).get_all_symbols_and_roots()
        vue_symbol_names = [s.get("name") for s in vue_symbols[0]]

        assert len(vue_symbols[0]) >= 15, f"Vue server should return at least 15 symbols for App.vue, got {len(vue_symbols[0])}"
        assert "appTitle" in vue_symbol_names, "Vue server should extract ref declarations from script setup"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_cross_file_references_vue_to_typescript(self, language_server: SolidLanguageServer) -> None:
        store_file = os.path.join("src", "stores", "calculator.ts")
        store_symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        store_symbol = None
        for sym in store_symbols[0]:
            if sym.get("name") == "useCalculatorStore":
                store_symbol = sym
                break

        if not store_symbol or "selectionRange" not in store_symbol:
            pytest.skip("useCalculatorStore symbol not found - test fixture may need updating")

        # Request references for this symbol
        sel_start = store_symbol["selectionRange"]["start"]
        refs = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Verify we found references: definition + usage in App.vue, CalculatorInput.vue, CalculatorDisplay.vue
        assert len(refs) >= 4, f"useCalculatorStore should have at least 4 references (definition + 3 usages), found {len(refs)} references"

        # Verify references include .vue files (components that import the store)
        vue_refs = [ref for ref in refs if ".vue" in ref.get("uri", "")]
        assert (
            len(vue_refs) >= 3
        ), f"Should find at least 3 references in Vue components, found {len(vue_refs)}: {[ref.get('uri', '') for ref in vue_refs]}"

        # Verify specific components that use the store
        expected_vue_files = ["App.vue", "CalculatorInput.vue", "CalculatorDisplay.vue"]
        found_components = []
        for expected_file in expected_vue_files:
            matching_refs = [ref for ref in vue_refs if expected_file in ref.get("uri", "")]
            if matching_refs:
                found_components.append(expected_file)

        assert len(found_components) > 0, (
            f"Should find references in at least one component that uses the store. "
            f"Expected any of {expected_vue_files}, found references in: {[ref.get('uri', '') for ref in vue_refs]}"
        )

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_cross_file_references_typescript_to_vue(self, language_server: SolidLanguageServer) -> None:
        types_file = os.path.join("src", "types", "index.ts")
        types_symbols = language_server.request_document_symbols(types_file).get_all_symbols_and_roots()
        types_symbol_names = [s.get("name") for s in types_symbols[0]]

        # Operation type is used in calculator.ts and CalculatorInput.vue
        assert "Operation" in types_symbol_names, "Operation type should exist in types file"

        operation_symbol = None
        for sym in types_symbols[0]:
            if sym.get("name") == "Operation":
                operation_symbol = sym
                break

        if not operation_symbol or "selectionRange" not in operation_symbol:
            pytest.skip("Operation type symbol not found - test fixture may need updating")

        # Request references for the Operation type
        sel_start = operation_symbol["selectionRange"]["start"]
        refs = language_server.request_references(types_file, sel_start["line"], sel_start["character"])

        # Verify we found references: definition + usage in calculator.ts and Vue files
        assert len(refs) >= 2, f"Operation type should have at least 2 references (definition + usages), found {len(refs)} references"

        # The Operation type should be referenced in both .ts files (calculator.ts) and potentially .vue files
        all_ref_uris = [ref.get("uri", "") for ref in refs]
        has_ts_refs = any(".ts" in uri and "types" not in uri for uri in all_ref_uris)

        assert (
            has_ts_refs
        ), f"Operation type should be referenced in TypeScript files like calculator.ts. Found references in: {all_ref_uris}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_reference_deduplication(self, language_server: SolidLanguageServer) -> None:
        store_file = os.path.join("src", "stores", "calculator.ts")
        store_symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find a commonly-used symbol (useCalculatorStore)
        store_symbol = None
        for sym in store_symbols[0]:
            if sym.get("name") == "useCalculatorStore":
                store_symbol = sym
                break

        if not store_symbol or "selectionRange" not in store_symbol:
            pytest.skip("useCalculatorStore symbol not found - test fixture may need updating")

        # Request references
        sel_start = store_symbol["selectionRange"]["start"]
        refs = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Check for duplicate references (same file, line, and character)
        seen_locations = set()
        duplicates = []

        for ref in refs:
            # Create a unique key for this reference location
            uri = ref.get("uri", "")
            if "range" in ref:
                line = ref["range"]["start"]["line"]
                character = ref["range"]["start"]["character"]
                location_key = (uri, line, character)

                if location_key in seen_locations:
                    duplicates.append(location_key)
                else:
                    seen_locations.add(location_key)

        assert len(duplicates) == 0, (
            f"Found {len(duplicates)} duplicate reference locations. "
            f"The dual-LSP architecture should deduplicate references from both servers. "
            f"Duplicates: {duplicates}"
        )


@pytest.mark.vue
class TestVueSpecificFeatures:
    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_reactive_primitives_are_symbols(self, language_server: SolidLanguageServer) -> None:
        app_file = os.path.join("src", "App.vue")
        doc_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        symbol_names = [s.get("name") for s in doc_symbols[0]]

        # Verify ref declarations are symbols
        assert "appTitle" in symbol_names, "ref declarations like 'appTitle' should be extractable symbols"

        # Verify computed properties are symbols
        assert "totalCalculations" in symbol_names, "computed properties like 'totalCalculations' should be symbols"
        assert "greetingMessage" in symbol_names, "computed properties like 'greetingMessage' should be symbols"
        assert "isCalculatorActive" in symbol_names, "computed properties like 'isCalculatorActive' should be symbols"

        # Verify watch/watchEffect callbacks are recognized
        # Note: The exact symbol name for watch callbacks may vary by LSP implementation,
        # but they should be present in some form
        watch_related = [name for name in symbol_names if name and "watch" in str(name).lower()]
        assert len(watch_related) > 0, f"watch or watchEffect callbacks should appear in symbols. Found symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_lifecycle_hooks_as_symbols(self, language_server: SolidLanguageServer) -> None:
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        app_symbol_names = [s.get("name") for s in app_symbols[0]]

        lifecycle_hooks_in_app = [
            name for name in app_symbol_names if name and ("mounted" in str(name).lower() or "unmount" in str(name).lower())
        ]
        assert len(lifecycle_hooks_in_app) >= 1, (
            f"App.vue has onMounted lifecycle hook which should appear in symbols. "
            f"Found {len(lifecycle_hooks_in_app)} lifecycle hooks: {lifecycle_hooks_in_app}"
        )

        # Test CalculatorInput.vue which has onMounted and onBeforeUnmount
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        input_symbol_names = [s.get("name") for s in input_symbols[0]]

        lifecycle_hooks_in_input = [
            name for name in input_symbol_names if name and ("mounted" in str(name).lower() or "unmount" in str(name).lower())
        ]
        assert len(lifecycle_hooks_in_input) >= 2, (
            f"CalculatorInput.vue has onMounted and onBeforeUnmount hooks (2 total) which should appear in symbols. "
            f"Found {len(lifecycle_hooks_in_input)} lifecycle hooks: {lifecycle_hooks_in_input}"
        )

        # Verify we found lifecycle hooks in multiple components
        assert (
            len(lifecycle_hooks_in_app) + len(lifecycle_hooks_in_input) >= 2
        ), "Should find at least 2 lifecycle hook symbols across App.vue and CalculatorInput.vue"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_watch_callbacks_recognized(self, language_server: SolidLanguageServer) -> None:
        app_file = os.path.join("src", "App.vue")
        app_symbols = language_server.request_document_symbols(app_file).get_all_symbols_and_roots()
        app_symbol_names = [s.get("name") for s in app_symbols[0]]

        # Look for watch-related symbols
        watch_symbols = [name for name in app_symbol_names if name and "watch" in str(name).lower()]
        assert len(watch_symbols) >= 2, (
            f"App.vue uses both watch() and watchEffect() which should create at least 2 watch-related symbols. "
            f"Found {len(watch_symbols)} watch-related symbols: {watch_symbols}"
        )

        # CalculatorInput.vue also has watch calls
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        input_symbol_names = [s.get("name") for s in input_symbols[0]]

        watch_symbols_input = [name for name in input_symbol_names if name and "watch" in str(name).lower()]
        assert (
            len(watch_symbols_input) >= 1
        ), f"CalculatorInput.vue uses watch() which should create symbols. Found watch-related symbols: {watch_symbols_input}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_computed_returning_functions(self, language_server: SolidLanguageServer) -> None:
        input_file = os.path.join("src", "components", "CalculatorInput.vue")
        input_symbols = language_server.request_document_symbols(input_file).get_all_symbols_and_roots()
        input_symbol_names = [s.get("name") for s in input_symbols[0]]

        # getOperationClass is a computed property that returns a function
        assert "getOperationClass" in input_symbol_names, (
            "Computed properties that return functions should be extracted as symbols. "
            f"Expected 'getOperationClass' in symbols, found: {input_symbol_names}"
        )

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_directory_exclusion(self, language_server: SolidLanguageServer) -> None:
        full_tree = language_server.request_full_symbol_tree()

        # Flatten the symbol tree to get all file paths
        def extract_file_paths(symbols, paths=None):
            """Recursively extract all file paths from symbol tree."""
            if paths is None:
                paths = []

            if isinstance(symbols, list):
                for symbol in symbols:
                    extract_file_paths(symbol, paths)
            elif isinstance(symbols, dict):
                # Check if this is a file/module symbol with a location
                if "location" in symbols:
                    uri = symbols["location"].get("uri", "")
                    if uri:
                        paths.append(uri)

                # Recurse into children
                if "children" in symbols:
                    extract_file_paths(symbols["children"], paths)

            return paths

        file_paths = extract_file_paths(full_tree)

        # Check that excluded directories are not present
        excluded_dirs = ["node_modules", "dist", ".nuxt"]
        for excluded_dir in excluded_dirs:
            matching_paths = [path for path in file_paths if excluded_dir in path]
            assert len(matching_paths) == 0, (
                f"Directory '{excluded_dir}' should be excluded from symbol tree. "
                f"Found {len(matching_paths)} files from this directory: {matching_paths[:5]}"
            )

        # Verify we still have symbols from the actual source directories
        src_paths = [path for path in file_paths if "src/" in path or "src\\" in path]
        assert len(src_paths) >= 8, (
            f"Source files from 'src/' directory should be included in symbol tree (at least 8 files: App.vue, 3 components, calculator.ts, 2 composables, types/index.ts). "
            f"Found {len(src_paths)} src/ paths"
        )


@pytest.mark.vue
class TestVueEdgeCases:
    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_empty_position_handling(self, language_server: SolidLanguageServer) -> None:
        app_file = os.path.join("src", "App.vue")

        # Test position at line 0, character 0 (typically template tag)
        containing_symbol = language_server.request_containing_symbol(app_file, 0, 0)

        # Should return None or empty dict, not crash
        # May return the template symbol or None depending on LSP behavior
        assert (
            containing_symbol is None or containing_symbol == {} or isinstance(containing_symbol, dict)
        ), f"Position at line 0, character 0 should return None, empty dict, or a valid symbol. Got: {containing_symbol}"

        # Test references at an empty position (template start)
        refs = language_server.request_references(app_file, 0, 0)

        # Some LSPs return None, others return empty list for positions with no references
        assert refs is None or isinstance(refs, list), f"References at position should return None or a list. Got: {refs}"

        # Test containing symbol at a position in script imports (should be at top-level or no containing symbol)
        # Line 1-5 typically contain <template>, <script>, and imports in Vue SFCs
        import_position = language_server.request_containing_symbol(app_file, 3, 5)

        # Should return None, empty dict, or possibly a script/template symbol
        assert (
            import_position is None or import_position == {} or isinstance(import_position, dict)
        ), f"Position in imports/top-level should return None, empty dict, or valid symbol. Got: {import_position}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_symbol_tree_structure(self, language_server: SolidLanguageServer) -> None:
        full_tree = language_server.request_full_symbol_tree()

        # Helper to extract all file paths from symbol tree
        def extract_paths_from_tree(symbols, paths=None):
            """Recursively extract file paths from symbol tree."""
            if paths is None:
                paths = []

            if isinstance(symbols, list):
                for symbol in symbols:
                    extract_paths_from_tree(symbol, paths)
            elif isinstance(symbols, dict):
                # Check if this symbol has a location
                if "location" in symbols and "uri" in symbols["location"]:
                    uri = symbols["location"]["uri"]
                    # Extract the path after file://
                    if uri.startswith("file://"):
                        file_path = uri[7:]  # Remove "file://"
                        paths.append(file_path)

                # Recurse into children
                if "children" in symbols:
                    extract_paths_from_tree(symbols["children"], paths)

            return paths

        all_paths = extract_paths_from_tree(full_tree)

        # Verify we have files from expected directories
        # Note: Symbol tree may include duplicate paths (one per symbol in file)
        components_files = list({p for p in all_paths if "components" in p and ".vue" in p})
        stores_files = list({p for p in all_paths if "stores" in p and ".ts" in p})
        composables_files = list({p for p in all_paths if "composables" in p and ".ts" in p})

        assert len(components_files) == 3, (
            f"Symbol tree should include exactly 3 unique Vue components (CalculatorButton, CalculatorInput, CalculatorDisplay). "
            f"Found {len(components_files)} unique component files: {[p.split('/')[-1] for p in sorted(components_files)]}"
        )

        assert len(stores_files) == 1, (
            f"Symbol tree should include exactly 1 unique store file (calculator.ts). "
            f"Found {len(stores_files)} unique store files: {[p.split('/')[-1] for p in sorted(stores_files)]}"
        )

        assert len(composables_files) == 2, (
            f"Symbol tree should include exactly 2 unique composable files (useFormatter.ts, useTheme.ts). "
            f"Found {len(composables_files)} unique composable files: {[p.split('/')[-1] for p in sorted(composables_files)]}"
        )

        # Verify specific expected files exist in the tree
        expected_files = [
            "CalculatorButton.vue",
            "CalculatorInput.vue",
            "CalculatorDisplay.vue",
            "App.vue",
            "calculator.ts",
            "useFormatter.ts",
            "useTheme.ts",
        ]

        for expected_file in expected_files:
            matching_files = [p for p in all_paths if expected_file in p]
            assert len(matching_files) > 0, f"Expected file '{expected_file}' should be in symbol tree. All paths: {all_paths}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_document_overview(self, language_server: SolidLanguageServer) -> None:
        app_file = os.path.join("src", "App.vue")
        overview = language_server.request_document_overview(app_file)

        # Overview should return a list of top-level symbols
        assert isinstance(overview, list), f"Overview should be a list, got: {type(overview)}"
        assert len(overview) >= 1, f"App.vue should have at least 1 top-level symbol in overview, got {len(overview)}"

        # Extract symbol names from overview
        symbol_names = [s.get("name") for s in overview if isinstance(s, dict)]

        # Vue LSP returns SFC structure (template/script/style sections) for .vue files
        # This is expected behavior - overview shows the file's high-level structure
        assert (
            len(symbol_names) >= 1
        ), f"Should have at least 1 symbol name in overview (e.g., 'App' or SFC section), got {len(symbol_names)}: {symbol_names}"

        # Test overview for a TypeScript file
        store_file = os.path.join("src", "stores", "calculator.ts")
        store_overview = language_server.request_document_overview(store_file)

        assert isinstance(store_overview, list), f"Store overview should be a list, got: {type(store_overview)}"
        assert len(store_overview) >= 1, f"calculator.ts should have at least 1 top-level symbol in overview, got {len(store_overview)}"

        store_symbol_names = [s.get("name") for s in store_overview if isinstance(s, dict)]
        assert (
            "useCalculatorStore" in store_symbol_names
        ), f"useCalculatorStore should be in store file overview. Found {len(store_symbol_names)} symbols: {store_symbol_names}"

        # Test overview for another Vue component
        button_file = os.path.join("src", "components", "CalculatorButton.vue")
        button_overview = language_server.request_document_overview(button_file)

        assert isinstance(button_overview, list), f"Button overview should be a list, got: {type(button_overview)}"
        assert (
            len(button_overview) >= 1
        ), f"CalculatorButton.vue should have at least 1 top-level symbol in overview, got {len(button_overview)}"

        # For Vue files, overview provides SFC structure which is useful for navigation
        # The detailed symbols are available via request_document_symbols
        button_symbol_names = [s.get("name") for s in button_overview if isinstance(s, dict)]
        assert len(button_symbol_names) >= 1, (
            f"CalculatorButton.vue should have at least 1 symbol in overview (e.g., 'CalculatorButton' or SFC section). "
            f"Found {len(button_symbol_names)} symbols: {button_symbol_names}"
        )

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_directory_overview(self, language_server: SolidLanguageServer) -> None:
        components_dir = os.path.join("src", "components")
        dir_overview = language_server.request_dir_overview(components_dir)

        # Directory overview should be a dict mapping file paths to symbol lists
        assert isinstance(dir_overview, dict), f"Directory overview should be a dict, got: {type(dir_overview)}"
        assert len(dir_overview) == 3, f"src/components directory should have exactly 3 files in overview, got {len(dir_overview)}"

        # Verify all component files are included
        expected_components = ["CalculatorButton.vue", "CalculatorInput.vue", "CalculatorDisplay.vue"]

        for expected_component in expected_components:
            # Find files that match this component name
            matching_files = [path for path in dir_overview.keys() if expected_component in path]
            assert len(matching_files) == 1, (
                f"Component '{expected_component}' should appear exactly once in directory overview. "
                f"Found {len(matching_files)} matches. All files: {list(dir_overview.keys())}"
            )

            # Verify the matched file has symbols
            file_path = matching_files[0]
            symbols = dir_overview[file_path]
            assert isinstance(symbols, list), f"Symbols for {file_path} should be a list, got {type(symbols)}"
            assert len(symbols) >= 1, f"Component {expected_component} should have at least 1 symbol in overview, got {len(symbols)}"

        # Test overview for stores directory
        stores_dir = os.path.join("src", "stores")
        stores_overview = language_server.request_dir_overview(stores_dir)

        assert isinstance(stores_overview, dict), f"Stores overview should be a dict, got: {type(stores_overview)}"
        assert (
            len(stores_overview) == 1
        ), f"src/stores directory should have exactly 1 file (calculator.ts) in overview, got {len(stores_overview)}"

        # Verify calculator.ts is included
        calculator_files = [path for path in stores_overview.keys() if "calculator.ts" in path]
        assert len(calculator_files) == 1, (
            f"calculator.ts should appear exactly once in stores directory overview. "
            f"Found {len(calculator_files)} matches. All files: {list(stores_overview.keys())}"
        )

        # Verify the store file has symbols
        store_path = calculator_files[0]
        store_symbols = stores_overview[store_path]
        store_symbol_names = [s.get("name") for s in store_symbols if isinstance(s, dict)]
        assert (
            "useCalculatorStore" in store_symbol_names
        ), f"calculator.ts should have useCalculatorStore in overview. Found {len(store_symbol_names)} symbols: {store_symbol_names}"

        # Test overview for composables directory
        composables_dir = os.path.join("src", "composables")
        composables_overview = language_server.request_dir_overview(composables_dir)

        assert isinstance(composables_overview, dict), f"Composables overview should be a dict, got: {type(composables_overview)}"
        assert (
            len(composables_overview) == 2
        ), f"src/composables directory should have exactly 2 files in overview, got {len(composables_overview)}"

        # Verify composable files are included
        expected_composables = ["useFormatter.ts", "useTheme.ts"]
        for expected_composable in expected_composables:
            matching_files = [path for path in composables_overview.keys() if expected_composable in path]
            assert len(matching_files) == 1, (
                f"Composable '{expected_composable}' should appear exactly once in directory overview. "
                f"Found {len(matching_files)} matches. All files: {list(composables_overview.keys())}"
            )
