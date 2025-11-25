#!/usr/bin/env python3
"""Debug script to test Vue Language Server custom volar/client/findFileReference request."""

import logging
import os
import sys
from pathlib import Path

# Add test directory to path to import conftest utilities
sys.path.insert(0, str(Path(__file__).parent / "test"))

from conftest import create_default_ls
from solidlsp.ls_config import Language

# Enable debug logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Test repository path
test_repo = Path(__file__).parent / "test/resources/repos/vue/test_repo"

print(f"Testing Vue Language Server with repository: {test_repo}")
print("-" * 80)

# Create language server using test helper
ls = create_default_ls(Language.VUE)

try:
    # Start the server
    print("Starting Vue Language Server...")
    ls.start()
    print("Language server started successfully")
    print("-" * 80)

    # Test 1: Get symbols from CalculatorButton.vue
    print("\n1. Getting symbols from CalculatorButton.vue...")
    button_file = os.path.join("src", "components", "CalculatorButton.vue")
    symbols = ls.request_document_symbols(button_file).get_all_symbols_and_roots()
    print(f"Found {len(symbols[0])} symbols")
    for sym in symbols[0][:5]:  # Show first 5
        print(f"  - {sym.get('name')} ({sym.get('kind')})")

    # Test 2: Try custom volar/client/findFileReference request
    print("\n2. Testing volar/client/findFileReference for CalculatorButton.vue...")
    if hasattr(ls, 'request_file_references'):
        file_refs = ls.request_file_references(button_file)
        print(f"Found {len(file_refs)} file references")
        for ref in file_refs:
            print(f"  - {ref.get('relativePath')} at line {ref['range']['start']['line']}")
    else:
        print("  ERROR: request_file_references method not found on language server")

    # Test 3: Try textDocument/references for comparison
    print("\n3. Testing textDocument/references for Props symbol...")
    props_symbol = None
    for sym in symbols[0]:
        if sym.get("name") == "Props":
            props_symbol = sym
            break

    if props_symbol:
        sel_start = props_symbol["selectionRange"]["start"]
        print(f"Props symbol at line {sel_start['line']}, character {sel_start['character']}")
        references = ls.request_references(button_file, sel_start["line"], sel_start["character"])
        print(f"Found {len(references)} references via textDocument/references")
        for ref in references:
            print(f"  - {ref.get('relativePath')} at line {ref['range']['start']['line']}")
    else:
        print("  ERROR: Props symbol not found")

    # Test 4: Direct file reference for CalculatorInput.vue
    print("\n4. Testing volar/client/findFileReference for CalculatorInput.vue...")
    input_file = os.path.join("src", "components", "CalculatorInput.vue")
    if hasattr(ls, 'request_file_references'):
        file_refs = ls.request_file_references(input_file)
        print(f"Found {len(file_refs)} file references")
        for ref in file_refs:
            print(f"  - {ref.get('relativePath')} at line {ref['range']['start']['line']}")

    print("\n" + "=" * 80)
    print("Debug test complete!")

finally:
    print("\nStopping language server...")
    ls.stop()
    print("Language server stopped")
