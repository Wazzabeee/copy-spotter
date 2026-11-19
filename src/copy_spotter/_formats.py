"""Readers for markup formats: Markdown, HTML, RTF and Jupyter notebooks.

Every reader takes the file content as bytes and returns plain text, using the standard library only, so they
also run in the browser (Pyodide). Markup is removed but the visible text keeps its line and paragraph breaks.
"""

from __future__ import annotations

import codecs
import json
import re
from html.parser import HTMLParser
from typing import Any

# Encodings tried in order for text files. cp1252 is a superset of latin-1 for printable characters and is
# what most Windows editors produce; latin-1 never fails and acts as last resort.
TXT_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def decode_text(data: bytes, encoding: str | None = None) -> str:
    """Decode ``data`` with ``encoding`` if it is known and works, else with the first encoding that works.

    A byte order mark always wins. UTF-8 is tried first, then cp1252 (what most Windows editors produce),
    then latin-1, which decodes any byte sequence.
    """
    for bom, name in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if data.startswith(bom):
            return data.decode(name)
    candidates = TXT_ENCODINGS if encoding is None else (encoding, *TXT_ENCODINGS)
    for candidate in candidates:
        try:
            return data.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    raise AssertionError("unreachable: latin-1 decodes any byte sequence")  # pragma: no cover


# Markdown ------------------------------------------------------------------------------------------------------

_MD_RULES = (
    (re.compile(r"<!--.*?-->", re.DOTALL), ""),  # comments
    (re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*\S.*$", re.MULTILINE), ""),  # reference link definitions
    (re.compile(r"!\[([^\]\n]*)\]\([^)\n]*\)"), r"\1"),  # images: keep the alt text
    (re.compile(r"\[([^\]\n]*)\]\([^)\n]*\)"), r"\1"),  # inline links: keep the link text
    (re.compile(r"\[([^\]\n]*)\]\[[^\]\n]*\]"), r"\1"),  # reference links
    (re.compile(r"<(?:https?|ftp|mailto):[^>\s]*>"), ""),  # autolinks
    (re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>"), ""),  # inline HTML tags
    # Underscore emphasis (_word_, __word__): "_" is a word character, so it would stick to the word.
    # Underscores inside a word (snake_case) are kept.
    (re.compile(r"(?<!\w)_{1,3}(?=\w)|(?<=\w)_{1,3}(?!\w)"), ""),
)


def markdown_to_text(source: str) -> str:
    """Remove the Markdown syntax that would add or glue words: link targets, inline HTML, ``_`` emphasis.

    Headings, lists, emphasis with ``*`` and code stay as written: their marks are not words, so they never
    change the matching, and they keep the text readable in the report.
    """
    for pattern, replacement in _MD_RULES:
        source = pattern.sub(replacement, source)
    return source


def read_markdown(data: bytes) -> str:
    """Return the text of a Markdown file without link targets, inline HTML and ``_`` emphasis marks."""
    return markdown_to_text(decode_text(data))


# HTML ----------------------------------------------------------------------------------------------------------

_HTML_SKIPPED = frozenset({"script", "style", "template", "noscript", "title", "svg", "iframe", "object", "canvas"})
_HTML_BLOCKS = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "caption", "dd", "details", "div", "dl", "dt",
        "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
        "li", "main", "nav", "ol", "p", "pre", "section", "summary", "table", "tr", "ul",
    }
)  # fmt: skip
_HTML_CELLS = frozenset({"td", "th"})
_HTML_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"})
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
_SPACES_RE = re.compile(r"\s+")


class _VisibleText(HTMLParser):
    """Collect the text a browser shows: no scripts, styles or head, line breaks at block elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipped = 0  # depth inside elements whose content is not shown
        self._pre = 0  # depth inside <pre>, where white space is kept

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HTML_SKIPPED:
            self._skipped += 1
        elif tag in _HTML_BLOCKS:
            self.parts.append("\n")
        elif tag in _HTML_CELLS:
            self.parts.append(" ")
        if tag == "pre":
            self._pre += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <br/>, <img/>, and self-closed elements such as <svg/>: nothing to skip inside them.
        if tag in _HTML_BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HTML_SKIPPED:
            self._skipped = max(self._skipped - 1, 0)
        elif tag in _HTML_BLOCKS and tag not in _HTML_VOID:
            self.parts.append("\n")
        if tag == "pre":
            self._pre = max(self._pre - 1, 0)

    def handle_data(self, data: str) -> None:
        if self._skipped:
            return
        self.parts.append(data if self._pre else _SPACES_RE.sub(" ", data))

    def text(self) -> str:
        lines = "".join(self.parts).split("\n")
        return "\n".join(line.strip(" ") for line in lines)


def html_to_text(source: str) -> str:
    """Return the visible text of an HTML document, one line per block element (paragraph, heading, item...)."""
    parser = _VisibleText()
    parser.feed(source)
    parser.close()
    return parser.text()


def read_html(data: bytes) -> str:
    """Return the visible text of an HTML file, decoded with the charset it declares (UTF-8 by default)."""
    declared = _META_CHARSET_RE.search(data[:4096])
    return html_to_text(decode_text(data, declared.group(1).decode("ascii") if declared else None))


# RTF -----------------------------------------------------------------------------------------------------------

# Destinations whose text is not part of the document body: tables, metadata, pictures, field codes...
_RTF_SKIPPED = frozenset(
    {
        "author", "bkmkend", "bkmkstart", "buptim", "colortbl", "comment", "company", "creatim", "datastore",
        "doccomm", "fldinst", "fonttbl", "footer", "footerf", "footerl", "footerr", "generator", "header",
        "headerf", "headerl", "headerr", "info", "keywords", "latentstyles", "listoverridetable", "listtable",
        "object", "operator", "pict", "printim", "revtbl", "revtim", "rsidtbl", "stylesheet", "subject",
        "themedata", "title", "colorschememapping", "xmlnstbl", "filetbl", "pgdsctbl", "mmathPr",
    }
)  # fmt: skip
_RTF_TEXT = {
    "par": "\n", "line": "\n", "sect": "\n\n", "page": "\n\n", "row": "\n", "cell": " ", "tab": "\t",
    "emdash": "\u2014", "endash": "\u2013", "emspace": " ", "enspace": " ", "qmspace": " ", "bullet": "\u2022",
    "lquote": "\u2018", "rquote": "\u2019", "ldblquote": "\u201c", "rdblquote": "\u201d",
}  # fmt: skip
_RTF_SYMBOLS = {"~": "\u00a0", "_": "-", "-": "", "\\": "\\", "{": "{", "}": "}", "\n": "\n", "\r": "\n"}
_RTF_TOKEN_RE = re.compile(
    r"\\([a-zA-Z]+)(-?\d+)? ?"  # control word, optional numeric parameter, optional delimiting space
    r"|\\'([0-9a-fA-F]{2})"  # byte in the document code page
    r"|\\(.)"  # control symbol
    r"|([{}])"  # group
    r"|[\r\n]+"  # line breaks in the source are not text
    r"|([^\\{}\r\n]+)",  # plain text
    re.DOTALL,
)


class _RtfGroup:
    __slots__ = ("skip", "uc")

    def __init__(self, skip: bool = False, uc: int = 1) -> None:
        self.skip = skip  # inside a destination that is not shown
        self.uc = uc  # characters that follow \uN as a fallback for readers without Unicode


class _RtfParser:
    """Turn RTF source into text: a token loop over groups, control words and plain text."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.out: list[str] = []
        self.pending = bytearray()  # \'hh bytes, decoded together so multibyte code pages work
        self.codepage = "cp1252"
        self.stack: list[_RtfGroup] = []
        self.group = _RtfGroup()
        self.fallback = 0  # characters still to drop after a \uN
        self.group_start = False  # just after "{": the next control word may name a destination

    def parse(self) -> str:
        pos = 0
        while pos < len(self.source):
            match = _RTF_TOKEN_RE.match(self.source, pos)
            if match is None:  # a lone backslash at the end
                break
            pos = match.end()
            group_start, self.group_start = self.group_start, False
            word, param, hex_byte, symbol, brace, plain = match.groups()
            if brace is not None:
                self._brace(brace)
            elif hex_byte is not None:
                if not self._drop_fallback() and not self.group.skip:
                    self.pending.append(int(hex_byte, 16))
            elif plain is not None:
                self._plain(plain)
            elif symbol is not None:
                self._symbol(symbol)
            elif word is not None:
                pos += self._word(word, param, group_start)
        self._flush()
        return "".join(self.out)

    def _flush(self) -> None:
        if self.pending:
            try:
                self.out.append(self.pending.decode(self.codepage, errors="replace"))
            except LookupError:
                self.out.append(self.pending.decode("cp1252", errors="replace"))
            self.pending.clear()

    def _emit(self, text: str) -> None:
        if not self.group.skip:
            self._flush()
            self.out.append(text)

    def _drop_fallback(self) -> bool:
        if self.fallback:
            self.fallback -= 1
            return True
        return False

    def _brace(self, brace: str) -> None:
        self._flush()
        self.fallback = 0
        if brace == "{":
            self.stack.append(self.group)
            self.group = _RtfGroup(self.group.skip, self.group.uc)
            self.group_start = True
        else:
            self.group = self.stack.pop() if self.stack else _RtfGroup()

    def _plain(self, plain: str) -> None:
        dropped = min(self.fallback, len(plain))
        self.fallback -= dropped
        if plain[dropped:]:
            self._emit(plain[dropped:])

    def _symbol(self, symbol: str) -> None:
        if symbol == "*":
            self.group.skip = True  # ignorable destination: readers that do not know it skip the group
        elif not self._drop_fallback() and symbol in _RTF_SYMBOLS:
            self._emit(_RTF_SYMBOLS[symbol])

    def _word(self, word: str, param: str | None, group_start: bool) -> int:
        """Handle a control word; return how many source characters to skip after it."""
        if word == "bin" and param:  # raw binary data
            return max(int(param), 0)
        if group_start and word in _RTF_SKIPPED:
            self.group.skip = True
        elif word == "ansicpg" and param:
            self.codepage = f"cp{param}"
        elif word == "uc" and param is not None:
            self.group.uc = max(int(param), 0)
        elif word == "u" and param is not None:
            code = int(param)
            self._emit(chr(code + 65536 if code < 0 else code))
            self.fallback = self.group.uc
        elif word in _RTF_TEXT:
            self._emit(_RTF_TEXT[word])
        return 0


def rtf_to_text(source: str) -> str:
    """Return the text of an RTF document (given as latin-1 decoded bytes), without formatting or metadata."""
    return _RtfParser(source).parse()


def read_rtf(data: bytes) -> str:
    """Return the text of an RTF file. Raises ``ValueError`` if the data does not look like RTF."""
    source = data.decode("latin-1")
    if not source.lstrip().startswith("{\\rtf"):
        raise ValueError("not an RTF file (it must start with {\\rtf)")
    return rtf_to_text(source)


# Jupyter notebooks ---------------------------------------------------------------------------------------------


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", cell.get("input", ""))  # "input": code cells of nbformat 3
    return "".join(source) if isinstance(source, list) else str(source)


def read_ipynb(data: bytes) -> str:
    """Return the Markdown and code cells of a Jupyter notebook, separated by blank lines. Outputs are left out."""
    notebook = json.loads(decode_text(data))
    if not isinstance(notebook, dict):
        raise ValueError("not a Jupyter notebook")
    cells = notebook.get("cells")
    if cells is None:  # nbformat 3 keeps the cells in worksheets
        cells = [cell for sheet in notebook.get("worksheets", []) for cell in sheet.get("cells", [])]
    if not isinstance(cells, list):
        raise ValueError("not a Jupyter notebook")
    blocks = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        kind = cell.get("cell_type")
        if kind == "markdown":
            blocks.append(markdown_to_text(_cell_source(cell)))
        elif kind == "code":
            blocks.append(_cell_source(cell))
    return "\n\n".join(block.strip("\n") for block in blocks if block.strip())
