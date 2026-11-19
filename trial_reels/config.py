"""Stałe, ścieżki i ustawienia klienta.

Ścieżki danych liczy `use_root`. Inne moduły czytają je zawsze przez `config.NAZWA`
(nigdy `from trial_reels.config import STATE`), bo `use_root` podmienia je w locie.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Kod i zasoby leżą zawsze przy kodzie. Dane klienta liczy `use_root`.
CODE = Path(__file__).resolve().parents[1]
PKG = CODE / "trial_reels"
ASSETS = CODE / "assets"

ZERNIO_BASE = "https://zernio.com/api/v1"
# Repozytorium z wydaniami (właściciel/nazwa). Adres zastępczy ma podkreślenia, których nie ma w nazwach kont na
# GitHubie, więc nigdy nie wskaże cudzego repozytorium: aktualizacja z nim odmawia (`repo_problem`), a narzędzie wydania
# nie zbuduje z nim zipa. Przed pierwszym wydaniem wpisuje się tu i w README.md prawdziwą organizację.
REPO_SLUG = "come2daddy13/trial-reels"

# Poziomy zmian w wersji rolki i ich udział (50/30/20).
LEVELS = ("subtelna", "srednia", "mocna")
LEVEL_MIX = {"subtelna": 0.5, "srednia": 0.3, "mocna": 0.2}
LEVEL_LABEL = {"subtelna": "Subtelna", "srednia": "Średnia", "mocna": "Mocna"}

STATUS_LABEL = {
    "do_akceptacji": "Do akceptacji",
    "zaakceptowana": "Zaakceptowana",
    "odrzucona": "Odrzucona",
    "zaplanowana": "Zaplanowana",
    "opublikowana": "Opublikowana",
    "blad": "Błąd",
}

MIN_LEAD_MIN = 20          # minimalny zapas przed terminem (min), żeby Zernio nie opublikował od razu
STATS_MIN_AGE_DAYS = 3     # statystyki rolki czytamy dopiero po 3 dniach od publikacji
BRAKE_DROP = 0.30          # spadek mediany wyświetleń zwykłych rolek, który włącza hamulec
BRAKE_NODATA_DAYS = 14     # po tylu dniach bez danych włączony hamulec sam się wyłącza

# Ustawienia domyślne. Klient nadpisuje je w dane/config.json.
DEFAULTS = {
    "timezone": "Europe/Warsaw",
    "day_window": ["07:15", "22:00"],
    "hours": ["09:00", "21:00"],
    "daily_max": 10,
    "brake_slot": "13:00",
    "ig_account_id": None,
    "ig_handle": None,
}

EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

# Na Windowsie podmiana pliku, który ktoś właśnie czyta (przeglądarka, antywirus), kończy się PermissionError.
# Zapis ponawiamy kilka razy po krótkiej przerwie, zanim zgłosimy błąd.
REPLACE_RETRIES = 5
REPLACE_WAIT_S = 0.1


# Nazwy na GitHubie: konto albo organizacja to do 39 liter i cyfr z pojedynczymi „-” w środku, a repozytorium to litery,
# cyfry, „.”, „-” i „_”.
_GITHUB_OWNER = re.compile(r"[A-Za-z0-9](?:-?[A-Za-z0-9])*")
_GITHUB_REPO = re.compile(r"[A-Za-z0-9._-]+")


def repo_problem(slug=None) -> str | None:
    """None, gdy `slug` (domyślnie `REPO_SLUG`) może być repozytorium na GitHubie. Inaczej jedna linia po polsku.

    Kopia programu z adresem zastępczym nie pochodzi z wydania, więc nie wolno jej pytać GitHuba o aktualizacje: pod
    zastępczą nazwą mogłoby kiedyś stanąć cudze repozytorium z cudzym kodem.
    """
    slug = REPO_SLUG if slug is None else slug
    owner, _, name = slug.partition("/") if isinstance(slug, str) else ("", "", "")
    if (len(owner) <= 39 and _GITHUB_OWNER.fullmatch(owner) and _GITHUB_REPO.fullmatch(name)
            and name not in (".", "..")):
        return None
    return ("W tej kopii programu nie ma prawdziwego adresu repozytorium z wydaniami (jest „%s”), więc nie sprawdzam "
            "ani nie instaluję aktualizacji. Napisz do opiekuna w programie." % " ".join(str(slug).split()))


def line(text) -> str:
    """Tekst w jednej linii (komunikat dla klienta nie może rozlać się na wiele linii)."""
    return " ".join(str(text).split())


class UserError(Exception):
    """Problem, który komenda opisuje klientowi jedną zrozumiałą linią (bez śladu stosu) i kończy się kodem 1."""


# Błędy, które zgłasza `ZoneInfo(nazwa)` dla nazwy, której system nie zna albo która w ogóle nie jest nazwą strefy
# (pusty napis, ścieżka, liczba, brak wartości).
ZONE_ERRORS = (ZoneInfoNotFoundError, ValueError, TypeError, OSError)


def zone_problem(zone) -> str:
    """Jedna linia o strefie czasowej, której nie da się wczytać.

    Gdy system nie zna nawet strefy domyślnej, to nie wina ustawień, tylko instalacji: na Windowsie bazę stref daje
    pakiet tzdata, a gdy nie działa, żadna strefa nie jest znana. Wtedy linia odsyła do doktora i do kroku „Programy”.
    W pozostałych przypadkach mówi, gdzie w dane/config.json poprawić nazwę i jak powinna wyglądać.
    """
    try:
        ZoneInfo(DEFAULTS["timezone"])
    except ZONE_ERRORS:
        return ("Ten komputer nie ma bazy stref czasowych (pakiet tzdata nie działa), więc nie mogę liczyć terminów. "
                "Uruchom komendę doktor i zainstaluj pakiety jeszcze raz (krok „Programy”).")
    return ("Nieznana strefa czasowa „%s” w dane/config.json. Otwórz ten plik i w polu timezone wpisz nazwę w formie "
            "Europe/Warsaw albo usuń z pliku wiersz timezone." % " ".join(str(zone).split()))


# Ścieżki danych klienta. Ustawia je `use_root` (przy imporcie i w testach).
ROOT: Path
DATA: Path
SRC: Path
OUT: Path
TRANSCRIPTS: Path
REPORTS: Path
STATE: Path
POOL: Path
HOOKS: Path
CANDIDATES: Path
WIZARD: Path
SETTINGS: Path
ENV: Path


def use_root(root: str | os.PathLike) -> None:
    """Ustawia folder klienta i przelicza wszystkie ścieżki danych (dane/…). PKG i ASSETS zostają przy kodzie."""
    global ROOT, DATA, SRC, OUT, TRANSCRIPTS, REPORTS, STATE, POOL, HOOKS, CANDIDATES, WIZARD, SETTINGS, ENV
    ROOT = Path(os.path.abspath(root))
    DATA = ROOT / "dane"
    SRC = DATA / "src"
    OUT = DATA / "wersje"
    TRANSCRIPTS = DATA / "transkrypcje"
    REPORTS = DATA / "raporty"
    STATE = DATA / "stan.json"
    POOL = DATA / "pula.json"
    HOOKS = DATA / "hooki.json"
    CANDIDATES = DATA / "kandydaci.json"
    WIZARD = DATA / "kreator.json"
    SETTINGS = DATA / "config.json"
    ENV = DATA / ".env"


use_root(os.environ.get("TRIAL_REELS_ROOT") or CODE)


# Kod rolki i numer wersji z plików w dane/ trafiają do nazw plików (dane/src/KOD.mp4, dane/wersje/TR-001.mp4), więc
# przed użyciem w ścieżce muszą mieć bezpieczny kształt: bez ukośników, kropek, dwukropków i liter spoza ASCII.
_CODE_IN_PATH = re.compile(r"[A-Za-z0-9_-]{1,64}")
_VERSION_ID = re.compile(r"TR-[0-9]{3,}")


def code_ok(code) -> bool:
    """Czy kod rolki może stać w nazwie pliku: 1–64 liter, cyfr, „-” i „_”."""
    return isinstance(code, str) and _CODE_IN_PATH.fullmatch(code) is not None


def version_id_ok(vid) -> bool:
    """Czy numer wersji ma postać TR-001 (TR- i co najmniej trzy cyfry), czyli może stać w nazwie pliku."""
    return isinstance(vid, str) and _VERSION_ID.fullmatch(vid) is not None


def checked_code(code) -> str:
    """Kod rolki do nazwy pliku albo `UserError` (jedna linia), gdy mógłby wyprowadzić ścieżkę poza folder."""
    if not code_ok(code):
        raise UserError("Kod rolki „%s” ma niedozwolone znaki albo jest za długi (kod to do 64 liter, cyfr, „-” i „_”), "
                        "więc nie użyję go w nazwie pliku. Popraw go w dane/pula.json." % line(code)[:80])
    return code


def checked_version_id(vid) -> str:
    """Numer wersji do nazwy pliku albo `UserError` (jedna linia), gdy nie ma postaci TR-001."""
    if not version_id_ok(vid):
        raise UserError("Numer wersji „%s” w dane/stan.json nie ma postaci TR-001, więc nie użyję go w nazwie pliku."
                        % line(vid)[:40])
    return vid


def within(path, folder) -> bool:
    """Czy `path` po rozwinięciu („..”, dowiązania) leży w `folder`, też po rozwinięciu (folder może być dowiązaniem)."""
    try:
        return Path(path).resolve().is_relative_to(Path(folder).resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def read_json(path, default=None):
    """Czyta plik JSON (UTF-8, z BOM lub bez). Brak pliku daje `default`; uszkodzony plik zgłasza błąd z jego ścieżką."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"{path}: {e.msg}", e.doc, e.pos) from None


def _replace(src: str, dest: Path) -> None:
    """`os.replace` z ponowieniem przy PermissionError (Windows: plik jest chwilowo otwarty przez inny program)."""
    for attempt in range(REPLACE_RETRIES + 1):
        try:
            os.replace(src, dest)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES:
                raise
            time.sleep(REPLACE_WAIT_S)


def write_json(path, obj) -> None:
    """Zapisuje JSON atomowo: najpierw plik tymczasowy obok, potem podmiana. Tworzy brakujące katalogi.

    Podmiana ponawia się do 5 razy co 0,1 s, gdy system odmawia dostępu (na Windowsie ktoś czyta plik).
    """
    path = Path(path)
    text = json.dumps(obj, ensure_ascii=False, indent=1)  # błąd serializacji wychodzi, zanim cokolwiek zapiszemy
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as f:
            tmp = f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
    except BaseException:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


SETTINGS_FIX = ("Otwórz go w edytorze i popraw albo usuń: wtedy program wraca do ustawień domyślnych (konto "
                "Instagrama wybierzesz jeszcze raz komendą konto).")


def stored_settings() -> dict:
    """Ustawienia zapisane w dane/config.json (pusty słownik, gdy pliku nie ma).

    Plik, którego nie da się wczytać jako ustawienia (zły JSON, zły układ, kodowanie inne niż UTF-8), to `UserError`
    z jedną linią po polsku: gdzie jest błąd i co zrobić. Dzięki temu zgłasza się tak samo w każdej komendzie i w
    doktorze, a nie jako ślad stosu.
    """
    try:
        data = read_json(SETTINGS, {})
    except json.JSONDecodeError as e:
        raise UserError("Plik dane/config.json jest uszkodzony (linia %d, kolumna %d). %s"
                        % (e.lineno, e.colno, SETTINGS_FIX)) from None
    except UnicodeDecodeError:
        raise UserError("Plik dane/config.json nie jest zapisany w UTF-8. %s" % SETTINGS_FIX) from None
    if not isinstance(data, dict):
        raise UserError("Plik dane/config.json ma zły układ: powinien zawierać obiekt, na przykład "
                        "{\"daily_max\": 10}. %s" % SETTINGS_FIX)
    return data


def settings() -> dict:
    """Ustawienia: DEFAULTS nadpisane wartościami z dane/config.json."""
    merged = copy.deepcopy(DEFAULTS)
    merged.update(stored_settings())
    return merged


def save_settings(updates: dict) -> dict:
    """Dopisuje `updates` do dane/config.json (trzymamy tylko to, co klient zmienił) i zwraca ustawienia po zmianie.

    Uszkodzonego pliku nie nadpisuje: zgłasza `UserError`, żeby klient nie stracił ustawień, które da się jeszcze ręcznie
    poprawić.
    """
    stored = stored_settings()
    stored.update(updates)
    write_json(SETTINGS, stored)
    return settings()


KEY_NAME = "ZERNIO_API_KEY"
PRIVATE_MODE = 0o600       # dane/.env: czyta i zapisuje tylko właściciel konta (Mac, Linux)


def private(path) -> None:
    """Na Macu i Linuksie zawęża prawa pliku do właściciela (600), gdy są szersze. Na Windowsie nic nie robi.

    Plik z kluczem założony ręcznie albo przeniesiony z Notatnika dostaje prawa z umask (zwykle 644), czyli czytają go
    też inne konta na tym komputerze. Błąd zmiany praw (np. cudzy plik) nie zatrzymuje programu.
    """
    if os.name == "nt":
        return
    try:
        if os.stat(path).st_mode & 0o077:
            os.chmod(path, PRIVATE_MODE)
    except OSError:
        pass


def _env_file(path) -> dict:
    """Wartości z pliku w formie KLUCZ=wartość (bez cudzysłowów i spacji na brzegach). Brak pliku daje pusty słownik."""
    out = {}
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def env() -> dict:
    """Czyta dane/.env (KLUCZ=wartość). Niepusty klucz ZERNIO_API_KEY ze zmiennej środowiskowej ma pierwszeństwo.

    Przy odczycie zawęża prawa pliku do właściciela (`private`).
    """
    private(ENV)
    out = _env_file(ENV)
    from_environment = os.environ.get(KEY_NAME, "").strip()    # bez spacji i końców linii, jak wartości z pliku
    if from_environment:
        out[KEY_NAME] = from_environment
    return out


def key_in_file() -> bool:
    """Czy w pliku dane/.env stoi niepusty klucz Zernio (zmiennej środowiskowej nie liczy). Treści nie wypisuje."""
    return bool(_env_file(ENV).get(KEY_NAME, "").strip())


def create_env() -> bool:
    """Tworzy dane/.env z jedną linią ZERNIO_API_KEY= (poza Windowsem z prawami 600), gdy pliku nie ma. True, gdy powstał.

    Istniejącego pliku nie nadpisuje i nie czyta: tylko zawęża jego prawa.
    """
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), PRIVATE_MODE)
    except FileExistsError:
        private(ENV)
        return False
    with os.fdopen(fd, "wb") as f:
        f.write((KEY_NAME + "=\n").encode("ascii"))
    private(ENV)
    return True


def adopt_env_txt() -> bool:
    """Notatnik bywa zapisuje dane/.env jako dane/.env.txt. Gdy w dane/.env nie ma klucza, a w .env.txt jest, przenosi
    .env.txt na miejsce .env (z prawami 600 poza Windowsem) i zwraca True. Treści żadnego z plików nie wypisuje."""
    txt = ENV.with_name(ENV.name + ".txt")
    if not txt.is_file() or key_in_file() or not _env_file(txt).get(KEY_NAME, "").strip():
        return False
    _replace(str(txt), ENV)
    private(ENV)
    return True


def ffmpeg_exe() -> str:
    """Ścieżka do ffmpeg dołączonego do paczki imageio-ffmpeg (nic nie instalujemy w systemie)."""
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def uv_exe() -> str | None:
    """Ścieżka do uv: z PATH, potem ~/.local/bin, potem ~/.cargo/bin. Gdy nigdzie go nie ma, zwraca None."""
    found = shutil.which("uv")
    if found:
        return found
    for folder in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        candidate = folder / ("uv" + EXE_SUFFIX)
        if candidate.is_file():
            return str(candidate)
    return None
