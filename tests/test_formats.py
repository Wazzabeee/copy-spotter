from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from copy_spotter import Document, DocumentReadError, find_documents, load_directory
from copy_spotter._formats import html_to_text, markdown_to_text, read_html, read_ipynb, read_markdown, read_rtf
from copy_spotter.cli import main
from copy_spotter.extract import SUPPORTED_FORMATS, extract_words

# Markdown ------------------------------------------------------------------------------------------------------


def test_markdown_keeps_link_text_and_drops_targets() -> None:
    text = markdown_to_text("See [the docs](http://example.com/a_b) and ![a chart](img/chart.png).")
    assert text == "See the docs and a chart."


def test_markdown_drops_reference_definitions_autolinks_html_and_comments() -> None:
    source = "Read [this][1] <https://example.com> <span class='x'>now</span><!-- hidden -->\n\n[1]: http://ref.org\n"
    assert markdown_to_text(source).split() == ["Read", "this", "now"]


def test_markdown_underscore_emphasis_does_not_stick_to_words() -> None:
    assert markdown_to_text("_quick_ __brown__ ___fox___ snake_case") == "quick brown fox snake_case"


def test_markdown_document_words() -> None:
    document = Document.from_bytes(b"# Title\n\n* one *item*\n* `code` here\n", "notes.md")
    assert document.words == ("title", "one", "item", "code", "here")
    assert document.text.startswith("# Title")


def test_markdown_encodings() -> None:
    assert read_markdown("café".encode("cp1252")) == "café"
    assert read_markdown(b"\xef\xbb\xbfhello") == "hello"


# HTML ----------------------------------------------------------------------------------------------------------

_PAGE = """<!DOCTYPE html>
<html><head><title>Page title</title><style>p { color: red }</style>
<script>var html = "<p>not shown</p>";</script></head>
<body><h1>Main   heading</h1><p>First &amp; <b>bold</b>
paragraph.</p><ul><li>one</li><li>two</li></ul>
<pre>  kept
  spaces</pre><table><tr><td>a</td><td>b</td></tr></table>x<br>y<br/>z<noscript>enable js</noscript></body></html>
"""


def test_html_visible_text_only() -> None:
    document = Document.from_text(html_to_text(_PAGE), "page.html")
    assert document.words == tuple(
        "main heading first bold paragraph one two kept spaces a b x y z".split()
    )  # no title, style, script or noscript
    assert "Main heading\n\nFirst & bold paragraph." in document.text
    assert "one\n\ntwo" in document.text
    assert "x\ny\nz" in document.text


def test_html_charset() -> None:
    declared = b'<html><head><meta charset="windows-1252"></head><body>caf\xe9</body></html>'
    assert read_html(declared).strip() == "café"
    http_equiv = b'<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"><p>na\xefve</p>'
    assert read_html(http_equiv).strip() == "naïve"
    assert read_html("<p>café</p>".encode()).strip() == "café"  # UTF-8 by default
    unknown = b'<meta charset="no-such-codec"><p>caf\xc3\xa9</p>'
    assert read_html(unknown).strip() == "café"


def test_htm_extension_and_entities() -> None:
    document = Document.from_bytes(b"<p>Fish &amp; chips &eacute;t&eacute; &#233;</p>", "menu.htm")
    assert document.words == ("fish", "chips", "été", "é")


def test_html_unclosed_skipped_element_does_not_hide_the_rest_forever() -> None:
    # A stray closing tag never makes the depth negative.
    assert html_to_text("</script><p>shown</p>").strip() == "shown"


# RTF -----------------------------------------------------------------------------------------------------------


def _rtf(body: str) -> bytes:
    return ("{\\rtf1\\ansi\\ansicpg1252\\deff0{\\fonttbl{\\f0\\fswiss Arial;}}{\\colortbl;\\red0\\green0\\blue0;}\n"
            "{\\info{\\title Hidden title}{\\author Someone}}{\\*\\generator Riched20;}\n"
            + body + "}").encode("ascii")  # fmt: skip


def test_rtf_text_and_paragraphs() -> None:
    text = read_rtf(_rtf("\\f0\\fs24 First \\b bold\\b0  paragraph.\\par\nSecond\\tab line\\line next\\par"))
    assert text == "First bold paragraph.\nSecond\tline\nnext\n"


def test_rtf_skips_metadata_tables_pictures_and_field_codes() -> None:
    body = '{\\field{\\*\\fldinst HYPERLINK "http://x.com"}{\\fldrslt link text}} {\\pict\\wmetafile8 0102ab}after'
    text = read_rtf(_rtf(body))
    assert text == "link text after"
    assert "Hidden" not in text and "Arial" not in text and "Riched" not in text


def test_rtf_code_page_bytes_and_unicode() -> None:
    assert read_rtf(_rtf("Caf\\'e9 cr\\'e8me")) == "Café crème"
    # \uN is followed by \ucN fallback characters (1 by default) that must be dropped.
    assert read_rtf(_rtf("\\u8220?quoted\\u8221? \\uc2\\u233\\'e9\\'e9 done")) == "“quoted” é done"
    assert read_rtf(_rtf("\\u-3913?")) == chr(65536 - 3913)
    # Multibyte code page: two \'hh bytes form one character.
    shift_jis = "{\\rtf1\\ansi\\ansicpg932 \\'93\\'fa\\'96\\'7b}".encode("ascii")
    assert read_rtf(shift_jis) == "日本"


def test_rtf_symbols_and_escapes() -> None:
    text = read_rtf(_rtf("a\\~b\\_c\\-d \\{braces\\} back\\\\slash \\emdash \\ldblquote q\\rdblquote"))
    assert text == f"a{chr(0xA0)}b-cd {{braces}} back\\slash {chr(0x2014)}{chr(0x201C)}q{chr(0x201D)}"


def test_rtf_binary_data_is_skipped() -> None:
    assert read_rtf(_rtf("before {\\*\\blipuid \\bin4 {}\\x}after")) == "before after"
    assert read_rtf(_rtf("before \\bin3 a}b after")) == "before  after"


def test_rtf_document_and_errors() -> None:
    document = Document.from_bytes(_rtf("Hello\\par World"), "letter.rtf")
    assert document.words == ("hello", "world")
    with pytest.raises(DocumentReadError, match=r"Could not read notes\.rtf"):
        Document.from_bytes(b"plain text, not rtf", "notes.rtf")


# Jupyter notebooks ---------------------------------------------------------------------------------------------


def _notebook(cells: list[dict[str, Any]], **extra: Any) -> bytes:
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5, **extra}).encode()


def test_ipynb_markdown_and_code_cells_without_outputs() -> None:
    data = _notebook(
        [
            {"cell_type": "markdown", "source": ["# Analysis\n", "See [docs](http://x.org)."]},
            {"cell_type": "code", "source": "print('hello')", "outputs": [{"text": "hello output"}]},
            {"cell_type": "raw", "source": "raw cell"},
            {"cell_type": "markdown", "source": ""},
        ]
    )
    assert read_ipynb(data) == "# Analysis\nSee docs.\n\nprint('hello')"
    assert Document.from_bytes(data, "lab.ipynb").words == ("analysis", "see", "docs", "print", "hello")


def test_ipynb_nbformat_3() -> None:
    data = json.dumps(
        {"worksheets": [{"cells": [{"cell_type": "markdown", "source": "Intro"}, {"cell_type": "code", "input": "x"}]}]}
    ).encode()
    assert read_ipynb(data) == "Intro\n\nx"


@pytest.mark.parametrize("data", [b"not json", b"[1, 2]", b'{"cells": 3}'])
def test_ipynb_errors(data: bytes) -> None:
    with pytest.raises(DocumentReadError, match=r"Could not read bad\.ipynb"):
        Document.from_bytes(data, "bad.ipynb")


# Discovery and command line ------------------------------------------------------------------------------------


def test_supported_formats() -> None:
    assert SUPPORTED_FORMATS == ("pdf", "docx", "odt", "txt", "md", "html", "htm", "rtf", "ipynb")


@pytest.mark.parametrize("fmt", ["md", "html", "htm", "rtf", "ipynb", ".MD", "HTML"])
def test_from_bytes_format_override(fmt: str) -> None:
    data = {
        "md": b"Some words",
        "html": b"<p>Some words</p>",
        "htm": b"<p>Some words</p>",
        "rtf": b"{\\rtf1 Some words}",
        "ipynb": _notebook([{"cell_type": "markdown", "source": "Some words"}]),
    }[fmt.lower().lstrip(".")]
    assert Document.from_bytes(data, "upload", format=fmt).words == ("some", "words")


def test_find_documents_skips_copy_spotter_reports(tmp_path: Path) -> None:
    for name in ("a.md", "b.html", "c.rtf", "d.ipynb", "e.HTM", "old/_results.html", "old/0_1.html", "old/notes.md"):
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text("x")
    found = [p.relative_to(tmp_path).as_posix() for p in find_documents(tmp_path, recursive=True)]
    assert found == ["a.md", "b.html", "c.rtf", "d.ipynb", "e.HTM", "old/notes.md"]


def test_extract_words_from_path(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_bytes(b"<p>Hello <i>there</i></p>")
    assert extract_words(path) == ["hello", "there"]


def test_cli_compares_new_formats(tmp_path: Path) -> None:
    passage = "the industrial revolution changed the way people lived and worked in cities"
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text(f"# Essay\n\n{passage}, said [the book](http://b.org).\n", encoding="utf-8")
    (docs / "b.html").write_text(f"<html><body><p>{passage}.</p></body></html>", encoding="utf-8")
    (docs / "c.rtf").write_text("{\\rtf1\\ansi " + passage + "\\par}", encoding="ascii")
    (docs / "d.ipynb").write_bytes(_notebook([{"cell_type": "markdown", "source": passage}]))
    json_path = tmp_path / "pairs.json"
    assert main([str(docs), "-o", str(tmp_path / "out"), "--json", str(json_path), "--no-open"]) == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert [d["name"] for d in data["documents"]] == ["a.md", "b.html", "c.rtf", "d.ipynb"]
    assert len(data["pairs"]) == 6
    # The passage is complete in every document, so each one is found in the html, rtf and notebook versions.
    for pair in data["pairs"]:
        if pair["document_1"] != "a.md":
            assert pair["coverage_1"] == pair["coverage_2"] == 100.0


def test_load_directory_reads_new_formats(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("alpha beta", encoding="utf-8")
    (tmp_path / "b.rtf").write_text("{\\rtf1 gamma delta}", encoding="ascii")
    assert [d.words for d in load_directory(tmp_path)] == [("alpha", "beta"), ("gamma", "delta")]
