"""Odczyt wyników z panelu Instagrama: parser liczb, skrypt dla przeglądarki i lista wersji do odczytu.

Obserwujących z rolki nie podaje ani Zernio, ani API Mety, więc czytamy ich z panelu statystyk rolki
(`https://www.instagram.com/insights/media/<pk>/`) w przeglądarce, w której klient jest zalogowany. Skrypt
`JS_ODCZYT` tylko czyta tekst strony, a liczby z jego wyniku zamienia `parse_count`.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import config, planner
from .candidates import media_id

MAX_AGE_DAYS = 35   # starszych rolek nie czytamy: liczby prawie już nie rosną
FRESH_DAYS = 6      # rolkę czytaną niedawno zostawiamy w spokoju do kolejnego tygodnia
PANEL_QUERY = "?hl=en"   # adresy do odczytu mają zawsze angielskie etykiety panelu, bez względu na język konta

_COUNT = re.compile(r"^([\d\s.,\u00a0\u202f]+)\s*(tys\.?|mln|k|m)?$")
_MULTIPLIER = {"tys": 1000, "k": 1000, "mln": 1_000_000, "m": 1_000_000}
_SEPARATORS = re.compile(r"[\s\u00a0\u202f,.]")


def parse_count(s) -> int:
    """Liczba z panelu IG jako int: „1234”, „1 234” (też z twardą spacją), „12,345”, „12,3 tys.”, „1,2 mln”,
    „1.2K”, „1.2M”.

    Ze skrótem („tys.”, „mln”, „K”, „M”) przecinek to część dziesiętna, a wynik jest zaokrąglany od połowy w górę.
    Bez skrótu każdy separator (spacja, przecinek, kropka) to separator tysięcy. Napis, który nie jest liczbą,
    zgłasza ValueError.
    """
    text = str(s).strip().lower()
    match = _COUNT.match(text)
    problem = ValueError("Nie rozumiem liczby: %r. Przepisz ją tak, jak widać w panelu, np. 1234 albo 12,3 tys." % (s,))
    if not match:
        raise problem
    number, unit = match.group(1), match.group(2)
    try:
        if unit:
            value = Decimal("".join(number.split()).replace(",", ".")) * _MULTIPLIER[unit.rstrip(".")]
            return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return int(_SEPARATORS.sub("", number))
    except (InvalidOperation, ValueError):
        raise problem from None


# Skrypt dla przeglądarki. Działa w zakładce https://www.instagram.com/insights/media/<PK>/ w przeglądarce, w której
# klient jest zalogowany: czeka do 20 s na dwie etykiety (po polsku „Wyświetlenia” i „Obserwowanie”, po angielsku
# „Views” i „Follows”) i zwraca tekst JSON {pk, views_raw, follows_raw, lang} albo {pk, error, login, tekst}.
# Niczego nie klika i niczego nie wysyła, tylko czyta tekst strony. Liczby zostają w takiej postaci, w jakiej
# są w panelu (np. „12,3 tys.”), a zamienia je `parse_count`.
JS_ODCZYT = r"""const pk = location.pathname.split('/').filter(Boolean).pop() || '';
const L = {
  pl: [/Wyświetlenia \| Wyświetlenia \| ([^|]+)/, /Obserwowanie \| ([^|]+)/],
  en: [/Views \| Views \| ([^|]+)/, /Follows \| ([^|]+)/]
};
let s = '', jezyk = null;
const t0 = Date.now();
while (Date.now() - t0 < 20000) {
  s = ((document.body && document.body.innerText) || '').replace(/\n+/g, ' | ');
  jezyk = Object.keys(L).find(k => L[k][0].test(s) && L[k][1].test(s)) || null;
  if (jezyk) break;
  await new Promise(r => setTimeout(r, 500));
}
const liczba = re => ((s.match(re) || [])[1] || '').trim();
JSON.stringify(jezyk
  ? {pk, views_raw: liczba(L[jezyk][0]), follows_raw: liczba(L[jezyk][1]), lang: jezyk}
  : {pk, error: 'brak liczb w panelu (inny język panelu? dopisz ?hl=en do adresu strony)',
     login: /\/accounts\/login/.test(location.pathname) || /Zaloguj się|Log in|Log into/.test(s), tekst: s.slice(0, 200)})
"""


def panel_url(pk) -> str:
    """Adres panelu statystyk rolki o danym ID mediów."""
    return "https://www.instagram.com/insights/media/%s/" % pk


def _read_recently(version: dict, now: datetime) -> bool:
    """Czy wersję czytano w ostatnich 6 dniach (`read_at`: RRRR-MM-DDTGG:MM w czasie planera). Zepsuta data: nie."""
    read_at = version.get("read_at")
    if not read_at:
        return False
    try:
        t = datetime.fromisoformat(str(read_at))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=planner.TZ)
    return (now - t).days < FRESH_DAYS


def todo(versions, now: datetime, sample: bool = False) -> list[dict]:
    """Wersje do odczytu w panelu jako lista {id, pk, url}, od najstarszej.

    `url` to adres panelu z dopiskiem `?hl=en`, więc etykiety są po angielsku niezależnie od języka Instagrama klienta
    (parametr nie zmienia języka konta na stałe).

    Bierze opublikowane wersje (z numerem ID mediów albo z adresem rolki), które mają od 3 do 35 dni (liczone od
    terminu publikacji w czasie planera) i nie były czytane w ostatnich 6 dniach. Wersje z `skip_stats` pomija.
    Przy `sample=True` zostaje tylko najnowsza taka wersja każdej rolki, czyli próbka do ręcznego odczytu.
    `versions` to słownik {id: wersja} ze stanu (może być też lista wersji).
    """
    now = now if now.tzinfo else now.replace(tzinfo=planner.TZ)
    items = versions.values() if isinstance(versions, dict) else versions
    due = []
    for v in items:
        if v.get("status") != "opublikowana" or v.get("skip_stats") or not v.get("slot") or not v.get("id"):
            continue
        pk = v.get("ig_media_id") or media_id(v.get("ig_url"))
        if not pk:
            continue
        try:
            slot = planner.parse_slot(v["slot"])
        except ValueError:
            continue
        age = (now - slot).days
        if not config.STATS_MIN_AGE_DAYS <= age <= MAX_AGE_DAYS:
            continue
        if _read_recently(v, now):
            continue
        due.append((slot, v["id"], v.get("code") or v["id"], str(pk)))
    due.sort(key=lambda row: (row[0], row[1]))
    if sample:
        newest = {}
        for row in due:  # lista jest posortowana od najstarszej, więc ostatnia z kodem to najnowsza
            newest[row[2]] = row
        due = sorted(newest.values(), key=lambda row: (row[0], row[1]))
    return [{"id": vid, "pk": pk, "url": panel_url(pk) + PANEL_QUERY} for _, vid, _, pk in due]
