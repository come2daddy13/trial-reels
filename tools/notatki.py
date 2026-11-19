"""Notatki wydania: sekcje ZMIANY.md od poprzedniego wydania do bieżącego.

Uruchomienie z dowolnego folderu:

    python tools/notatki.py WERSJA [--tagi "v0.1.0 v0.2.0"] [--plik ZMIANY.md]

`aktualizuj` u klienta pokazuje notatki jednego wydania (najnowszego). Klient, który pominął wydanie, nie zobaczyłby
jego zmian, więc notatki wydania zawierają sekcje wszystkich wersji nowszych niż poprzedni tag, aż do bieżącej. Bez
poprzedniego tagu (pierwsze wydanie) jest tylko sekcja bieżąca. Poprzedni tag to największy tag o numerze X.Y.Z mniejszym
od bieżącej wersji: tagi próbne (np. v1.0.0-beta) i inne nazwy są pomijane.

Kod wyjścia: 0 gdy notatki gotowe (wypisane na stdout), 1 przy błędzie (brak sekcji bieżącej wersji albo jej opisu,
zła wersja, brak pliku). Narzędzie używa tylko biblioteki standardowej.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_HEADING = re.compile(r"^## (\S+)\s*$")


def parse(text: str) -> tuple | None:
    """Numer wersji „0.2.0” albo „v0.2.0” jako krotka liczb. None, gdy to nie jest numer w formie X.Y.Z."""
    match = _VERSION.fullmatch(text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def sections(text: str) -> list:
    """Sekcje `## X.Y.Z` jako lista (numer wersji, tekst sekcji z nagłówkiem), w kolejności z pliku.

    Nagłówki, które nie są numerem wersji, nie otwierają sekcji: ich treść należy do poprzedniej sekcji.
    """
    found, current = [], None
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        heading = _HEADING.match(line)
        if heading and parse(heading.group(1)):
            current = [parse(heading.group(1)), [line]]
            found.append(current)
        elif current is not None:
            current[1].append(line)
    return [(numbers, "\n".join(lines).strip("\n")) for numbers, lines in found]


def previous(current: tuple, tags: list) -> tuple | None:
    """Największy tag o numerze X.Y.Z mniejszym od `current`. None, gdy takiego nie ma."""
    older = [numbers for numbers in (parse(tag) for tag in tags) if numbers is not None and numbers < current]
    return max(older) if older else None


def notes(text: str, version: str, tags: list) -> str:
    """Notatki wydania `version`: sekcja tej wersji i sekcje wersji pomiędzy poprzednim tagiem a nią (od najnowszej).

    Zgłasza `ValueError`, gdy `version` nie jest numerem X.Y.Z albo ZMIANY.md nie ma jej sekcji z opisem (co najmniej
    nagłówek i jedna niepusta linia): wydanie bez opisu zmian nie powinno wyjść.
    """
    current = parse(version)
    if current is None:
        raise ValueError("numer wersji musi mieć postać X.Y.Z (jest: %s)" % " ".join(version.split()))
    found = sections(text)
    mine = next((body for numbers, body in found if numbers == current), None)
    if mine is None or sum(1 for line in mine.splitlines() if line.strip()) < 2:
        raise ValueError("ZMIANY.md nie ma sekcji ## %s z opisem zmian." % version)
    floor = previous(current, tags)
    chosen = [(numbers, body) for numbers, body in found
              if numbers == current or (floor is not None and floor < numbers < current)]
    chosen.sort(key=lambda item: item[0], reverse=True)
    return "\n\n".join(body for _, body in chosen) + "\n"


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="notatki", description="Buduje notatki wydania z ZMIANY.md.",
                                     epilog="Kody wyjścia: 0 gotowe, 1 błąd.")
    parser.add_argument("version", metavar="WERSJA", help="numer wydania, np. 0.2.0 (bez litery v)")
    parser.add_argument("--tagi", default="", help="istniejące tagi oddzielone spacjami albo liniami (git tag --list)")
    parser.add_argument("--plik", default=str(ROOT / "ZMIANY.md"), help="plik ze zmianami (domyślnie ZMIANY.md w repo)")
    args = parser.parse_args(argv)
    try:
        text = Path(args.plik).read_text(encoding="utf-8-sig")
        result = notes(text, args.version, args.tagi.split())
    except (OSError, ValueError) as err:
        print("Notatki: %s" % " ".join(str(err).split()), file=sys.stderr)
        return 1
    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
