"""
Vue-specific test configuration and fixtures.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest


def ensure_vue_test_repo_dependencies(repo_path: str) -> None:
    """Ensure the Vue test repository dependencies are installed.

    The Vue language server (TypeScript LSP) requires dependencies to be installed
    for proper symbol resolution and cross-file references. This function checks
    if node_modules exists and runs 'npm install' if needed.

    This is essential in CI environments where dependencies aren't pre-installed.

    Args:
        repo_path: Path to the Vue project root directory

    """
    # Check if this looks like a Node.js project
    package_json = os.path.join(repo_path, "package.json")
    if not os.path.exists(package_json):
        return

    # Check if dependencies are already installed
    node_modules = os.path.join(repo_path, "node_modules")

    if os.path.exists(node_modules) and os.path.isdir(node_modules):
        # Verify node_modules is not empty
        if any(os.scandir(node_modules)):
            print(f"Vue test repository dependencies already installed in {repo_path}")
            return

    try:
        print("Installing Vue test repository dependencies for optimal LSP performance...")

        print("=" * 60)
        print("Running: npm install")
        print("=" * 60)
        start_time = time.time()

        install_result = subprocess.run(
            ["npm", "install"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes for npm install (CI can be slow)
            check=False,
        )

        duration = time.time() - start_time
        print(f"npm install completed in {duration:.2f} seconds")

        # Always log the output for transparency
        if install_result.stdout.strip():
            print("npm install stdout:")
            print("-" * 40)
            print(install_result.stdout)
            print("-" * 40)

        if install_result.stderr.strip():
            print("npm install stderr:")
            print("-" * 40)
            print(install_result.stderr)
            print("-" * 40)

        if install_result.returncode == 0:
            print(f"✓ Vue test repository dependencies installed successfully in {repo_path}")
        else:
            print(f"⚠️  Warning: npm install completed with exit code {install_result.returncode}")
            # Still continue - some warnings are non-fatal

        print("=" * 60)

    except subprocess.TimeoutExpired as e:
        print("=" * 60)
        print(f"❌ TIMEOUT: npm install timed out after {e.timeout} seconds")
        print(f"Command: {' '.join(e.cmd)}")
        print("This may indicate slow CI environment - TypeScript LSP may still work but with reduced functionality")

        # Try to get partial output if available
        if hasattr(e, "stdout") and e.stdout:
            print("Partial stdout before timeout:")
            print("-" * 40)
            print(e.stdout)
            print("-" * 40)
        if hasattr(e, "stderr") and e.stderr:
            print("Partial stderr before timeout:")
            print("-" * 40)
            print(e.stderr)
            print("-" * 40)
        print("=" * 60)

    except FileNotFoundError:
        print("❌ ERROR: 'npm' command not found - Vue test repository dependencies may not be installed")
        print("Please ensure Node.js and npm are installed and available in PATH")
    except Exception as e:
        print(f"❌ ERROR: Failed to install Vue test repository dependencies: {e}")


@pytest.fixture(scope="session", autouse=True)
def setup_vue_test_environment():
    """Automatically prepare Vue test environment for all Vue tests.

    This fixture runs once per test session and automatically installs
    dependencies via 'npm install' if needed.

    It uses autouse=True so it runs automatically without needing to be explicitly
    requested by tests. This ensures the TypeScript LSP has a fully prepared project
    to work with.

    Uses generous timeout (5 minutes) to accommodate slow CI environments.
    All output is logged for transparency and debugging.
    """
    # Get the test repo path relative to this conftest.py file
    test_repo_path = Path(__file__).parent.parent.parent / "resources" / "repos" / "vue" / "test_repo"
    ensure_vue_test_repo_dependencies(str(test_repo_path))
    return str(test_repo_path)
