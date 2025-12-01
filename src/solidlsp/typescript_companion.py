"""Helpers for TypeScript companion server configuration.

This module provides utility functions for configuring TypeScript as a companion
language server. TypeScript is the most common companion server for modern web
frameworks like Vue, Svelte, and Astro.
"""

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
    Create a standard TypeScript embedded language configuration.

    This is a convenience function for creating EmbeddedLanguageConfig instances
    for TypeScript companion servers. TypeScript is typically configured to handle
    definitions, references, and rename operations by default.

    Args:
        file_patterns: Glob patterns for files to index (e.g., ["*.vue", "*.svelte"]).
            These patterns determine which domain files should be opened on the
            TypeScript server for cross-file reference support.
        handles_definitions: Whether the TypeScript server handles go-to-definition
            requests. Defaults to True.
        handles_references: Whether the TypeScript server handles find-references
            requests. Defaults to True.
        handles_rename: Whether the TypeScript server handles rename requests.
            Defaults to True.
        handles_completions: Whether the TypeScript server handles completion
            requests. Defaults to False (often handled by domain server).
        handles_diagnostics: Whether the TypeScript server handles diagnostic
            requests. Defaults to False (often handled by domain server).
        priority: Priority for this companion when multiple could handle an
            operation. Defaults to 100 (high priority).

    Returns:
        A configured EmbeddedLanguageConfig instance for TypeScript.

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
    Select the preferred definition, preferring source files over type definitions.

    TypeScript language servers often return both type definitions (.d.ts files
    in node_modules) and source definitions. This function prefers:
    1. Files not in node_modules
    2. Falls back to first definition if all are in node_modules

    This function should be used in _get_preferred_definition() overrides for
    language servers that use TypeScript companions.

    Args:
        definitions: A non-empty list of definition locations.

    Returns:
        The preferred definition location.

    """
    for d in definitions:
        rel_path = d.get("relativePath", "")
        if rel_path and "node_modules" not in rel_path:
            return d
    return definitions[0]
