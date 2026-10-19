"""Deterministic grounding checks used by the Verifier.

A text passes only if every number it states can be traced to the evidence (moment facts, context,
tool ledger) and every rostered player it names appears in that evidence.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

# digits not glued to latin letters; CJK text puts digits right after characters ("スコアは3-2").
# Signs are ignored: "3-2" is a score, and DVA values are compared by magnitude.
NUMBER = re.compile(r"(?<![A-Za-z0-9_.])\d+(?:[.,]\d+)?")
ALWAYS_ALLOWED = {0.0, 1.0, 2.0}


def numbers_in(text: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in NUMBER.findall(text)]


def _walk(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def allowed_numbers(*sources: Any) -> set[float]:
    """Every number in the evidence plus the renderings a writer may legitimately use."""
    out = set(ALWAYS_ALLOWED)
    for v in (x for s in sources for x in _walk(s)):
        if isinstance(v, bool) or v is None:
            continue
        values = numbers_in(v) if isinstance(v, str) else [float(v)] if isinstance(v, (int, float)) else []
        for n in values:
            variants = {n, abs(n), round(n), round(n, 1), round(n, 2)}
            if 0 < abs(n) <= 1:  # shares and probabilities may be written as percentages
                variants |= {round(n * 100), round(n * 100, 1)}
            if abs(n) >= 1000:  # metres may be written as kilometres
                variants |= {round(n / 1000, 1), round(n / 1000, 2)}
            out |= {float(abs(x)) for x in variants}
    return out


def unsupported_numbers(text: str, allowed: set[float]) -> list[float]:
    return [n for n in numbers_in(text) if not any(abs(abs(n) - a) < 1e-6 for a in allowed)]


def evidence_names(roster: dict[str, dict], *sources: Any) -> set[str]:
    blob = " ".join(str(v) for s in sources for v in _walk(s) if isinstance(v, str))
    return {pid for pid, p in roster.items() if p["name"] in blob or pid in blob}


def unsupported_players(text: str, roster: dict[str, dict], allowed_ids: set[str]) -> list[str]:
    bad = []
    for pid, p in roster.items():
        if pid not in allowed_ids and re.search(rf"\b{re.escape(p['short_name'])}\b", text):
            bad.append(p["name"])
    return bad


def check_text(text: str, allowed: set[float], roster: dict[str, dict], allowed_ids: set[str]) -> list[str]:
    problems = [f"number {n:g} is not in the evidence" for n in unsupported_numbers(text, allowed)]
    problems += [f"player {name} is not part of this moment's evidence"
                 for name in unsupported_players(text, roster, allowed_ids)]
    return problems


def same_numbers(source: str, translation: str) -> bool:
    """A translation must state exactly the same numbers as its source."""
    return Counter(numbers_in(source)) == Counter(numbers_in(translation))
