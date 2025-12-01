"""Configuration for embedded languages handled by companion servers."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class EmbeddedLanguageConfig:
    """
    Configuration for an embedded language that requires a companion server.

    Loosely inspired by Volar.js VirtualCode concept - represents a language
    region within a host file format that requires a separate language server
    for full LSP support (definitions, references, rename, completions, etc.).

    This dataclass is used by CompanionLanguageServer to configure how companion
    servers should be created and which LSP operations they should handle.

    Attributes:
        language_id: Identifier for the language (e.g., "typescript", "css").
            This is used as a key in the companions dictionary.
        file_patterns: Glob patterns for files this companion should index
            (e.g., ["*.vue", "*.svelte"]). Used to determine which domain files
            should be opened on this companion for cross-file references.
        handles_definitions: Whether this companion handles go-to-definition requests.
        handles_references: Whether this companion handles find-references requests.
        handles_rename: Whether this companion handles rename requests.
        handles_completions: Whether this companion handles completion requests.
        handles_diagnostics: Whether this companion handles diagnostic requests.
        priority: Priority when multiple companions could handle an operation.
            Higher values indicate higher priority. Default is 0.

    """

    language_id: str
    file_patterns: list[str]
    handles_definitions: bool = False
    handles_references: bool = False
    handles_rename: bool = False
    handles_completions: bool = False
    handles_diagnostics: bool = False
    priority: int = 0
