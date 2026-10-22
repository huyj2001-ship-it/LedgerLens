"""Parse tagged numeric facts out of an iXBRL report: the raw material of the answer key.

A fact's machine value is the displayed text, read according to its ``format`` transform,
multiplied by ``10 ** scale`` and negated when ``sign="-"``. Contexts give the period and any
dimensions; units give the currency (or currency per share).

The runtime package never imports this module; see ADR-0002.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from ledgerlens.ingest.ixbrl import IX, IxReport

XBRLI_NS = "http://www.xbrl.org/2003/instance"
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
XBRLI = f"{{{XBRLI_NS}}}"
XBRLDI = f"{{{XBRLDI_NS}}}"

_DIGITS_AND_DOT = re.compile(r"[^0-9.]")
_DIGITS_AND_COMMA = re.compile(r"[^0-9,]")
_DIGIT_GROUPS = re.compile(r"\d+")


class FormatError(ValueError):
    """The displayed text could not be read with the declared transform."""


@dataclass(frozen=True)
class Context:
    id: str
    start: date | None  # None for instants
    end: date  # inclusive end date, or the instant
    dims: tuple[tuple[str, str], ...]  # sorted (dimension, member) pairs


@dataclass(frozen=True)
class Fact:
    anchor: str
    concept: str
    value: Decimal
    decimals: int | None  # None means INF (exact)
    unit: str
    period_start: date | None
    period_end: date
    dims: tuple[tuple[str, str], ...]
    displayed: str
    scale: int
    negated: bool
    hidden: bool

    @property
    def is_instant(self) -> bool:
        return self.period_start is None

    @property
    def has_dimensions(self) -> bool:
        return bool(self.dims)


@dataclass(frozen=True)
class SkippedFact:
    anchor: str
    concept: str
    reason: str


def canonical_qname(qname: str, element: etree._Element) -> str:
    """Normalise a QName so the same concept compares equal across documents.

    Converters choose their own prefixes, so prefixes are resolved through the namespace map:
    any IFRS taxonomy version becomes ``ifrs-full``; company extensions keep their prefix.
    """
    prefix, _, local = qname.rpartition(":")
    namespace = element.nsmap.get(prefix or None, "")
    if "/ifrs-full" in namespace:
        return f"ifrs-full:{local}"
    if namespace.endswith("/iso4217"):
        return f"iso4217:{local}"
    if namespace == XBRLI_NS:
        return f"xbrli:{local}"
    return f"{prefix}:{local}" if prefix else local


def read_transform(fmt: str | None, displayed: str) -> Decimal:
    """Apply an Inline XBRL transformation (registries TR3 to TR5) to the displayed text."""
    text = displayed.strip()
    name = (fmt or "").rpartition(":")[2].replace("-", "").lower()
    try:
        if name in ("", "numdotdecimal"):
            cleaned = _DIGITS_AND_DOT.sub("", text) if name else text
            return Decimal(cleaned)
        if name == "numcommadecimal":
            return Decimal(_DIGITS_AND_COMMA.sub("", text).replace(",", "."))
        if name in ("fixedzero", "zerodash", "numdotdecimalzero"):
            return Decimal(0)
        if name in ("numunitdecimal", "numcommadecimalunit"):
            groups = _DIGIT_GROUPS.findall(text)
            if len(groups) == 1:
                return Decimal(groups[0])
            return Decimal(f"{''.join(groups[:-1])}.{groups[-1]}")
    except InvalidOperation as exc:
        raise FormatError(f"cannot read {displayed!r} with {fmt}") from exc
    raise FormatError(f"unsupported format {fmt}")


def parse_contexts(root: etree._Element) -> dict[str, Context]:
    contexts: dict[str, Context] = {}
    for ctx in root.iter(f"{XBRLI}context"):
        period = ctx.find(f"{XBRLI}period")
        if period is None:
            continue
        instant = period.findtext(f"{XBRLI}instant")
        start = period.findtext(f"{XBRLI}startDate")
        end = period.findtext(f"{XBRLI}endDate")
        dims = []
        for member in ctx.iter(f"{XBRLDI}explicitMember"):
            dims.append(
                (
                    canonical_qname(member.get("dimension", ""), member),
                    canonical_qname((member.text or "").strip(), member),
                )
            )
        for member in ctx.iter(f"{XBRLDI}typedMember"):
            value = _raw_text(member).strip()
            dims.append((canonical_qname(member.get("dimension", ""), member), value))
        contexts[ctx.get("id", "")] = Context(
            id=ctx.get("id", ""),
            start=None if instant else _date(start),
            end=_date(instant or end),
            dims=tuple(sorted(dims)),
        )
    return contexts


def parse_units(root: etree._Element) -> dict[str, str]:
    units: dict[str, str] = {}
    for unit in root.iter(f"{XBRLI}unit"):
        divide = unit.find(f"{XBRLI}divide")
        if divide is not None:
            num = _measures(divide.find(f"{XBRLI}unitNumerator"))
            den = _measures(divide.find(f"{XBRLI}unitDenominator"))
            units[unit.get("id", "")] = f"{num}/{den}"
        else:
            units[unit.get("id", "")] = _measures(unit)
    return units


def _measures(parent: etree._Element | None) -> str:
    if parent is None:
        return ""
    return "*".join(
        canonical_qname((m.text or "").strip(), m) for m in parent.findall(f"{XBRLI}measure")
    )


def _raw_text(el: etree._Element) -> str:
    return "".join(t for t in el.itertext() if isinstance(t, str))


def _date(value: str | None) -> date:
    if not value:
        raise ValueError("context without a period date")
    return date.fromisoformat(value.strip()[:10])


def _is_hidden_fact(el: etree._Element) -> bool:
    return any(a.tag == f"{IX}hidden" for a in el.iterancestors())


def parse_numeric_facts(report: IxReport) -> tuple[list[Fact], list[SkippedFact]]:
    """All numeric facts of a report, plus the ones that could not be read and why."""
    contexts = parse_contexts(report.root)
    units = parse_units(report.root)
    facts: list[Fact] = []
    skipped: list[SkippedFact] = []
    for el, anchor in report.anchors.items():
        concept = canonical_qname(el.get("name", ""), el)
        if el.get(XSI_NIL) == "true":
            skipped.append(SkippedFact(anchor, concept, "nil"))
            continue
        ctx = contexts.get(el.get("contextRef", ""))
        unit = units.get(el.get("unitRef", ""))
        if ctx is None or unit is None:
            skipped.append(SkippedFact(anchor, concept, "unknown context or unit"))
            continue
        displayed = _raw_text(el)
        try:
            magnitude = read_transform(el.get("format"), displayed)
        except FormatError as exc:
            skipped.append(SkippedFact(anchor, concept, str(exc)))
            continue
        scale = int(el.get("scale") or 0)
        negated = el.get("sign") == "-"
        value = magnitude.scaleb(scale)
        decimals = el.get("decimals")
        facts.append(
            Fact(
                anchor=anchor,
                concept=concept,
                value=-value if negated else value,
                decimals=None if decimals in (None, "INF") else int(decimals),
                unit=unit,
                period_start=ctx.start,
                period_end=ctx.end,
                dims=ctx.dims,
                displayed=displayed.strip(),
                scale=scale,
                negated=negated,
                hidden=_is_hidden_fact(el),
            )
        )
    return facts, skipped
