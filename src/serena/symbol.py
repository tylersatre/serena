import json
import logging
import os
from collections.abc import Iterable, Iterator, Reversible, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Self, Union

from sensai.util.string import ToStringMixin

from solidlsp.ls import ReferenceInSymbol as LSPReferenceInSymbol
from solidlsp.ls_config import Language
from solidlsp.ls_types import Position, SymbolKind, UnifiedSymbolInformation

if TYPE_CHECKING:
    from .agent import SerenaAgent
    from .multi_language_server import MultiLanguageServer

log = logging.getLogger(__name__)


class LineChange(NamedTuple):
    """Represents a change to a specific line or range of lines."""

    operation: Literal["insert", "delete", "replace"]
    original_start: int
    original_end: int
    modified_start: int
    modified_end: int
    original_lines: list[str]
    modified_lines: list[str]


@dataclass
class CodeDiff:
    """
    Represents the difference between original and modified code.
    Provides object-oriented access to diff information including line numbers.
    """

    relative_path: str
    original_content: str
    modified_content: str
    _line_changes: list[LineChange] = field(init=False)

    def __post_init__(self) -> None:
        """Compute the diff using difflib's SequenceMatcher."""
        original_lines = self.original_content.splitlines(keepends=True)
        modified_lines = self.modified_content.splitlines(keepends=True)

        matcher = SequenceMatcher(None, original_lines, modified_lines)
        self._line_changes = []

        for tag, orig_start, orig_end, mod_start, mod_end in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "insert":
                self._line_changes.append(
                    LineChange(
                        operation="insert",
                        original_start=orig_start,
                        original_end=orig_start,
                        modified_start=mod_start,
                        modified_end=mod_end,
                        original_lines=[],
                        modified_lines=modified_lines[mod_start:mod_end],
                    )
                )
            elif tag == "delete":
                self._line_changes.append(
                    LineChange(
                        operation="delete",
                        original_start=orig_start,
                        original_end=orig_end,
                        modified_start=mod_start,
                        modified_end=mod_start,
                        original_lines=original_lines[orig_start:orig_end],
                        modified_lines=[],
                    )
                )
            elif tag == "replace":
                self._line_changes.append(
                    LineChange(
                        operation="replace",
                        original_start=orig_start,
                        original_end=orig_end,
                        modified_start=mod_start,
                        modified_end=mod_end,
                        original_lines=original_lines[orig_start:orig_end],
                        modified_lines=modified_lines[mod_start:mod_end],
                    )
                )

    @property
    def line_changes(self) -> list[LineChange]:
        """Get all line changes in the diff."""
        return self._line_changes

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return len(self._line_changes) > 0

    @property
    def added_lines(self) -> list[tuple[int, str]]:
        """Get all added lines with their line numbers (0-based) in the modified file."""
        result = []
        for change in self._line_changes:
            if change.operation in ("insert", "replace"):
                for i, line in enumerate(change.modified_lines):
                    result.append((change.modified_start + i, line))
        return result

    @property
    def deleted_lines(self) -> list[tuple[int, str]]:
        """Get all deleted lines with their line numbers (0-based) in the original file."""
        result = []
        for change in self._line_changes:
            if change.operation in ("delete", "replace"):
                for i, line in enumerate(change.original_lines):
                    result.append((change.original_start + i, line))
        return result

    @property
    def modified_line_numbers(self) -> list[int]:
        """Get all line numbers (0-based) that were modified in the modified file."""
        line_nums: set[int] = set()
        for change in self._line_changes:
            if change.operation in ("insert", "replace"):
                line_nums.update(range(change.modified_start, change.modified_end))
        return sorted(line_nums)

    @property
    def affected_original_line_numbers(self) -> list[int]:
        """Get all line numbers (0-based) that were affected in the original file."""
        line_nums: set[int] = set()
        for change in self._line_changes:
            if change.operation in ("delete", "replace"):
                line_nums.update(range(change.original_start, change.original_end))
        return sorted(line_nums)

    def get_unified_diff(self, context_lines: int = 3) -> str:
        """Get the unified diff as a string."""
        import difflib

        original_lines = self.original_content.splitlines(keepends=True)
        modified_lines = self.modified_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines, modified_lines, fromfile=f"a/{self.relative_path}", tofile=f"b/{self.relative_path}", n=context_lines
        )
        return "".join(diff)

    def get_context_diff(self, context_lines: int = 3) -> str:
        """Get the context diff as a string."""
        import difflib

        original_lines = self.original_content.splitlines(keepends=True)
        modified_lines = self.modified_content.splitlines(keepends=True)

        diff = difflib.context_diff(
            original_lines, modified_lines, fromfile=f"a/{self.relative_path}", tofile=f"b/{self.relative_path}", n=context_lines
        )
        return "".join(diff)


@dataclass
class SymbolLocation:
    """
    Represents the (start) location of a symbol identifier, which, within Serena, uniquely identifies the symbol.
    """

    relative_path: str | None
    """
    the relative path of the file containing the symbol; if None, the symbol is defined outside of the project's scope
    """
    line: int | None
    """
    the line number in which the symbol identifier is defined (if the symbol is a function, class, etc.);
    may be None for some types of symbols (e.g. SymbolKind.File)
    """
    column: int | None
    """
    the column number in which the symbol identifier is defined (if the symbol is a function, class, etc.);
    may be None for some types of symbols (e.g. SymbolKind.File)
    """

    def __post_init__(self) -> None:
        if self.relative_path is not None:
            self.relative_path = self.relative_path.replace("/", os.path.sep)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def has_position_in_file(self) -> bool:
        return self.relative_path is not None and self.line is not None and self.column is not None


class Symbol(ToStringMixin):
    _NAME_PATH_SEP = "/"

    @staticmethod
    def match_name_path(
        name_path: str,
        symbol_name_path_parts: list[str],
        substring_matching: bool,
    ) -> bool:
        """
        Checks if a given `name_path` matches a symbol's qualified name parts.
        See docstring of `Symbol.find` for more details.
        """
        assert name_path, "name_path must not be empty"
        assert symbol_name_path_parts, "symbol_name_path_parts must not be empty"
        name_path_sep = Symbol._NAME_PATH_SEP

        is_absolute_pattern = name_path.startswith(name_path_sep)
        pattern_parts = name_path.lstrip(name_path_sep).rstrip(name_path_sep).split(name_path_sep)

        # filtering based on ancestors
        if len(pattern_parts) > len(symbol_name_path_parts):
            # can't possibly match if pattern has more parts than symbol
            return False
        if is_absolute_pattern and len(pattern_parts) != len(symbol_name_path_parts):
            # for absolute patterns, the number of parts must match exactly
            return False
        if symbol_name_path_parts[-len(pattern_parts) : -1] != pattern_parts[:-1]:
            # ancestors must match
            return False

        # matching the last part of the symbol name
        name_to_match = pattern_parts[-1]
        symbol_name = symbol_name_path_parts[-1]
        if substring_matching:
            return name_to_match in symbol_name
        else:
            return name_to_match == symbol_name

    def __init__(self, symbol_root_from_ls: UnifiedSymbolInformation) -> None:
        self.symbol_root = symbol_root_from_ls

    def _tostring_includes(self) -> list[str]:
        return []

    def _tostring_additional_entries(self) -> dict[str, Any]:
        return dict(name=self.name, kind=self.kind, num_children=len(self.symbol_root["children"]))

    @property
    def name(self) -> str:
        return self.symbol_root["name"]

    @property
    def kind(self) -> str:
        return SymbolKind(self.symbol_kind).name

    @property
    def symbol_kind(self) -> SymbolKind:
        return self.symbol_root["kind"]

    def is_neighbouring_definition_separated_by_empty_line(self) -> bool:
        """
        :return: whether a symbol definition of this symbol's kind is usually separated from the
            previous/next definition by at least one empty line.
        """
        return self.symbol_kind in (SymbolKind.Function, SymbolKind.Method, SymbolKind.Class, SymbolKind.Interface, SymbolKind.Struct)

    @property
    def relative_path(self) -> str | None:
        location = self.symbol_root.get("location")
        if location:
            return location.get("relativePath")
        return None

    @property
    def location(self) -> SymbolLocation:
        """
        :return: the start location of the actual symbol identifier
        """
        return SymbolLocation(relative_path=self.relative_path, line=self.line, column=self.column)

    @property
    def body_start_position(self) -> Position | None:
        location = self.symbol_root.get("location")
        if location:
            range_info = location.get("range")
            if range_info:
                start_pos = range_info.get("start")
                if start_pos:
                    return start_pos
        return None

    @property
    def body_end_position(self) -> Position | None:
        location = self.symbol_root.get("location")
        if location:
            range_info = location.get("range")
            if range_info:
                end_pos = range_info.get("end")
                if end_pos:
                    return end_pos
        return None

    def get_body_line_numbers(self) -> tuple[int | None, int | None]:
        start_pos = self.body_start_position
        end_pos = self.body_end_position
        start_line = start_pos["line"] if start_pos else None
        end_line = end_pos["line"] if end_pos else None
        return start_line, end_line

    @property
    def line(self) -> int | None:
        """
        :return: the line in which the symbol identifier is defined.
        """
        if "selectionRange" in self.symbol_root:
            return self.symbol_root["selectionRange"]["start"]["line"]
        else:
            # line is expected to be undefined for some types of symbols (e.g. SymbolKind.File)
            return None

    @property
    def column(self) -> int | None:
        if "selectionRange" in self.symbol_root:
            return self.symbol_root["selectionRange"]["start"]["character"]
        else:
            # precise location is expected to be undefined for some types of symbols (e.g. SymbolKind.File)
            return None

    @property
    def body(self) -> str | None:
        return self.symbol_root.get("body")

    def get_name_path(self) -> str:
        """
        Get the name path of the symbol (e.g. "class/method/inner_function").
        """
        return self._NAME_PATH_SEP.join(self.get_name_path_parts())

    def get_name_path_parts(self) -> list[str]:
        """
        Get the parts of the name path of the symbol (e.g. ["class", "method", "inner_function"]).
        """
        ancestors_within_file = list(self.iter_ancestors(up_to_symbol_kind=SymbolKind.File))
        ancestors_within_file.reverse()
        return [a.name for a in ancestors_within_file] + [self.name]

    def iter_children(self) -> Iterator[Self]:
        for c in self.symbol_root["children"]:
            yield self.__class__(c)

    def iter_ancestors(self, up_to_symbol_kind: SymbolKind | None = None) -> Iterator[Self]:
        """
        Iterate over all ancestors of the symbol, starting with the parent and going up to the root or
        the given symbol kind.

        :param up_to_symbol_kind: if provided, iteration will stop *before* the first ancestor of the given kind.
            A typical use case is to pass `SymbolKind.File` or `SymbolKind.Package`.
        """
        parent = self.get_parent()
        if parent is not None:
            if up_to_symbol_kind is None or parent.symbol_kind != up_to_symbol_kind:
                yield parent
                yield from parent.iter_ancestors(up_to_symbol_kind=up_to_symbol_kind)

    def get_parent(self) -> Self | None:
        parent_root = self.symbol_root.get("parent")
        if parent_root is None:
            return None
        return self.__class__(parent_root)

    def find(
        self,
        name_path: str,
        substring_matching: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
    ) -> list[Self]:
        """
        Find all symbols within the symbol's subtree that match the given `name_path`.
        The matching behavior is determined by the structure of `name_path`, which can
        either be a simple name (e.g. "method") or a name path like "class/method" (relative name path)
        or "/class/method" (absolute name path).

        Key aspects of the name path matching behavior:
        - Trailing slashes in `name_path` play no role and are ignored.
        - The name of the retrieved symbols will match (either exactly or as a substring)
          the last segment of `name_path`, while other segments will restrict the search to symbols that
          have a desired sequence of ancestors.
        - If there is no starting or intermediate slash in `name_path`, there is no
          restriction on the ancestor symbols. For example, passing `method` will match
          against symbols with name paths like `method`, `class/method`, `class/nested_class/method`, etc.
        - If `name_path` contains a `/` but doesn't start with a `/`, the matching is restricted to symbols
          with the same ancestors as the last segment of `name_path`. For example, passing `class/method` will match against
          `class/method` as well as `nested_class/class/method` but not `method`.
        - If `name_path` starts with a `/`, it will be treated as an absolute name path pattern, meaning
          that the first segment of it must match the first segment of the symbol's name path.
          For example, passing `/class` will match only against top-level symbols like `class` but not against `nested_class/class`.
          Passing `/class/method` will match against `class/method` but not `nested_class/class/method` or `method`.

        :param name_path: the name path to match against
        :param substring_matching: whether to use substring matching (as opposed to exact matching)
            of the last segment of `name_path` against the symbol name.
        :param include_kinds: an optional sequence of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
        """
        result = []

        def should_include(s: "Symbol") -> bool:
            if include_kinds is not None and s.symbol_kind not in include_kinds:
                return False
            if exclude_kinds is not None and s.symbol_kind in exclude_kinds:
                return False
            return Symbol.match_name_path(
                name_path=name_path,
                symbol_name_path_parts=s.get_name_path_parts(),
                substring_matching=substring_matching,
            )

        def traverse(s: "Symbol") -> None:
            if should_include(s):
                result.append(s)
            for c in s.iter_children():
                traverse(c)

        traverse(self)
        return result

    def to_dict(
        self, kind: bool = False, location: bool = False, depth: int = 0, include_body: bool = False, include_children_body: bool = False
    ) -> dict[str, Any]:
        """
        Converts the symbol to a dictionary.

        :param kind: whether to include the kind of the symbol
        :param location: whether to include the location of the symbol
        :param depth: the depth of the symbol
        :param include_body: whether to include the body of the top-level symbol.
        :param include_children_body: whether to also include the body of the children.
            Note that the body of the children is part of the body of the parent symbol,
            so there is usually no need to set this to True unless you want process the output
            and pass the children without passing the parent body to the LM.
        :return: a dictionary representation of the symbol
        """
        result: dict[str, Any] = {"name": self.name, "name_path": self.get_name_path()}

        if kind:
            result["kind"] = self.kind

        if location:
            result["location"] = self.location.to_dict()
            body_start_line, body_end_line = self.get_body_line_numbers()
            result["body_location"] = {"start_line": body_start_line, "end_line": body_end_line}

        if include_body:
            if self.body is None:
                log.warning("Requested body for symbol, but it is not present. The symbol might have been loaded with include_body=False.")
            result["body"] = self.body

        def add_children(s: Self) -> list[dict[str, Any]]:
            children = []
            for c in s.iter_children():
                children.append(
                    c.to_dict(
                        kind=kind,
                        location=location,
                        depth=depth - 1,
                        include_body=include_children_body,
                        include_children_body=include_children_body,
                    )
                )
            return children

        if depth > 0:
            result["children"] = add_children(self)

        return result


@dataclass
class ReferenceInSymbol(ToStringMixin):
    """Same as the class of the same name in the language server, but using Serena's Symbol class.
    Be careful to not confuse it with counterpart!
    """

    symbol: Symbol
    line: int
    character: int

    def get_relative_path(self) -> str | None:
        return self.symbol.location.relative_path

    @classmethod
    def from_lsp_reference(cls, reference: LSPReferenceInSymbol) -> Self:
        return cls(symbol=Symbol(reference.symbol), line=reference.line, character=reference.character)


from serena.multi_language_server import MultiLanguageServer


class SymbolManager:
    def __init__(self, lang_server: MultiLanguageServer, agent: Union["SerenaAgent", None] = None) -> None:
        """
        :param lang_server: the language server to use for symbol retrieval as well as editing operations.
        :param agent: the agent to use (only needed for marking files as modified). You can pass None if you don't
            need an agent to be aware of file modifications performed by the symbol manager.
        """
        self._lang_server = lang_server
        self.agent = agent

    def find_by_name(
        self,
        name_path: str,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
        substring_matching: bool = False,
        within_relative_path: str | None = None,
        *,
        language: Language | None = None,
    ) -> list[Symbol]:
        """
        Find all symbols that match the given name. See docstring of `Symbol.find` for more details.
        The only parameter not mentioned there is `within_relative_path`, which can be used to restrict the search
        to symbols within a specific file or directory.
        """
        log.debug(
            "SymbolManager.find_by_name: Searching for '%s' (path: %s, language: %s, substring: %s)",
            name_path,
            within_relative_path or "all",
            language.value if language else "all",
            substring_matching,
        )

        symbols: list[Symbol] = []
        symbol_roots = self._lang_server.request_full_symbol_tree(
            within_relative_path=within_relative_path, include_body=include_body, language=language
        )

        log.debug("SymbolManager.find_by_name: Got %d symbol roots to search", len(symbol_roots))

        for root in symbol_roots:
            matching_symbols = Symbol(root).find(
                name_path, include_kinds=include_kinds, exclude_kinds=exclude_kinds, substring_matching=substring_matching
            )
            if matching_symbols:
                log.debug("Found %d matches in %s", len(matching_symbols), root.get("location", {}).get("relativePath", "unknown"))
            symbols.extend(matching_symbols)

        log.debug("SymbolManager.find_by_name: Total symbols found: %d", len(symbols))
        return symbols

    def get_document_symbols(self, relative_path: str) -> list[Symbol]:
        symbol_dicts, roots = self._lang_server.request_document_symbols(relative_path, include_body=False)
        symbols = [Symbol(s) for s in symbol_dicts]
        return symbols

    def find_by_location(self, location: SymbolLocation) -> Symbol | None:
        if location.relative_path is None:
            return None
        symbol_dicts, roots = self._lang_server.request_document_symbols(location.relative_path, include_body=False)
        for symbol_dict in symbol_dicts:
            symbol = Symbol(symbol_dict)
            if symbol.location == location:
                return symbol
        return None

    def find_referencing_symbols(
        self,
        name_path: str,
        relative_file_path: str,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
        language: Language | None = None,
    ) -> list[ReferenceInSymbol]:
        """
        Find all symbols that reference the symbol with the given name.
        If multiple symbols fit the name (e.g. for variables that are overwritten), will use the first one.

        :param name_path: the name path of the symbol to find
        :param relative_file_path: the relative path of the file in which the referenced symbol is defined.
        :param include_body: whether to include the body of all symbols in the result.
            Not recommended, as the referencing symbols will often be files, and thus the bodies will be very long.
        :param include_kinds: which kinds of symbols to include in the result.
        :param exclude_kinds: which kinds of symbols to exclude from the result.
        :param language: optional language filter to only include references from files of that language.
        """
        log.debug(
            "SymbolManager.find_referencing_symbols: Searching references for '%s' in %s (language filter: %s)",
            name_path,
            relative_file_path,
            language.value if language else "none",
        )

        symbol_candidates = self.find_by_name(name_path, substring_matching=False, within_relative_path=relative_file_path)
        if len(symbol_candidates) == 0:
            log.warning(f"No symbol with name {name_path} found in file {relative_file_path}")
            return []
        if len(symbol_candidates) > 1:
            log.error(
                f"Found {len(symbol_candidates)} symbols with name {name_path} in file {relative_file_path}."
                f"May be an overwritten variable, in which case you can ignore this error. Proceeding with the first one. "
                f"Found symbols for {name_path=} in {relative_file_path=}: \n"
                f"{json.dumps([s.location.to_dict() for s in symbol_candidates], indent=2)}"
            )
        symbol = symbol_candidates[0]
        log.debug("Found symbol at %s:%s:%s", symbol.location.relative_path, symbol.location.line, symbol.location.column)

        return self.find_referencing_symbols_by_location(
            symbol.location, include_body=include_body, include_kinds=include_kinds, exclude_kinds=exclude_kinds, language=language
        )

    def find_referencing_symbols_by_location(
        self,
        symbol_location: SymbolLocation,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
        language: Language | None = None,
    ) -> list[ReferenceInSymbol]:
        """
        Find all symbols that reference the symbol at the given location.

        :param symbol_location: the location of the symbol for which to find references.
            Does not need to include an end_line, as it is unused in the search.
        :param include_body: whether to include the body of all symbols in the result.
            Not recommended, as the referencing symbols will often be files, and thus the bodies will be very long.
            Note: you can filter out the bodies of the children if you set include_children_body=False
            in the to_dict method.
        :param include_kinds: an optional sequence of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
            Takes precedence over include_kinds.
        :param language: optional language filter to only include references from files of that language.
        :return: a list of symbols that reference the given symbol
        """
        log.debug(
            "SymbolManager.find_referencing_symbols_by_location: Searching references at %s:%s:%s (language filter: %s)",
            symbol_location.relative_path,
            symbol_location.line,
            symbol_location.column,
            language.value if language else "none",
        )

        if not symbol_location.has_position_in_file():
            raise ValueError("Symbol location does not contain a valid position in a file")
        assert symbol_location.relative_path is not None
        assert symbol_location.line is not None
        assert symbol_location.column is not None

        references = self._lang_server.request_referencing_symbols(
            relative_file_path=symbol_location.relative_path,
            line=symbol_location.line,
            column=symbol_location.column,
            include_imports=False,
            include_self=False,
            include_body=include_body,
            include_file_symbols=True,
            language=language,
        )

        log.debug("Found %d total references before filtering", len(references))

        if include_kinds is not None:
            references = [s for s in references if s.symbol["kind"] in include_kinds]
            log.debug("After include_kinds filter: %d references", len(references))

        if exclude_kinds is not None:
            references = [s for s in references if s.symbol["kind"] not in exclude_kinds]
            log.debug("After exclude_kinds filter: %d references", len(references))

        result = [ReferenceInSymbol.from_lsp_reference(r) for r in references]
        log.debug("SymbolManager.find_referencing_symbols_by_location: Returning %d references", len(result))
        return result

    @contextmanager
    def _edited_file(self, relative_path: str) -> Iterator[None]:
        with self._lang_server.open_file(relative_path) as file_buffer:
            yield
            root_path = self._lang_server.repository_root_path
            abs_path = os.path.join(root_path, relative_path)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(file_buffer.contents)
            if self.agent is not None:
                self.agent.mark_file_modified(relative_path)

    @contextmanager
    def _edited_symbol_location(self, location: SymbolLocation) -> Iterator[Symbol]:
        """
        Context manager for locating and editing a symbol in a file.
        """
        symbol = self.find_by_location(location)
        if symbol is None:
            raise ValueError("Symbol not found/has no defined location within a file")
        assert location.relative_path is not None
        with self._edited_file(location.relative_path):
            yield symbol

    def _get_code_file_content(self, relative_path: str) -> str:
        """Get the content of a file using the language server."""
        return self._lang_server.retrieve_full_file_content(relative_path)

    def replace_body(self, name_path: str, relative_file_path: str, body: str, *, use_same_indentation: bool = True) -> None:
        """
        Replace the body of the symbol with the given name_path in the given file.

        :param name_path: the name path of the symbol to replace.
        :param relative_file_path: the relative path of the file in which the symbol is defined.
        :param body: the new body
        :param use_same_indentation: whether to use the same indentation as the original body. This means that
            the user doesn't have to provide the correct indentation, but can just write the body.
        """
        symbol_candidates = self.find_by_name(name_path, within_relative_path=relative_file_path)
        if len(symbol_candidates) == 0:
            raise ValueError(f"No symbol with name {name_path} found in file {relative_file_path}")
        if len(symbol_candidates) > 1:
            raise ValueError(
                f"Found multiple {len(symbol_candidates)} symbols with name {name_path} in file {relative_file_path}. "
                "Will not replace the body of any of them, but you can use `replace_body_at_location`, the replace lines tool or other editing "
                "tools to perform your edits. Their locations are: \n "
                + json.dumps([s.location.to_dict() for s in symbol_candidates], indent=2)
            )
        symbol = symbol_candidates[0]
        return self.replace_body_at_location(symbol.location, body, use_same_indentation=use_same_indentation)

    def replace_body_at_location(self, location: SymbolLocation, body: str, *, use_same_indentation: bool = True) -> None:
        """
        Replace the body of the symbol at the given location with the given body

        :param location: the location of the symbol to replace.
        :param body: the new body
        :param use_same_indentation: whether to use the same indentation as the original body. This means that
            the user doesn't have to provide the correct indentation, but can just write the body.
        """
        with self._edited_symbol_location(location) as symbol:
            assert location.relative_path is not None
            start_pos = symbol.body_start_position
            end_pos = symbol.body_end_position
            if start_pos is None or end_pos is None:
                raise ValueError(f"Symbol at {location} does not have a defined body range.")
            start_line, start_col = start_pos["line"], start_pos["character"]

            if use_same_indentation:
                indent = " " * start_col
                body_lines = body.splitlines()
                body = body_lines[0] + "\n" + "\n".join(indent + line for line in body_lines[1:])

            # make sure the replacement adds no additional newlines (before or after) - all newlines
            # and whitespace before/after should remain the same, so we strip it entirely
            body = body.strip()

            self._lang_server.delete_text_between_positions(location.relative_path, start_pos, end_pos)
            self._lang_server.insert_text_at_position(location.relative_path, start_line, start_col, body)

    @staticmethod
    def _count_leading_newlines(text: Iterable) -> int:
        cnt = 0
        for c in text:
            if c == "\n":
                cnt += 1
            elif c == "\r":
                continue
            else:
                break
        return cnt

    @classmethod
    def _count_trailing_newlines(cls, text: Reversible) -> int:
        return cls._count_leading_newlines(reversed(text))

    def insert_after_symbol(self, name_path: str, relative_file_path: str, body: str, *, use_same_indentation: bool = True) -> None:
        """
        Inserts content after the symbol with the given name in the given file.
        """
        symbol_candidates = self.find_by_name(name_path, within_relative_path=relative_file_path)
        if len(symbol_candidates) == 0:
            raise ValueError(f"No symbol with name {name_path} found in file {relative_file_path}")
        if len(symbol_candidates) > 1:
            raise ValueError(
                f"Found multiple {len(symbol_candidates)} symbols with name {name_path} in file {relative_file_path}. "
                f"May be an overwritten variable, in which case you can ignore this error. Proceeding with the last one. "
                f"Found symbols at locations: \n" + json.dumps([s.location.to_dict() for s in symbol_candidates], indent=2)
            )
        symbol = symbol_candidates[-1]
        return self.insert_after_symbol_at_location(symbol.location, body, use_same_indentation=use_same_indentation)

    def insert_after_symbol_at_location(self, location: SymbolLocation, body: str, *, use_same_indentation: bool = True) -> None:
        """
        Appends content after the given symbol

        :param location: the location of the symbol after which to add new lines
        :param body: the body of the entity to append
        """
        # make sure body always ends with at least one newline
        if not body.endswith("\n"):
            body += "\n"

        assert location.relative_path is not None

        # Find the symbol to get its end position
        symbol = self.find_by_location(location)
        if symbol is None:
            raise ValueError("Symbol not found/has no defined location within a file")

        pos = symbol.body_end_position
        if pos is None:
            raise ValueError(f"Symbol at {location} does not have a defined end position.")

        # start at the beginning of the next line
        col = 0
        line = pos["line"] + 1
        # make sure a suitable number of leading empty lines is used (at least 0/1 depending on the symbol type,
        # otherwise as many as the caller wanted to insert)
        original_leading_newlines = self._count_leading_newlines(body)
        body = body.lstrip("\r\n")
        min_empty_lines = 0
        if symbol.is_neighbouring_definition_separated_by_empty_line():
            min_empty_lines = 1
        num_leading_empty_lines = max(min_empty_lines, original_leading_newlines)
        if num_leading_empty_lines:
            body = ("\n" * num_leading_empty_lines) + body
        # make sure the one line break succeeding the original symbol, which we repurposed as prefix via
        # `line += 1`, is replaced
        body = body.rstrip("\r\n") + "\n"

        if use_same_indentation:
            symbol_start_pos = symbol.body_start_position
            assert symbol_start_pos is not None, f"Symbol at {location=} does not have a defined start position."
            symbol_identifier_col = symbol_start_pos["character"]
            indent = " " * (symbol_identifier_col)
            body = "\n".join(indent + line for line in body.splitlines())
            # IMPORTANT: without this, the insertion does the wrong thing. See implementation of insert_text_at_position in TextUtils,
            # it is somewhat counterintuitive (never inserts whitespace)
            # I am not 100% sure whether col=0 is always the best choice here.
            #
            # Without col=0, inserting after dataclass_instance in variables.py:
            # > dataclass_instance = VariableDataclass(id=1, name="Test")
            # > test test
            # > dataclass_instancetest test
            # > second line
            # > .status = "active"  # Reassign dataclass field
            #
            # With col=0:
            # > dataclass_instance = VariableDataclass(id=1, name="Test")
            # > test test
            # > second line
            # > dataclass_instance.status = "active"  # Reassign dataclass field

        with self._edited_symbol_location(location):
            self._lang_server.insert_text_at_position(location.relative_path, line=line, column=col, text_to_be_inserted=body)

    def insert_before_symbol(self, name_path: str, relative_file_path: str, body: str, *, use_same_indentation: bool = True) -> None:
        """
        Inserts content before the symbol with the given name in the given file.
        """
        symbol_candidates = self.find_by_name(name_path, within_relative_path=relative_file_path)
        if len(symbol_candidates) == 0:
            raise ValueError(f"No symbol with name {name_path} found in file {relative_file_path}")
        if len(symbol_candidates) > 1:
            raise ValueError(
                f"Found multiple {len(symbol_candidates)} symbols with name {name_path} in file {relative_file_path}. "
                f"May be an overwritten variable, in which case you can ignore this error. Proceeding with the first one. "
                f"Found symbols at locations: \n" + json.dumps([s.location.to_dict() for s in symbol_candidates], indent=2)
            )
        symbol = symbol_candidates[0]
        self.insert_before_symbol_at_location(symbol.location, body, use_same_indentation=use_same_indentation)

    def insert_before_symbol_at_location(self, location: SymbolLocation, body: str, *, use_same_indentation: bool = True) -> None:
        """
        Inserts content before the given symbol

        :param location: the location of the symbol before which to add new lines
        :param body: the body of the entity to insert
        """
        with self._edited_symbol_location(location) as symbol:
            symbol_start_pos = symbol.body_start_position
            if symbol_start_pos is None:
                raise ValueError(f"Symbol at {location} does not have a defined start position.")

            if use_same_indentation:
                indent = " " * (symbol_start_pos["character"])
                body = "\n".join(indent + line for line in body.splitlines())

            # insert position is the start of line where the symbol is defined
            line = symbol_start_pos["line"]
            col = 0

            original_trailing_empty_lines = self._count_trailing_newlines(body) - 1

            # ensure eol is present at end
            body = body.rstrip() + "\n"

            # add suitable number of trailing empty lines after the body (at least 0/1 depending on the symbol type,
            # otherwise as many as the caller wanted to insert)
            min_trailing_empty_lines = 0
            if symbol.is_neighbouring_definition_separated_by_empty_line():
                min_trailing_empty_lines = 1
            num_trailing_newlines = max(min_trailing_empty_lines, original_trailing_empty_lines)
            body += "\n" * num_trailing_newlines

            assert location.relative_path is not None

            self._lang_server.insert_text_at_position(location.relative_path, line=line, column=col, text_to_be_inserted=body)

    def insert_at_line(self, relative_path: str, line: int, content: str) -> None:
        """
        Inserts content at the given line in the given file.

        :param line: the 0-based index of the line to insert content at
        :param content: the content to insert
        """
        with self._edited_file(relative_path):
            self._lang_server.insert_text_at_position(relative_path, line, 0, content)

    def delete_lines(self, relative_path: str, start_line: int, end_line: int) -> None:
        """
        Deletes lines in the given file.

        :param start_line: the 0-based index of the first line to delete (inclusive)
        :param end_line: the 0-based index of the last line to delete (inclusive)
        """
        start_col = 0
        end_line_for_delete = end_line + 1
        end_col = 0
        with self._edited_file(relative_path):
            start_pos = Position(line=start_line, character=start_col)
            end_pos = Position(line=end_line_for_delete, character=end_col)
            self._lang_server.delete_text_between_positions(relative_path, start_pos, end_pos)

    def delete_symbol_at_location(self, location: SymbolLocation) -> None:
        """
        Deletes the symbol at the given location.
        """
        with self._edited_symbol_location(location) as symbol:
            assert location.relative_path is not None
            assert symbol.body_start_position is not None
            assert symbol.body_end_position is not None
            self._lang_server.delete_text_between_positions(location.relative_path, symbol.body_start_position, symbol.body_end_position)

    def delete_symbol(self, name_path: str, relative_file_path: str) -> None:
        """
        Deletes the symbol with the given name in the given file.
        """
        symbol_candidates = self.find_by_name(name_path, within_relative_path=relative_file_path)
        if len(symbol_candidates) == 0:
            raise ValueError(f"No symbol with name {name_path} found in file {relative_file_path}")
        if len(symbol_candidates) > 1:
            raise ValueError(
                f"Found multiple {len(symbol_candidates)} symbols with name {name_path} in file {relative_file_path}. "
                "Will not delete any of them, but you can use `delete_symbol_at_location` or a corresponding tool to perform your edits. "
                "Their locations are: \n " + json.dumps([s.location.to_dict() for s in symbol_candidates], indent=2)
            )
        symbol = symbol_candidates[0]
        self.delete_symbol_at_location(symbol.location)
