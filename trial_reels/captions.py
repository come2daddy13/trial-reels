"""Podpis wersji triala.

Pierwsza linia zostaje bliska oryginałowi, bo wezwanie do akcji ma być takie, jak było. Zmienia się
sformułowanie CTA (`cta_variants` w puli, oryginał zostaje w rotacji) i dopisek na końcu (`extras`),
więc kolejne wersje tej samej rolki mają inny tekst.
"""
from __future__ import annotations

import math
import re

KEEP = re.compile(r"@[\w.]*\w|„[^”]+”")


def must_keep(cta: str) -> set:
    """Elementy CTA, których wariant nie może zgubić: @profil i słowo-klucz w cudzysłowie („PLAN”)."""
    return set(KEEP.findall(cta))


def has_cta(reel: dict) -> bool:
    """Czy rolka ma wezwanie do działania (`cta`). Pole jest opcjonalne: brak, None i pusty tekst znaczą „nie ma”."""
    cta = reel.get("cta")
    return isinstance(cta, str) and bool(cta.strip())


def period(reel: dict) -> int:
    """Co ile wersji podpis rolki zaczyna się powtarzać (`compose` daje ten sam tekst dla `nth` i `nth + okres`).

    Zaproszenie i dopisek rotują osobno, więc okres to najmniejsza wspólna wielokrotność liczby wersji zaproszenia
    (oryginał i warianty, o ile rotacja w ogóle działa) i liczby dopisków. Pola o złym formacie dają 1: błąd
    zgłosi dopiero `compose`.
    """
    try:
        rotates = has_cta(reel) and bool(reel.get("cta_variants")) and reel["cta"] in reel.get("caption", "")
        options = len(reel["cta_variants"]) + 1 if rotates else 1
        return math.lcm(options, len(reel.get("extras") or []) or 1)
    except (TypeError, AttributeError):
        return 1


def compose(reel: dict, nth: int) -> str:
    """nth = numer wersji tej rolki (0, 1, 2…). CTA i dopiski rotują osobno, więc sąsiednie wersje się różnią.

    Rolka bez `cta` nie ma czego rotować: podpis zostaje taki, jaki jest, i dopisuje się do niego tylko dopisek
    z `extras` (warianty CTA bez `cta` się nie liczą).
    """
    text = reel.get("caption", "")
    cta, variants = reel.get("cta"), reel.get("cta_variants") or []
    if has_cta(reel) and variants and cta in text:
        options = [cta] + variants
        text = text.replace(cta, options[nth % len(options)], 1)
    extras = reel.get("extras") or []
    if extras:
        text = text.rstrip() + "\n\n" + extras[nth % len(extras)]
    return text
