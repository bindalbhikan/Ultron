"""HTML pages read in one place (docs/libraries/09-selectolax.md).

    page = parse(html)                      a page; selectolax (Lexbor, C) when installed, else BeautifulSoup
    page.select("table tbody > tr")         CSS, every match;  page.select_one(css) the first or None
    node.text()                             its text, pieces stripped and joined by a space (BeautifulSoup's
                                            get_text(" ", strip=True));  text_of(node) with spaces folded, "" for None
    node.attr("href")                       an attribute ("" for an empty one, None when missing); node["href"] or KeyError
    node.children("td")                     the direct child elements of those tags
    node.next_sibling("dd")                 the next sibling element of that tag;  node.parent_of("li") the nearest one up

selectolax parses 10-30x faster than BeautifulSoup. The seller-neutral core (ultron.portals.omsguru) stays
installable without it (Android / Termux, pure Python): there the same calls run on BeautifulSoup.
"""
from __future__ import annotations

import re
from typing import Iterable, Iterator

try:
    from selectolax.lexbor import LexborHTMLParser as _Lexbor
except ImportError:                        # pragma: no cover - Termux: pure Python
    _Lexbor = None

_SKIP = {"-comment", "script", "style", "template"}


class Node:
    """One element of a page, the same calls whatever parsed it."""
    __slots__ = ("_n", "_lex")

    def __init__(self, n, lex: bool):
        self._n, self._lex = n, lex

    # --------------------------------------------------------------- finding
    def select(self, css: str) -> list["Node"]:
        found = self._n.css(css) if self._lex else self._n.select(css)
        return [Node(x, self._lex) for x in found]

    def select_one(self, css: str) -> "Node | None":
        x = self._n.css_first(css) if self._lex else self._n.select_one(css)
        return Node(x, self._lex) if x is not None else None

    @property
    def tag(self) -> str:
        return (self._n.tag if self._lex else self._n.name) or ""

    def _elements(self, nodes: Iterable) -> Iterator["Node"]:
        for x in nodes:
            tag = x.tag if self._lex else getattr(x, "name", None)
            if tag and not tag.startswith("-"):
                yield Node(x, self._lex)

    def children(self, *tags: str) -> list["Node"]:
        kids = self._n.iter(include_text=False) if self._lex else self._n.children
        return [k for k in self._elements(kids) if not tags or k.tag in tags]

    def next_sibling(self, tag: str) -> "Node | None":
        x = self._n.next if self._lex else self._n.next_sibling
        while x is not None:
            name = x.tag if self._lex else getattr(x, "name", None)
            if name == tag:
                return Node(x, self._lex)
            x = x.next if self._lex else x.next_sibling
        return None

    def parent_of(self, tag: str) -> "Node | None":
        x = self._n.parent
        while x is not None:
            if (x.tag if self._lex else x.name) == tag:
                return Node(x, self._lex)
            x = x.parent
        return None

    # --------------------------------------------------------------- reading
    def attr(self, name: str, default: str | None = None) -> str | None:
        if self._lex:
            attrs = self._n.attributes
            if name not in attrs:
                return default
            v = attrs[name]
            return "" if v is None else v
        v = self._n.get(name)
        if v is None:
            return default
        return " ".join(v) if isinstance(v, list) else v

    def __getitem__(self, name: str) -> str:
        v = self.attr(name)
        if v is None:
            raise KeyError(name)
        return v

    def has(self, name: str) -> bool:
        return self.attr(name) is not None

    def text(self) -> str:
        """The text pieces, each stripped, joined by one space (BeautifulSoup's get_text(" ", strip=True))."""
        if not self._lex:
            return self._n.get_text(" ", strip=True)
        pieces = []
        for x in self._n.traverse(include_text=True):
            if x.tag == "-text" and not _inside_skipped(x, self._n):
                t = (x.text_content or "").strip()
                if t:
                    pieces.append(t)
        return " ".join(pieces)

    def html(self) -> str:
        return (self._n.html if self._lex else str(self._n)) or ""


def _inside_skipped(x, top) -> bool:
    p = x.parent
    while p is not None and p is not top:
        if p.tag in _SKIP:
            return True
        p = p.parent
    return False


def parse(html: str | bytes, engine: str = "") -> Node:
    """A page. engine "bs4" forces BeautifulSoup (the tests and the Termux core use it)."""
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    if _Lexbor is not None and engine != "bs4":
        return Node(_Lexbor(html).root or _Lexbor("<html></html>").root, True)
    from bs4 import BeautifulSoup
    return Node(BeautifulSoup(html, "html.parser"), False)


def text_of(node: Node | None) -> str:
    """A node's text with every run of spaces folded into one; "" for no node."""
    return re.sub(r"\s+", " ", node.text()).strip() if node is not None else ""
