"""Doktor: sprawdza, czy komputer jest gotowy do pracy z trial reels, i rozpoznaje foldery synchronizowane w chmurze.

Każda kontrola zwraca parę (czy jest dobrze, opis dla klienta). Moduł nie importuje na starcie pakietów, które mogą
być zepsute (PIL, PyAV, faster-whisper): importuje je dopiero kontrola, więc doktor działa także wtedy, gdy instalacja
jest uszkodzona, a o to właśnie ma powiedzieć.
"""
from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePath
from zoneinfo import ZoneInfo

from . import config

MIN_PYTHON = (3, 12)
MIN_EMOJI = 25
MIN_FREE_BYTES = 5 * 10**9    # 5 GB: model rozpoznawania mowy (ok. 1,6 GB), filmy źródłowe i tygodniowa paczka wersji
PACKAGES = ("faster_whisper", "PIL", "imageio_ffmpeg", "av", "filelock", "tzdata", "numpy")


# --- foldery synchronizowane ----------------------------------------------------

def synced_folder(path) -> str | None:
    """„iCloud” albo „OneDrive”, gdy ścieżka leży w folderze synchronizowanym z chmurą, w pozostałych None.

    Poznajemy to po nazwach folderów: `Library/Mobile Documents` (iCloud Drive na Macu), folder z „iCloud” w nazwie
    (iCloud na Windowsie), folder zaczynający się od „OneDrive”. Synchronizacja Biurka i Dokumentów w iCloud nie
    zmienia ścieżki, więc dla `~/Documents` i `~/Desktop` sprawdzamy, czy iCloud ma u siebie taki folder.
    """
    parts = tuple((path if isinstance(path, PurePath) else Path(path)).parts)
    lower = tuple(part.lower() for part in parts)
    for i, part in enumerate(lower):
        if part.startswith("onedrive"):
            return "OneDrive"
        if "icloud" in part or part == "com~apple~clouddocs":
            return "iCloud"
        if part == "library" and lower[i + 1: i + 2] == ("mobile documents",):
            return "iCloud"
    try:
        home = Path.home()
    except (RuntimeError, KeyError, OSError):
        return None
    home_parts = tuple(part.lower() for part in home.parts)
    for name in ("Documents", "Desktop"):
        if lower[: len(home_parts) + 1] == home_parts + (name.lower(),):
            if (home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / name).exists():
                return "iCloud"
    return None


# --- kontrole -------------------------------------------------------------------

def _reason(error: BaseException) -> str:
    """Jedna linia z nazwą błędu i jego treścią (skróconą)."""
    text = " ".join(str(error).split())
    if len(text) > 160:
        text = text[:159] + "…"
    return "%s: %s" % (type(error).__name__, text) if text else type(error).__name__


def _gb(n: int) -> str:
    """Liczba bajtów jako GB z jednym miejscem po przecinku (w dół, więc 2,96 GB nie wygląda jak „3,0”)."""
    return ("%.1f" % (n // 10**8 / 10)).replace(".", ",")


def _existing_dir(path) -> Path:
    """Najbliższy istniejący folder: sam `path`, a gdy go jeszcze nie ma, pierwszy istniejący folder nad nim."""
    path = Path(path)
    while not path.is_dir() and path != path.parent:
        path = path.parent
    return path


def _python_version() -> tuple:
    return tuple(sys.version_info[:3])


def check_python() -> tuple[bool, str]:
    version = _python_version()
    text = "%d.%d.%d" % tuple(version[:3])
    if tuple(version[:2]) >= MIN_PYTHON:
        return True, "Python %s" % text
    return False, ("Masz Python %s, a potrzebny jest 3.12 lub nowszy. Zainstaluj środowisko jeszcze raz "
                   "(krok „Programy”)." % text)


def check_packages() -> tuple[bool, str]:
    broken = []
    for name in PACKAGES:
        try:
            importlib.import_module(name)
        except Exception as e:  # nie tylko ImportError: uszkodzone koło zgłasza też błąd ładowania biblioteki
            broken.append("%s (%s)" % (name, _reason(e)))
    if broken:
        return False, "nie działają: %s. Zainstaluj pakiety jeszcze raz (krok „Programy”)." % ", ".join(broken)
    return True, "wszystkie pakiety są i działają"


def check_ffmpeg() -> tuple[bool, str]:
    try:
        done = subprocess.run([config.ffmpeg_exe(), "-hide_banner", "-encoders"], capture_output=True,
                              encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    except Exception as e:  # brak pakietu imageio-ffmpeg, brak pliku programu, zawieszenie
        return False, ("Nie mogę uruchomić ffmpeg (%s). Zainstaluj pakiety jeszcze raz (krok „Programy”)."
                       % _reason(e))
    if done.returncode == 0 and re.search(r"\blibx264\b", done.stdout or ""):
        return True, "ffmpeg ma kodek libx264 (H.264)"
    return False, ("ffmpeg z paczki nie ma kodeka libx264, więc nie zrobi filmu w H.264. Zainstaluj pakiety jeszcze raz "
                   "(krok „Programy”).")


def check_font() -> tuple[bool, str]:
    try:
        from . import render

        render.font_path()
    except FileNotFoundError as e:
        return False, str(e)
    except Exception as e:
        return False, "Nie mogę sprawdzić fontu (%s)." % _reason(e)
    return True, "Poppins Bold jest w paczce"


def check_emoji() -> tuple[bool, str]:
    try:
        from . import render

        count = len(render.emoji_set())
    except Exception as e:
        return False, "Nie mogę sprawdzić emotek (%s)." % _reason(e)
    if count >= MIN_EMOJI:
        return True, "%d emotek w paczce" % count
    return False, "W paczce jest tylko %d emotek, a potrzeba co najmniej %d. Pobierz paczkę ponownie." % (count, MIN_EMOJI)


def check_write() -> tuple[bool, str]:
    try:
        config.DATA.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=config.DATA) as probe:  # znika sam po zamknięciu
            probe.write(b"test")
    except OSError as e:
        return False, ("Nie mogę zapisać pliku w folderze dane (%s). Sprawdź, czy folder nie jest tylko do odczytu."
                       % _reason(e))
    return True, "mogę zapisywać w folderze dane"


def check_space() -> tuple[bool, str]:
    free = shutil.disk_usage(_existing_dir(config.DATA)).free
    if free >= MIN_FREE_BYTES:
        return True, "wolne miejsce: %s GB" % _gb(free)
    return False, ("Wolne jest tylko %s GB, a potrzebne są co najmniej 5 GB (sam model rozpoznawania mowy ma ok. "
                   "1,6 GB, a paczka wersji na tydzień to kolejne ok. 1,3 GB). Zwolnij miejsce na dysku." % _gb(free))


def check_folder() -> tuple[bool, str]:
    where = synced_folder(config.ROOT)
    if where is None:
        try:
            where = synced_folder(config.ROOT.resolve())  # dowiązanie do folderu w chmurze też się liczy
        except OSError:
            where = None
    if where is None:
        return True, "folder nie leży w iCloud ani w OneDrive"
    return False, ("Ten folder leży w %s. Przenieś cały folder trial-reels poza %s, na przykład do folderu "
                   "użytkownika, bo synchronizacja psuje pliki i spowalnia render." % (where, where))


def check_settings() -> tuple[bool, str]:
    """Plik dane/config.json musi dać się wczytać: poprawny JSON w UTF-8, będący obiektem. Brak pliku to ustawienia
    domyślne, więc też jest dobrze."""
    try:
        stored = config.stored_settings()
    except config.UserError as e:
        return False, " ".join(str(e).split())
    if not config.SETTINGS.is_file():
        return True, "nie ma pliku, więc działają ustawienia domyślne"
    return True, "plik jest w porządku (zapisanych ustawień: %d)" % len(stored)


def check_timezone() -> tuple[bool, str]:
    """Strefa czasowa z dane/config.json (pole timezone) musi być nazwą, którą zna system, np. Europe/Warsaw.

    Gdy samego pliku nie da się wczytać, strefy nie sprawdzamy: to ten sam jeden problem, a opisuje go kontrola ustawień
    tuż wyżej. Komendy, które działają mimo to, liczą wtedy w strefie domyślnej.
    """
    try:
        zone = config.settings().get("timezone")
    except config.UserError:
        return True, "%s (domyślna, bo plik ustawień jest uszkodzony: patrz wyżej)" % config.DEFAULTS["timezone"]
    try:
        ZoneInfo(zone)
    except config.ZONE_ERRORS:
        return False, config.zone_problem(zone)
    return True, str(zone)


def _run(name: str, check) -> dict:
    try:
        ok, info = check()
    except Exception as e:  # jedna zepsuta kontrola nie może zasłonić pozostałych
        return {"nazwa": name, "ok": False, "info": "Nie udało się sprawdzić (%s)." % _reason(e)}
    return {"nazwa": name, "ok": bool(ok), "info": info}


def checks() -> list[dict]:
    """Wszystkie kontrole jako lista {nazwa, ok, info}, w stałej kolejności.

    Sprawdza: Pythona (3.12 lub nowszy), pakiety, ffmpeg z libx264, font, co najmniej 25 emotek, zapis do dane/,
    wolne miejsce (co najmniej 5 GB), to, że folder nie leży w iCloud ani w OneDrive, że plik ustawień
    dane/config.json da się wczytać i strefę czasową z ustawień. Strefa jest ostatnia.
    """
    return [
        _run("Python 3.12 lub nowszy", check_python),
        _run("Pakiety Pythona", check_packages),
        _run("ffmpeg z kodekiem H.264", check_ffmpeg),
        _run("Font Poppins", check_font),
        _run("Emotki (co najmniej 25)", check_emoji),
        _run("Zapis w folderze dane", check_write),
        _run("Wolne miejsce (co najmniej 5 GB)", check_space),
        _run("Folder poza iCloud i OneDrive", check_folder),
        _run("Ustawienia (dane/config.json)", check_settings),
        _run("Strefa czasowa", check_timezone),
    ]
