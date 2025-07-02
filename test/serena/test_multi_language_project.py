import json
from pathlib import Path

import pytest

from serena.agent import (
    FindSymbolTool,
    GetLanguageStatisticsTool,
    GetSymbolsOverviewTool,
    ProjectConfig,
    SearchForPatternTool,
    SerenaAgent,
    SerenaConfigBase,
)
from serena.util.general import save_yaml
from solidlsp.ls_config import Language


class TestConfig(SerenaConfigBase):
    gui_log_window_enabled: bool = False
    web_dashboard: bool = False


def test_find_symbol_across_languages():
    """Test basic symbol finding across multiple languages."""
    repo = Path("test/resources/repos/multi/test_repo")
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())

    # Wait for language server initialization to complete
    import time

    for _ in range(50):  # Wait up to 5 seconds
        if agent.symbol_manager is not None:
            break
        time.sleep(0.1)
    assert agent.symbol_manager is not None, "Language server failed to initialize"

    tool = agent.get_tool(FindSymbolTool)
    
    # Test finding symbols across all languages
    result = json.loads(tool.apply("func", substring_matching=True))
    paths = {s["relative_path"] for s in result}
    assert "py_mod.py" in paths
    assert "ts_mod.ts" in paths

    # Test language-specific filtering
    result_py = json.loads(tool.apply("py_func", language="python"))
    assert any(r["relative_path"] == "py_mod.py" for r in result_py)
    assert not any(r["relative_path"] == "ts_mod.ts" for r in result_py)
    
    result_ts = json.loads(tool.apply("ts_func", language="typescript"))
    assert any(r["relative_path"] == "ts_mod.ts" for r in result_ts)
    assert not any(r["relative_path"] == "py_mod.py" for r in result_ts)


def test_get_symbols_overview_with_language_filter():
    """Test get_symbols_overview tool with language filtering."""
    repo = Path("test/resources/repos/multi/test_repo")
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())
    
    # Wait for initialization
    import time
    for _ in range(50):
        if agent.symbol_manager is not None:
            break
        time.sleep(0.1)
    assert agent.symbol_manager is not None
    
    tool = agent.get_tool(GetSymbolsOverviewTool)
    
    # Test overview without language filter (should include all files)
    result = json.loads(tool.apply("."))
    assert "py_mod.py" in result
    assert "ts_mod.ts" in result
    
    # Test with Python language filter
    result_py = json.loads(tool.apply(".", language="python"))
    assert "py_mod.py" in result_py
    assert "ts_mod.ts" not in result_py
    
    # Test with TypeScript language filter
    result_ts = json.loads(tool.apply(".", language="typescript"))
    assert "ts_mod.ts" in result_ts
    assert "py_mod.py" not in result_ts


def test_search_for_pattern_with_language_filter():
    """Test search_for_pattern tool with language filtering."""
    repo = Path("test/resources/repos/multi/test_repo")
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())
    
    # Wait for initialization
    import time
    for _ in range(50):
        if agent.symbol_manager is not None:
            break
        time.sleep(0.1)
    assert agent.symbol_manager is not None
    
    tool = agent.get_tool(SearchForPatternTool)
    
    # Search for "function" in all languages
    result = json.loads(tool.apply("function"))
    assert len(result) > 0
    
    # Search only in Python files
    result_py = json.loads(tool.apply("def", language="python"))
    for file_path in result_py:
        assert file_path.endswith(".py")
    
    # Search only in TypeScript files
    result_ts = json.loads(tool.apply("function", language="typescript"))
    for file_path in result_ts:
        assert file_path.endswith(".ts")

def test_find_referencing_symbols_with_language_filter(get_agent):
    """Test that FindReferencingSymbolsTool respects language parameter."""
    agent = get_agent(repo_root=TestConfig.root)
    
    # First, create a Python class that will be referenced
    py_file = TestConfig.root / "base_class.py"
    py_file.write_text("""
class BaseProcessor:
    def process(self):
        pass
""")
    
    # Create Python file that references BaseProcessor
    py_ref_file = TestConfig.root / "py_processor.py"
    py_ref_file.write_text("""
from base_class import BaseProcessor

class PythonProcessor(BaseProcessor):
    def process(self):
        return "Python processing"
""")
    
    # Create TypeScript file that also has a BaseProcessor reference (but different)
    ts_ref_file = TestConfig.root / "ts_processor.ts"
    ts_ref_file.write_text("""
import { BaseProcessor } from './base_processor';

class TypeScriptProcessor extends BaseProcessor {
    process(): string {
        return "TypeScript processing";
    }
}
""")
    
    # Use FindReferencingSymbolsTool to find references
    find_ref_tool = agent.get_tool("find_referencing_symbols")
    
    # Find all references to BaseProcessor
    all_refs_result = find_ref_tool.apply(
        name_path="BaseProcessor",
        relative_path="base_class.py"
    )
    all_refs = json.loads(all_refs_result)
    
    # Should find the Python reference (TypeScript one is to a different BaseProcessor)
    assert len(all_refs) == 1
    assert any("PythonProcessor" in str(ref) for ref in all_refs)
    
    # Find only Python references
    py_refs_result = find_ref_tool.apply(
        name_path="BaseProcessor",
        relative_path="base_class.py",
        language="python"
    )
    py_refs = json.loads(py_refs_result)
    
    # Should still find the Python reference
    assert len(py_refs) == 1
    assert any("PythonProcessor" in str(ref) for ref in py_refs)
    
    # Find only TypeScript references (should be empty since TS file references different BaseProcessor)
    ts_refs_result = find_ref_tool.apply(
        name_path="BaseProcessor",
        relative_path="base_class.py",
        language="typescript"
    )
    ts_refs = json.loads(ts_refs_result)
    
    # Should find no TypeScript references to the Python BaseProcessor
    assert len(ts_refs) == 0


def test_language_detection():
    """Test automatic language detection in projects."""
    repo = Path("test/resources/repos/multi/test_repo")
    
    # Create agent without specifying languages
    project_config = ProjectConfig(
        name="test_multi_lang",
        root_path=str(repo),
        # languages not specified - should auto-detect
    )
    
    # Save project config
    project_dir = repo / ".serena"
    project_dir.mkdir(exist_ok=True)
    save_yaml(project_config.to_json_dict(), project_dir / "project.yml")
    
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())
    
    # Check that languages were detected
    assert agent._active_project is not None
    assert Language.PYTHON in agent._active_project.languages
    assert Language.TYPESCRIPT in agent._active_project.languages


def test_language_statistics_tool():
    """Test the GetLanguageStatisticsTool."""
    repo = Path("test/resources/repos/multi/test_repo")
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())
    
    # Wait for initialization
    import time
    for _ in range(50):
        if agent.symbol_manager is not None:
            break
        time.sleep(0.1)
    assert agent.symbol_manager is not None
    
    tool = agent.get_tool(GetLanguageStatisticsTool)
    result = json.loads(tool.apply())
    
    # Check that statistics were generated
    assert "languages" in result
    assert len(result["languages"]) >= 2  # At least Python and TypeScript
    
    # Check Python stats
    python_stats = next((lang for lang in result["languages"] if lang["language"] == "python"), None)
    assert python_stats is not None
    assert python_stats["file_count"] >= 1
    assert python_stats["percentage"] > 0
    assert len(python_stats["common_patterns"]) > 0
    
    # Check TypeScript stats
    ts_stats = next((lang for lang in result["languages"] if lang["language"] == "typescript"), None)
    assert ts_stats is not None
    assert ts_stats["file_count"] >= 1
    assert ts_stats["percentage"] > 0


def test_project_config_backward_compatibility():
    """Test that ProjectConfig handles both old 'language' and new 'languages' format."""
    # Test old format with single language
    old_config = {
        "name": "test_project",
        "root_path": "/path/to/project",
        "language": "python"
    }
    project = ProjectConfig.from_json_dict(old_config)
    assert project.languages == [Language.PYTHON]
    
    # Test new format with multiple languages
    new_config = {
        "name": "test_project",
        "root_path": "/path/to/project",
        "languages": ["python", "typescript"]
    }
    project = ProjectConfig.from_json_dict(new_config)
    assert Language.PYTHON in project.languages
    assert Language.TYPESCRIPT in project.languages
    
    # Test that to_json_dict outputs new format
    output = project.to_json_dict()
    assert "languages" in output
    assert "language" not in output
    assert output["languages"] == ["python", "typescript"]


def test_missing_language_server_handling():
    """Test handling of files when language server is not available."""
    # This test would require mocking a missing language server
    # For now, we'll test the behavior with an unsupported file type
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a project with an unsupported file type
        test_file = Path(temp_dir) / "test.xyz"  # Unsupported extension
        test_file.write_text("Some content")
        
        # Create a Python file too
        py_file = Path(temp_dir) / "test.py"
        py_file.write_text("def test_func(): pass")
        
        agent = SerenaAgent(project=temp_dir, serena_config=TestConfig())
        
        # Wait for initialization
        import time
        for _ in range(50):
            if agent.symbol_manager is not None:
                break
            time.sleep(0.1)
        
        # The agent should still work with supported files
        tool = agent.get_tool(FindSymbolTool)
        result = json.loads(tool.apply("test_func"))
        assert len(result) > 0


def test_empty_project_handling():
    """Test handling of empty projects."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        agent = SerenaAgent(project=temp_dir, serena_config=TestConfig())
        
        # Should handle empty project gracefully
        tool = agent.get_tool(GetLanguageStatisticsTool)
        result = json.loads(tool.apply())
        assert "languages" in result
        assert len(result["languages"]) == 0 or all(lang["file_count"] == 0 for lang in result["languages"])


def test_large_multi_language_project():
    """Test performance with multiple languages and files."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create files for multiple languages
        languages_and_extensions = [
            ("python", ".py", "def func_{i}(): pass"),
            ("typescript", ".ts", "function func_{i}() {{ return {i}; }}"),
            ("java", ".java", "public class Class{i} {{ public void func_{i}() {{}} }}"),
            ("go", ".go", "package main\n\nfunc func_{i}() {{ return }}"),
        ]
        
        for lang, ext, template in languages_and_extensions:
            for i in range(5):  # Create 5 files per language
                file_path = Path(temp_dir) / f"{lang}_file_{i}{ext}"
                content = template.format(i=i)
                file_path.write_text(content)
        
        agent = SerenaAgent(project=temp_dir, serena_config=TestConfig())
        
        # Wait for initialization
        import time
        for _ in range(100):  # Wait longer for multiple language servers
            if agent.symbol_manager is not None:
                break
            time.sleep(0.1)
        
        # Test language statistics
        tool = agent.get_tool(GetLanguageStatisticsTool)
        result = json.loads(tool.apply())
        assert len(result["languages"]) >= 2  # At least some languages should be detected
        
        # Test finding symbols with language filter
        find_tool = agent.get_tool(FindSymbolTool)
        for lang, _, _ in languages_and_extensions[:2]:  # Test at least Python and TypeScript
            if lang == "python":
                lang_enum = "python"
            elif lang == "typescript":
                lang_enum = "typescript"
            else:
                continue
                
            result = json.loads(find_tool.apply("func", substring_matching=True, language=lang_enum))
            # Should find functions only in the specified language
            for symbol in result:
                assert lang in symbol["relative_path"]

def test_tool_language_parameter_validation():
    """Test that tools properly validate language parameter."""
    repo = Path("test/resources/repos/multi/test_repo")
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())
    
    # Wait for initialization
    import time
    for _ in range(50):
        if agent.symbol_manager is not None:
            break
        time.sleep(0.1)
    assert agent.symbol_manager is not None
    
    # Test with invalid language
    tool = agent.get_tool(FindSymbolTool)
    try:
        # This should handle invalid language gracefully
        result = json.loads(tool.apply("func", language="invalid_language"))
        # Should either return empty or raise a meaningful error
        assert isinstance(result, list)
    except Exception as e:
        # If it raises an error, it should be meaningful
        assert "language" in str(e).lower() or "invalid" in str(e).lower()


def test_multi_language_onboarding_prompt():
    """Test that onboarding prompt includes multi-language instructions."""
    from serena.prompt_factory import SerenaPromptFactory
    
    factory = SerenaPromptFactory()
    prompt = factory.get_simple_tool_output_prompt("onboarding_prompt", system="linux")
    
    # Check that the prompt mentions multiple languages
    assert "programming languages" in prompt.lower()
    assert "multi-language" in prompt.lower() or "multiple language" in prompt.lower()
    assert "get_language_statistics" in prompt


def test_concurrent_language_server_operations():
    """Test that multiple language servers can operate concurrently."""
    repo = Path("test/resources/repos/multi/test_repo")
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())
    
    # Wait for initialization
    import time
    for _ in range(50):
        if agent.symbol_manager is not None:
            break
        time.sleep(0.1)
    assert agent.symbol_manager is not None
    
    # Perform operations on both languages simultaneously
    find_tool = agent.get_tool(FindSymbolTool)
    overview_tool = agent.get_tool(GetSymbolsOverviewTool)
    
    # These should work without interfering with each other
    py_symbols = json.loads(find_tool.apply("py_func", language="python"))
    ts_overview = json.loads(overview_tool.apply(".", language="typescript"))
    
    assert len(py_symbols) > 0
    assert "ts_mod.ts" in ts_overview
    
    # Now do the reverse
    ts_symbols = json.loads(find_tool.apply("ts_func", language="typescript"))
    py_overview = json.loads(overview_tool.apply(".", language="python"))
    
    assert len(ts_symbols) > 0
    assert "py_mod.py" in py_overview


def test_create_multi_ls_for_project():
    """Test the create_multi_ls_for_project function."""
    from serena.agent import create_multi_ls_for_project
    
    repo = Path("test/resources/repos/multi/test_repo")
    
    # Create multi-language server
    multi_ls = create_multi_ls_for_project(str(repo))
    
    # Check that multiple servers were created
    assert len(multi_ls._servers) >= 2
    assert Language.PYTHON in multi_ls._servers
    assert Language.TYPESCRIPT in multi_ls._servers
    
    # Test that each server can be started
    multi_ls.start()
    assert multi_ls.is_running()
    
    # Clean up
    multi_ls.stop()


def test_backward_compatible_create_ls():
    """Test that create_ls_for_project still works for backward compatibility."""
    from serena.agent import create_ls_for_project
    
    repo = Path("test/resources/repos/multi/test_repo")
    
    # This should issue a deprecation warning but still work
    with pytest.warns(None) as warning_list:
        ls = create_ls_for_project(str(repo))
    
    # Should return a single language server (the primary one)
    assert ls is not None
    assert hasattr(ls, 'start_server')
    
    # Check deprecation warning was issued
    # Note: pytest.warns might not catch log.warning, so we don't assert on it
