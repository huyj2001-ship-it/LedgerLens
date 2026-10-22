"""Load Inline XBRL (iXBRL) reports and give every tagged number a stable anchor.

The runtime only needs the *displayed* document: text, tables and the anchor ids of tagged
numbers (so the evaluation can later locate the evidence for a gold fact). Fact values,
concepts and contexts are deliberately parsed elsewhere, in ``ledgerlens_eval.facts``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from lxml import etree

IX_NS = "http://www.xbrl.org/2013/inlineXBRL"
XHTML_NS = "http://www.w3.org/1999/xhtml"
IX = f"{{{IX_NS}}}"
XH = f"{{{XHTML_NS}}}"

_PAGE_CLASSES = ("pageView", "page", "pf")
_CSS_RULE = re.compile(r"\.([\w-]+)\s*\{([^}]*)\}")
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none", re.IGNORECASE)


class PageMarkup(StrEnum):
    """How a converter marks up pages (see notebooks/01_explore_ixbrl.ipynb)."""

    CLASS = "class"  # <div class="pageView|page|pf">
    BODY_CHILDREN = "body_children"  # each visible child of <body> is a page
    FLOW = "flow"  # continuous HTML without page boundaries


@dataclass
class IxReport:
    """A parsed report plus the lookups every later stage needs."""

    path: Path
    root: etree._Element
    css: dict[str, str] = field(repr=False)
    anchors: dict[etree._Element, str] = field(repr=False)

    @property
    def body(self) -> etree._Element:
        body = self.root.find(f"{XH}body")
        if body is None:
            raise ValueError(f"{self.path} has no XHTML body")
        return body

    @property
    def has_native_tables(self) -> bool:
        return self.body.find(f".//{XH}table") is not None

    def pages(self) -> tuple[PageMarkup, list[etree._Element]]:
        return find_pages(self.body)


def load_report(path: Path) -> IxReport:
    parser = etree.XMLParser(huge_tree=True, remove_comments=True)
    root = etree.parse(str(path), parser).getroot()
    return IxReport(path=path, root=root, css=parse_css(root), anchors=assign_anchors(root))


def parse_css(root: etree._Element) -> dict[str, str]:
    """Class name -> declaration block, from all inline <style> elements."""
    css = "".join(style.text or "" for style in root.iter(f"{XH}style"))
    return dict(_CSS_RULE.findall(css))


def numeric_fact_elements(root: etree._Element) -> list[etree._Element]:
    """All ``ix:nonFraction`` elements in document order (hidden ones included)."""
    return list(root.iter(f"{IX}nonFraction"))


def assign_anchors(root: etree._Element) -> dict[etree._Element, str]:
    """Map each numeric fact element to its ``id``, or a synthetic ``ix-NNNNN`` anchor.

    Several converters omit ids (e.g. Novo Nordisk FY2022-24). Synthetic anchors use document
    order, so the runtime and the evaluation package derive identical anchors independently.
    """
    return {el: el.get("id") or f"ix-{i:05d}" for i, el in enumerate(numeric_fact_elements(root))}


def is_hidden(el: etree._Element) -> bool:
    if el.tag in (f"{IX}header", f"{XH}style", f"{XH}script", f"{XH}head"):
        return True
    return bool(_HIDDEN_STYLE.search(el.get("style") or ""))


def _classes(el: etree._Element) -> list[str]:
    return (el.get("class") or "").split()


def find_pages(body: etree._Element) -> tuple[PageMarkup, list[etree._Element]]:
    """Locate page containers; fall back to treating the whole body as one flow."""
    for cls in _PAGE_CLASSES:
        pages = [el for el in body.iter(f"{XH}div") if cls in _classes(el)]
        if len(pages) >= 2:
            return PageMarkup.CLASS, pages
    visible = [el for el in body if isinstance(el.tag, str) and not is_hidden(el)]
    if len(visible) > 50:
        return PageMarkup.BODY_CHILDREN, visible
    return PageMarkup.FLOW, [body]


def iter_visible(el: etree._Element) -> Iterator[etree._Element]:
    """Depth-first iteration that skips hidden subtrees (ix:header, display:none, styles)."""
    if not isinstance(el.tag, str) or is_hidden(el):
        return
    yield el
    for child in el:
        yield from iter_visible(child)


_BLOCK_NAMES = ("div", "p", "li", "ul", "ol", "table", "tr", "td", "th", "section", "article")
_HEADING_NAMES = ("h1", "h2", "h3", "h4", "h5", "h6", "header", "footer", "br")
BLOCK_TAGS = frozenset(f"{XH}{name}" for name in (*_BLOCK_NAMES, *_HEADING_NAMES))


def text_of(el: etree._Element) -> str:
    """Visible text of an element, whitespace-normalised, hidden descendants excluded.

    Block-level boundaries become spaces, so adjacent ``<div>`` lines do not run together.
    """
    parts: list[str] = []

    def walk(node: etree._Element) -> None:
        if not isinstance(node.tag, str) or is_hidden(node):
            return
        block = node.tag in BLOCK_TAGS
        if block:
            parts.append(" ")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if block:
            parts.append(" ")

    walk(el)
    return " ".join("".join(parts).split())


def anchors_within(report: IxReport, el: etree._Element) -> list[str]:
    """Anchors of the numeric facts displayed inside ``el``, in document order."""
    return [report.anchors[n] for n in el.iter(f"{IX}nonFraction") if n in report.anchors]
