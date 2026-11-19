"""Kreator: 12 kroków prowadzących klienta od instalacji do rolek planowanych co tydzień.

Stan kroków wynika z plików w folderze dane/ (klucz, konto, pula, pliki, wersje w stanie), a nie z pamięci rozmowy,
więc działa po przerwie i w nowej rozmowie. Cztery kroki (powitanie, pomiar, tydzień, na co dzień) nie zostawiają śladu
w plikach, więc ich ukończenie zapisuje się w dane/kreator.json komendą `krok --gotowe ID`. Ten sam plik trzyma wpis
`nowa_wersja`, gdy `aktualizuj --sprawdz` znajdzie nowsze wydanie.

Moduł jest lekki: nie ładuje PIL, PyAV ani faster-whisper (robi to dopiero doktor i sprawdzanie puli, gdy ich trzeba).
Pojedyncza kontrola, która się wywróci (uszkodzony plik, zepsuta instalacja), nie psuje reszty: krok dostaje wtedy
„nie udało się sprawdzić” i opis problemu.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta

from . import VERSION, candidates, config, doctor, planner, state, update, versions, zernio

STEPS = (
    ("powitanie", "Powitanie"),
    ("programy", "Programy"),
    ("zernio", "Zernio i klucz"),
    ("konto", "Konto Instagram"),
    ("zwyciezcy", "Zwycięskie rolki"),
    ("pliki", "Pliki i transkrypcje"),
    ("ustawienia", "Ustawienia rolek"),
    ("hooki", "Hooki i podpisy"),
    ("pierwsze", "Pierwsze wersje"),
    ("pomiar", "Pomiar wyników"),
    ("tydzien", "Paczka co tydzień"),
    ("codziennie", "Na co dzień"),
)
IDS = tuple(step_id for step_id, _ in STEPS)
TITLES = dict(STEPS)
ENTRY_STEPS = ("powitanie", "pomiar", "tydzien", "codziennie")   # tylko te kroki są gotowe po wpisie w kreatorze
SHOWN = 5                              # tyle rolek wymieniamy z nazwy, resztę liczymy


# --- kreator.json ---------------------------------------------------------------

def entries() -> dict:
    """Wpisy z dane/kreator.json (pusty słownik, gdy pliku nie ma)."""
    data = config.read_json(config.WIZARD, {})
    if not isinstance(data, dict):
        raise config.UserError("Plik dane/kreator.json ma zły układ: powinien zawierać obiekt (słownik). Napraw go albo "
                               "usuń, a potem uruchom komendę jeszcze raz.")
    return data


def remember(key: str, value: str) -> None:
    """Zapisuje wpis w dane/kreator.json (zachowuje pozostałe)."""
    data = entries()
    data[key] = value
    config.write_json(config.WIZARD, data)


def forget(key: str) -> None:
    """Usuwa wpis z dane/kreator.json. Gdy go nie ma, niczego nie zapisuje."""
    data = entries()
    if key in data:
        del data[key]
        config.write_json(config.WIZARD, data)


def resolve(raw) -> str:
    """Id kroku z tekstu klienta (wielkie litery i białe znaki nie szkodzą). Nieznany krok to UserError z listą kroków."""
    key = str(raw).strip().lower()
    if key not in IDS:
        raise config.UserError("Nie ma kroku „%s”. Kroki: %s." % (" ".join(str(raw).split()), ", ".join(IDS)))
    return key


def mark(step_id: str, value: str = "tak") -> tuple:
    """Zapisuje krok jako zrobiony. Wartość to „tak” albo np. tryb pomiaru (chrome, reczny).

    Id kroku może mieć wielkie litery i białe znaki. Zwraca (id kroku, zapisana wartość).
    """
    key = resolve(step_id)
    text = str(value if value is not None else "").strip() or "tak"
    remember(key, text)
    return key, text


# --- kontrole kroków ------------------------------------------------------------

class _Ctx:
    def __init__(self, data: dict, run_doctor: bool):
        self.entries, self.run_doctor = data, run_doctor


def _active() -> list:
    """Aktywne rolki puli z poprawnym kodem (tak samo liczą je komendy)."""
    return [r for r in candidates.load_pool()
            if isinstance(r, dict) and candidates.valid_code(r.get("code")) and r.get("active", True)]


def _list(codes: list) -> str:
    shown = ", ".join(codes[:SHOWN])
    return shown if len(codes) <= SHOWN else "%s i jeszcze %d" % (shown, len(codes) - SHOWN)


def _sentence(text: str) -> str:
    text = " ".join(str(text).split())
    return text if text[-1:] in ".!?" else text + "."


def _entry(ctx: _Ctx, step_id: str, done: str, todo: str) -> tuple:
    if step_id not in ctx.entries:
        return False, todo
    value = str(ctx.entries[step_id])
    return True, done if value == "tak" else "Zapisane: %s." % value


def _powitanie(ctx):
    return _entry(ctx, "powitanie", "Powitanie za nami.", "Jeszcze nie zaczęliśmy.")


def _programy(ctx):
    if not ctx.run_doctor:
        return _entry(ctx, "programy", "Zapisane w kreatorze (doktor nie był uruchamiany).",
                      "Jeszcze nie sprawdzaliśmy komputera.")
    rows = doctor.checks()
    bad = [row for row in rows if not row.get("ok")]
    if not bad:
        return True, "Komputer jest gotowy (kontroli doktora: %d)." % len(rows)
    return False, "Do poprawienia: %s. Szczegóły pokaże komenda doktor." % ", ".join(str(row.get("nazwa")) for row in bad)


def _zernio(ctx):
    key = (config.env().get("ZERNIO_API_KEY") or "").strip()
    if not key:
        return False, "Brak klucza ZERNIO_API_KEY w dane/.env."
    if not zernio.KEY_CHARS.fullmatch(key):
        return False, ("Klucz w dane/.env ma niedozwolone znaki (spację, tabulator albo literę spoza ASCII). "
                       "Uruchom komendę klucz i wklej go jeszcze raz: w jednej linii, tuż za znakiem =.")
    return True, "Klucz Zernio jest w dane/.env."


def _konto(ctx):
    settings = config.settings()
    if not settings.get("ig_account_id"):
        return False, "Nie wybrano jeszcze konta Instagrama (komenda konto)."
    handle = settings.get("ig_handle")
    return True, ("Konto @%s." % handle if handle else "Konto jest zapisane.")


def _zwyciezcy(ctx):
    count = len(_active())
    if not count:
        return False, "Pula jest pusta albo wszystkie rolki są wyłączone."
    return True, "Aktywnych rolek w puli: %d." % count


def _pliki(ctx):
    active = _active()
    if not active:
        return False, "Nie ma aktywnych rolek."
    no_file, music, no_transcript = [], [], []
    for reel in active:
        code = reel["code"]
        if not (config.SRC / ("%s.mp4" % code)).is_file():
            (music if reel.get("brak_pliku") else no_file).append(code)
        elif not (config.TRANSCRIPTS / ("%s.json" % code)).is_file():
            no_transcript.append(code)
    parts = []
    if no_file:
        parts.append("Brak pliku: %s (komenda pobierz)." % _list(no_file))
    if music:
        parts.append("Zernio nie ma pliku rolek: %s (zwykle to muzyka z biblioteki Instagrama). Wrzuć oryginał jako "
                     "dane/src/KOD.mp4 albo wyłącz rolkę (active: false)." % _list(music))
    if no_transcript:
        parts.append("Brak transkrypcji: %s (komenda transkrybuj)." % _list(no_transcript))
    if parts:
        return False, " ".join(parts)
    return True, "Wszystkie aktywne rolki (%d) mają plik i transkrypcję." % len(active)


def _flagged(ctx, flag: str, todo: str, done: str):
    active = _active()
    if not active:
        return False, "Nie ma aktywnych rolek."
    lacking = [reel["code"] for reel in active if reel.get(flag) is not True]
    if lacking:
        return False, "%s: %s." % (todo, _list(lacking))
    return True, done % len(active)


def _ustawienia(ctx):
    return _flagged(ctx, "ustawienia_ok", "Ustawienia nie są jeszcze zatwierdzone dla rolek",
                    "Ustawienia zatwierdzone dla rolek: %d.")


def _hooki(ctx):
    ready, details = _flagged(ctx, "hooki_ok", "Hooki i podpisy nie są jeszcze zatwierdzone dla rolek",
                              "Hooki i podpisy zatwierdzone dla rolek: %d.")
    if not ready:
        return ready, details
    problems = candidates.validate(candidates.load_pool(), candidates.load_hooks())
    if problems:
        return False, ("Sprawdzenie puli zgłasza problemy (%d), na przykład: %s Pełną listę pokaże komenda "
                       "sprawdz-pule." % (len(problems), _sentence(problems[0])))
    return True, details + " Pula przechodzi sprawdzenie."


def _pierwsze(ctx):
    st = state.load()
    counts = Counter(v.get("status") for v in st["versions"].values())
    if versions.started(st):
        return True, "Zaplanowanych albo opublikowanych wersji: %d." % (counts["zaplanowana"] + counts["opublikowana"])
    return False, ("Żadna wersja nie jest jeszcze w Zernio. Do akceptacji: %d, zaakceptowanych: %d."
                   % (counts["do_akceptacji"], counts["zaakceptowana"]))


def _pomiar(ctx):
    return _entry(ctx, "pomiar", "Pomiar ustalony.", "Jeszcze nie ustaliliśmy, jak czytamy wyniki.")


def _tydzien(ctx):
    return _entry(ctx, "tydzien", "Paczka co tydzień ustawiona.", "Jeszcze nie ustawiliśmy paczki co tydzień.")


def _codziennie(ctx):
    return _entry(ctx, "codziennie", "Zasady na co dzień omówione.", "Jeszcze nie omówiliśmy codziennej pracy.")


CHECKS = {
    "powitanie": _powitanie, "programy": _programy, "zernio": _zernio, "konto": _konto, "zwyciezcy": _zwyciezcy,
    "pliki": _pliki, "ustawienia": _ustawienia, "hooki": _hooki, "pierwsze": _pierwsze, "pomiar": _pomiar,
    "tydzien": _tydzien, "codziennie": _codziennie,
}


def _problem(error: BaseException) -> str:
    text = " ".join(str(error).split())
    if isinstance(error, config.UserError):
        return text
    if isinstance(error, json.JSONDecodeError):
        return "uszkodzony plik z danymi: %s" % text
    return "%s: %s" % (type(error).__name__, text) if text else type(error).__name__


# --- alerty ---------------------------------------------------------------------

def _wersji(n: int) -> str:
    """Odmiana słowa „wersja” po liczbie: 1 wersja, 2-4 wersje, 5 i więcej wersji."""
    if n == 1:
        return "wersja"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "wersje"
    return "wersji"


def _tomorrow_alert(now: datetime, st: dict, ready: dict):
    if not all(ready[step_id] for step_id in IDS[:IDS.index("tydzien")]):
        return None                                   # kreator jeszcze trwa: brak triali na jutro to nie awaria
    local = now if now.tzinfo else now.replace(tzinfo=planner.TZ)
    tomorrow = local.astimezone(planner.TZ).date() + timedelta(days=1)
    if versions.planned_on(st, tomorrow):
        return None
    return "Na jutro nie ma żadnego triala. Zrób paczkę na najbliższy tydzień: komenda paczka --dni 7."


def _errors_alert(st: dict):
    count = len(versions.open_errors(st))
    if not count:
        return None
    return ("%d %s z błędem. Komenda status pokaże, które. Napraw przyczynę i uruchom paczka jeszcze raz albo odrzuć "
            "wersję komendą odrzuć ID." % (count, _wersji(count)))


def _hooks_alert(st: dict):
    """Rolka w puli bez hooków (np. dodana komendą pula) jest pomijana przez paczkę, a „Na jutro…” milczy, bo kroki 5–7
    dla niej znów są niegotowe. Alert mówi wprost, której rolce brakuje hooków. Przed pierwszymi wersjami w Zernio
    brak hooków to zwykły krok 7, więc wtedy alertu nie ma."""
    if not versions.started(st):
        return None
    names = versions.reels_without_hooks()
    if not names:
        return None
    todo = "Dopisz co najmniej %d hooki i uruchom sprawdz-pule (dla nowej rolki to krok 7)." % candidates.MIN_HOOKS
    if len(names) == 1:
        return "Rolka %s nie ma hooków w dane/hooki.json, więc paczka ją pomija. %s" % (names[0], todo)
    return "Rolki %s nie mają hooków w dane/hooki.json, więc paczka je pomija. %s" % (_list(names), todo)


def _version_alert(data: dict):
    new = str(data.get("nowa_wersja") or "").strip()
    if not new or (update.numbers(new) is not None and not update.newer(new, VERSION)):
        return None
    return ("Jest nowa wersja %s (masz %s). Komenda aktualizuj pokaże, co się zmieniło, i zaktualizuje po twojej zgodzie."
            % (new, VERSION))


def _try(make, *args):
    """Alert to dodatek: gdy jego liczenie się wywróci (uszkodzony stan zgłasza już krok „pierwsze”), jest go brak."""
    try:
        return make(*args)
    except Exception:
        return None


def _alerts(now: datetime, data: dict, ready: dict) -> list:
    try:
        st = state.load()
    except Exception:
        st = None
    found = []
    if st is not None:
        found += [_try(_tomorrow_alert, now, st, ready), _try(_errors_alert, st), _try(_hooks_alert, st)]
    found.append(_try(_version_alert, data))
    return [alert for alert in found if alert]


# --- stan kreatora --------------------------------------------------------------

def status(now: datetime, run_doctor: bool = True) -> dict:
    """Stan kreatora: {kroki: [{id, tytul, gotowy, szczegoly}], nastepny: id pierwszego niezrobionego kroku, alerty: [...]}.

    `now` to bieżący czas (ze strefą), z którego liczymy „jutro”. Przy `run_doctor=False` krok „programy” jest gotowy, gdy
    jest jego wpis w kreatorze (bez uruchamiania doktora). Niczego nie zapisuje; jedyny ślad to próbny zapis doktora
    w folderze dane (znika od razu).

    Alert o braku triali na jutro pojawia się, gdy gotowe są wszystkie kroki przed „tydzien” (kreator trwa, gdy któryś nie
    jest, więc brak triali nikogo nie dziwi). Sam krok „tydzien” nie musi być zrobiony: paczkę trzeba mieć już po pierwszych
    wersjach. Kolejne alerty: wersje z błędem, rolki bez hooków (dopiero gdy pierwsze wersje są w Zernio: paczka je pomija)
    i nowa wersja programu.
    """
    ctx = _Ctx(entries(), run_doctor)
    steps = []
    for step_id, title in STEPS:
        try:
            ready, details = CHECKS[step_id](ctx)
        except Exception as e:                         # jedna zepsuta kontrola nie może zasłonić reszty
            ready, details = False, _sentence("Nie udało się sprawdzić: %s" % _problem(e))
        steps.append({"id": step_id, "tytul": title, "gotowy": bool(ready), "szczegoly": details})
    ready_by_id = {step["id"]: step["gotowy"] for step in steps}
    return {"kroki": steps,
            "nastepny": next((step["id"] for step in steps if not step["gotowy"]), None),
            "alerty": _alerts(now, ctx.entries, ready_by_id)}
