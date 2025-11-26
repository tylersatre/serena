import os
import subprocess
import time
from pathlib import Path

import pytest


def ensure_vue_test_repo_dependencies(repo_path: str) -> None:
    package_json = os.path.join(repo_path, "package.json")
    if not os.path.exists(package_json):
        return

    node_modules = os.path.join(repo_path, "node_modules")

    if os.path.exists(node_modules) and os.path.isdir(node_modules):
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

        print("=" * 60)

    except subprocess.TimeoutExpired as e:
        print("=" * 60)
        print(f"❌ TIMEOUT: npm install timed out after {e.timeout} seconds")
        print(f"Command: {' '.join(e.cmd)}")
        print("This may indicate slow CI environment - TypeScript LSP may still work but with reduced functionality")

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
    test_repo_path = Path(__file__).parent.parent.parent / "resources" / "repos" / "vue" / "test_repo"
    ensure_vue_test_repo_dependencies(str(test_repo_path))
    return str(test_repo_path)
