"""Helpers for configuring TypeScript as a companion language server."""

from __future__ import annotations

from solidlsp import ls_types
from solidlsp.embedded_language_config import EmbeddedLanguageConfig


def create_typescript_companion_config(
    file_patterns: list[str],
    handles_definitions: bool = True,
    handles_references: bool = True,
    handles_rename: bool = True,
    handles_completions: bool = False,
    handles_diagnostics: bool = False,
    priority: int = 100,
) -> EmbeddedLanguageConfig:
    """
    Create standard TypeScript embedded language configuration.

    Args:
        file_patterns: Glob patterns for files to index (e.g., ["*.vue"]).
        handles_definitions: Handle go-to-definition requests.
        handles_references: Handle find-references requests.
        handles_rename: Handle rename requests.
        handles_completions: Handle completion requests.
        handles_diagnostics: Handle diagnostic requests.
        priority: Priority when multiple companions could handle an operation.

    Returns:
        Configured EmbeddedLanguageConfig for TypeScript.

    """
    return EmbeddedLanguageConfig(
        language_id="typescript",
        file_patterns=file_patterns,
        handles_definitions=handles_definitions,
        handles_references=handles_references,
        handles_rename=handles_rename,
        handles_completions=handles_completions,
        handles_diagnostics=handles_diagnostics,
        priority=priority,
    )


def prefer_non_node_modules_definition(
    definitions: list[ls_types.Location],
) -> ls_types.Location:
    """
    Select preferred definition, favoring source files over node_modules.

    Args:
        definitions: Non-empty list of definition locations.

    Returns:
        Preferred definition location (first non-node_modules, or first if all in node_modules).

    """
    for d in definitions:
        rel_path = d.get("relativePath", "")
        if rel_path and "node_modules" not in rel_path:
            return d
    return definitions[0]
