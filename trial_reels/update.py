"""Aktualizacje z wydań GitHuba: najnowsza wersja, pobranie zipa i podmiana kodu bez ruszania danych klienta.

Cała ścieżka komendy `aktualizuj` używa wyłącznie biblioteki standardowej. Na Windowsie uv nie podmieni pakietów, które
działający proces ma już załadowane (ich biblioteki .pyd i .dll są wtedy zablokowane), więc aktualizacja nie może
wczytać żadnego z nich. Z tego samego powodu doktor po aktualizacji idzie w osobnym procesie: dopiero on widzi nowy kod
i nowe pakiety.

Bezpieczeństwo:
- adresy: tylko https na api.github.com, github.com i *.githubusercontent.com, także przy przekierowaniach. Wyjątek
  to źródło wskazane zmienną TRIAL_REELS_RELEASES_URL (test na własnym serwerze): wolno otworzyć adresy z tego samego
  źródła, czyli o tym samym schemacie, hoście i porcie;
- zip: każdy wpis sprawdzamy, zanim cokolwiek zapiszemy (bez ścieżek bezwzględnych, bez „..”, bez dane/ i .venv/,
  bez krótkich nazw Windowsa z „~”), a uszkodzony zip niczego nie zmienia. Ścieżki porównujemy tak, jak widzi je system
  plików Windowsa i Maca: bez wielkości liter, bez końcowych kropek i spacji, w jednej postaci Unicode. Pliki klienta
  spoza listy PLIKI.txt aktualizacja zostawia w spokoju.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

from . import VERSION, config

ASSET_NAME = "trial-reels.zip"
RELEASES_ENV = "TRIAL_REELS_RELEASES_URL"
LIST_NAME = "PLIKI.txt"                  # lista plików wydania: z niej wiemy, co porzuciło nowe wydanie
TEMP_SUFFIX = ".aktualizacja"            # plik obok docelowego, zanim trafi na miejsce
REQUIRED = ("VERSION", "trial_reels/__init__.py")
LAST = (LIST_NAME, "VERSION")            # zapisywane na samym końcu: przerwana aktualizacja nadal pokazuje starą wersję
PROTECTED = ("dane", ".venv")            # nigdy nie nadpisujemy ani nie kasujemy

GITHUB_HOSTS = ("api.github.com", "github.com")
GITHUB_SUFFIX = ".githubusercontent.com"

TIMEOUT_S = 30
CHUNK = 1 << 20
MAX_JSON_BYTES = 5_000_000
MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_UNPACKED_BYTES = 300 * 1024 * 1024
NOTES_MAX = 4000                         # tyle znaków notatek o zmianach pokazujemy
INSTALL_TIMEOUT_S = 1800                 # pierwsze pobranie dużych pakietów trwa minuty
DOCTOR_TIMEOUT_S = 600

_TAG = re.compile(r"[vV]?\d+\.\d+\.\d+")
_NUMBERS = re.compile(r"\s*[vV]?(\d+(?:\.\d+)*)\s*")
_NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, ssl.SSLError,
                   socket.gaierror)


def _remove(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


# --- numery wersji --------------------------------------------------------------

def numbers(version) -> tuple | None:
    """Liczby z numeru wersji („v0.2.0”, „0.2.0”) albo None, gdy to nie jest numer w formie X.Y.Z (także dłuższej)."""
    match = _NUMBERS.fullmatch(version) if isinstance(version, str) else None
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def newer(tag, current) -> bool:
    """Czy wydanie `tag` jest nowsze niż `current`. Porównujemy krotki liczb, więc „v0.10.0” jest nowsze niż „0.9.9”.

    Tag, którego nie umiemy odczytać (też wydanie próbne, np. „v1.0.0-beta”), nigdy nie jest nowszy. Nieczytelna
    obecna wersja liczy się jak 0.
    """
    new, old = numbers(tag), numbers(current) or (0,)
    if new is None:
        return False
    size = max(len(new), len(old))
    return new + (0,) * (size - len(new)) > old + (0,) * (size - len(old))


# --- dozwolone adresy -----------------------------------------------------------

def _origin(url):
    """(schemat, host, port) adresu http(s) albo None, gdy adres jest nieczytelny, nie ma hosta albo ma dane logowania."""
    if not isinstance(url, str):
        return None
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    scheme, host = parts.scheme.lower(), parts.hostname or ""
    if scheme not in ("http", "https") or not host or parts.username is not None or parts.password is not None:
        return None
    return scheme, host, port or (443 if scheme == "https" else 80)


def allowed(url) -> bool:
    """Czy wolno otworzyć adres: https na GitHubie albo (test lokalny) adres z źródła zmiennej TRIAL_REELS_RELEASES_URL."""
    origin = _origin(url)
    if origin is None:
        return False
    scheme, host, port = origin
    if scheme == "https" and port == 443 and (
            host in GITHUB_HOSTS or (host.endswith(GITHUB_SUFFIX) and len(host) > len(GITHUB_SUFFIX))):
        return True
    override = os.environ.get(RELEASES_ENV)
    return bool(override) and origin == _origin(override)


def check(url) -> str:
    """Zwraca adres, gdy wolno go otworzyć. Inaczej polski komunikat (jedna linia) i `UserError`."""
    if not allowed(url):
        try:
            host = urllib.parse.urlsplit(url).hostname if isinstance(url, str) else None
        except ValueError:
            host = None
        raise config.UserError("Adres %s nie należy do GitHuba, więc go nie otwieram. Aktualizacja używa tylko adresów "
                               "https na github.com, api.github.com i *.githubusercontent.com."
                               % (host or "(nieczytelny adres)"))
    return url


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    """Przekierowanie wolno wykonać tylko na adres, który sam przeszedłby sprawdzenie `allowed`."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# --- sieć -----------------------------------------------------------------------

def _urlopen(req):
    """Jedyne miejsce, które łączy się z siecią (testy je podmieniają)."""
    return urllib.request.build_opener(_SafeRedirects()).open(req, timeout=TIMEOUT_S)


def _open(url: str, accept: str):
    check(url)
    request = urllib.request.Request(url, headers={"User-Agent": "trial-reels/%s" % VERSION, "Accept": accept})
    return _urlopen(request)


def _problem(error: BaseException) -> config.UserError:
    """Błąd sieci albo odpowiedź GitHuba z kodem błędu jako jedna zrozumiała linia."""
    if isinstance(error, urllib.error.HTTPError):
        code = error.code
        if code == 404:
            text = ("Nie znalazłem wydania programu na GitHubie (kod 404). Jeśli to się powtarza, napisz do "
                    "opiekuna w programie.")
        elif code in (403, 429):
            text = "GitHub chwilowo odmawia odpowiedzi (kod %d, zwykle to limit zapytań). Spróbuj za godzinę." % code
        elif code >= 500:
            text = "GitHub ma chwilową awarię (kod %d). Spróbuj za kilka minut." % code
        else:
            text = "GitHub odpowiedział błędem (kod %d)." % code
    else:
        text = "Nie mogę połączyć się z GitHubem. Sprawdź internet i uruchom komendę jeszcze raz."
    return config.UserError(text)


def _read(url: str, accept: str, limit: int) -> bytes:
    try:
        with _open(url, accept) as response:
            body = response.read(limit + 1)
    except config.UserError:
        raise
    except _NETWORK_ERRORS as e:
        raise _problem(e) from None
    if len(body) > limit:
        raise config.UserError("Odpowiedź GitHuba jest za duża. Spróbuj jeszcze raz za chwilę.")
    return body


def default_base() -> str:
    """Adres API wydań: ze zmiennej TRIAL_REELS_RELEASES_URL (test lokalny) albo z GitHuba.

    Kopia z adresem zastępczym repozytorium (nie z wydania) nie pyta GitHuba: `UserError` z jedną linią po polsku.
    """
    override = os.environ.get(RELEASES_ENV)
    if override:
        return override
    problem = config.repo_problem()
    if problem:
        raise config.UserError(problem)
    return "https://api.github.com/repos/%s" % config.REPO_SLUG


def latest(base: str | None = None) -> dict:
    """Najnowsze wydanie: {tag, notes, zip_url}. Pyta `GET {base}/releases/latest`, a zip to plik `trial-reels.zip`."""
    base = (base or default_base()).rstrip("/")
    raw = _read(base + "/releases/latest", "application/vnd.github+json", MAX_JSON_BYTES)
    unreadable = config.UserError("GitHub odpowiedział w nieczytelny sposób. Spróbuj jeszcze raz za chwilę.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise unreadable from None
    if not isinstance(data, dict):
        raise unreadable
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not _TAG.fullmatch(tag):
        raise config.UserError("Najnowsze wydanie ma niezrozumiały numer wersji (%s). Napisz do opiekuna w programie."
                               % config.line(repr(tag))[:40])
    assets = data.get("assets")
    asset = next((a for a in assets if isinstance(a, dict) and a.get("name") == ASSET_NAME), None) \
        if isinstance(assets, list) else None
    zip_url = asset.get("browser_download_url") if asset else None
    if not isinstance(zip_url, str) or not zip_url:
        raise config.UserError("Wydanie %s nie ma pliku %s, więc nie mam czego pobrać. Napisz do opiekuna w programie."
                               % (tag, ASSET_NAME))
    notes = str(data.get("body") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return {"tag": tag, "notes": notes, "zip_url": check(zip_url)}


def format_notes(notes) -> str:
    """Notatki o zmianach do pokazania klientowi (długie skracamy, żeby nie zalały ekranu)."""
    text = str(notes or "").strip()
    if len(text) > NOTES_MAX:
        text = text[:NOTES_MAX].rsplit("\n", 1)[0].rstrip() + "\n…"
    return text


def _announced(response):
    """Długość pliku z nagłówka Content-Length (None, gdy serwer jej nie podał albo podał bzdurę)."""
    headers = getattr(response, "headers", None)
    try:
        value = headers.get("Content-Length") if headers is not None else None
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _too_big() -> config.UserError:
    return config.UserError("Wydanie jest za duże (ponad %d MB), więc go nie pobieram. Napisz do opiekuna w programie."
                            % (MAX_ZIP_BYTES // (1024 * 1024)))


def _fetch(url: str, dest: Path) -> None:
    with _open(url, "application/octet-stream") as response:
        announced = _announced(response)
        if announced is not None and announced > MAX_ZIP_BYTES:
            raise _too_big()
        size = 0
        with open(dest, "wb") as f:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    raise _too_big()
                f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
    if announced is not None and size != announced:
        raise config.UserError("Pobieranie nie doszło do końca (pobrano %d z %d B). Uruchom komendę jeszcze raz."
                               % (size, announced))


def download(url: str, dest) -> Path:
    """Pobiera zip wydania do pliku `dest`. Przy błędzie nie zostawia niedokończonego pliku."""
    dest = Path(dest)
    try:
        _fetch(url, dest)
    except BaseException as e:
        _remove(dest)
        if isinstance(e, _NETWORK_ERRORS):
            raise _problem(e) from None
        if isinstance(e, OSError):                   # sieć jest wyżej, więc to dysk: brak miejsca, brak uprawnień
            raise config.UserError("Nie mogę zapisać pobranego pliku (%s)." % config.line(e)) from None
        raise
    return dest


# --- podmiana kodu --------------------------------------------------------------

def _key(rel: str) -> str:
    """Ścieżka do porównań tak, jak widzi ją system plików Windowsa i Maca: bez wielkości liter, bez końcowych kropek
    i spacji w nazwach (Windows je pomija) i w jednej postaci Unicode (Mac nie odróżnia „ó” od „o” z kreską)."""
    return "/".join(unicodedata.normalize("NFC", part.rstrip(" .")).casefold() for part in rel.split("/"))


def _safe_path(name: str) -> str:
    """Ścieżka wpisu zipa (z ukośnikami, bez końcowego) albo `ValueError`, gdy wychodzi poza folder programu.

    Odrzucamy ścieżki bezwzględne i z dyskiem (także UNC), dwukropek w nazwie (litera dysku, strumień NTFS), nazwy, które
    po zdjęciu końcowych kropek i spacji są puste albo są „..” (Windows czyta „.. ” i „...” jak „..”), tyldę (krótka
    nazwa 8.3, np. VENV~1 to .venv) oraz foldery klienta: dane/ i .venv/ (porównanie jak w `_key`).
    """
    text = name.replace("\\", "/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    shown = config.line(name)[:80]
    if not parts or text.startswith("/") or any(":" in part or "~" in part or not part.rstrip(" .") for part in parts):
        raise ValueError("wpis „%s” w wydaniu wychodzi poza folder programu albo ma nazwę, którą Windows czyta inaczej"
                         % shown)
    if _key(parts[0]) in PROTECTED:
        raise ValueError("wpis „%s” w wydaniu dotyka folderu, którego aktualizacja nie rusza (dane klienta)" % shown)
    return "/".join(parts)


def _entries(archive: zipfile.ZipFile) -> dict:
    """Pliki wydania jako {ścieżka: wpis}. Sprawdza każdy wpis (także foldery) i odrzuca powtórzone nazwy, także te,
    które różnią się tylko wielkością liter, końcową kropką albo postacią Unicode (na dysku to ten sam plik)."""
    files, seen = {}, set()
    for info in archive.infolist():
        rel = _safe_path(info.filename)
        if info.filename.replace("\\", "/").endswith("/"):
            continue
        if _key(rel) in seen:
            raise ValueError("w wydaniu plik %s występuje dwa razy" % rel)
        seen.add(_key(rel))
        files[rel] = info
    return files


def _test(archive: zipfile.ZipFile) -> None:
    try:
        bad = archive.testzip()
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as e:
        raise ValueError("wydanie jest uszkodzone (%s)" % type(e).__name__) from None
    if bad is not None:
        raise ValueError("plik %s w wydaniu jest uszkodzony" % bad)


def _listed(text: str) -> list:
    """Ścieżki z listy plików (jedna na linię). Linie, które nie są bezpieczną ścieżką, pomijamy."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(_safe_path(line))
        except ValueError:
            continue
    return out


def _read_bytes(path: Path):
    try:
        return path.read_bytes()
    except OSError:
        return None


def _same(dest: Path, payload: bytes) -> bool:
    try:
        return dest.is_file() and dest.stat().st_size == len(payload) and dest.read_bytes() == payload
    except OSError:
        return False


def _write(dest: Path, payload: bytes) -> None:
    """Zapis atomowo: plik obok pod inną nazwą, potem podmiana (na Windowsie z ponowieniem, gdy plik jest zajęty)."""
    tmp = dest.with_name(dest.name + TEMP_SUFFIX)
    try:
        with open(tmp, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        config._replace(tmp, dest)
    except BaseException:
        _remove(tmp)
        raise


def _prune(root: Path, folder: Path) -> None:
    """Usuwa puste foldery po skasowanych plikach, od najgłębszego w górę, ale nigdy sam folder programu."""
    while folder != root and root in folder.parents:
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


def _drop(root: Path, old: list, keep: set, undo: list) -> list:
    """Kasuje pliki ze starej listy, których nie ma w nowym wydaniu. Pliki spoza starej listy zostają.

    Przed skasowaniem zapisuje w `undo` treść pliku, żeby przerwana aktualizacja mogła go przywrócić.
    """
    removed = []
    for rel in old:
        if _key(rel) in keep:
            continue
        path = root.joinpath(*rel.split("/"))
        if path.is_file() or path.is_symlink():
            undo.append((path, _read_bytes(path)))
            path.unlink()
            removed.append(rel)
            _prune(root, path.parent)
    return sorted(removed)


def _rollback(root: Path, undo: list) -> None:
    """Cofa zapisy z `undo` od ostatniego: przywraca poprzednią treść, a pliki, które powstały, usuwa. Na ile się da."""
    for dest, old in reversed(undo):
        try:
            if old is None:
                dest.unlink()
                _prune(root, dest.parent)
            elif not _same(dest, old):
                dest.parent.mkdir(parents=True, exist_ok=True)
                _write(dest, old)
        except OSError:
            pass                                  # cofamy, ile się da: błąd przy cofaniu nie zasłania pierwotnego


def _make_executable(path: Path) -> None:
    """Zip nie pamięta bitów wykonywania, więc `trial.sh` dostaje je tu (poza Windowsem)."""
    if sys.platform != "win32" and path.is_file():
        os.chmod(path, path.stat().st_mode | 0o111)


def apply(zip_path, root) -> dict:
    """Podmienia kod programu w `root` plikami z zipa wydania i zwraca {zmienione, usuniete, wymagania}.

    Najpierw sprawdza cały zip (wpisy, wymagane pliki, sumy kontrolne), a dopiero potem pisze, więc zły zip niczego nie
    zmienia i zgłasza `ValueError`. Kopiuje każdy plik wydania (te same pliki, co już są, zostawia w spokoju), kasuje
    pliki ze starego PLIKI.txt, których nowe wydanie nie ma (reszty nie rusza), ustawia `trial.sh` jako wykonywalny
    poza Windowsem i mówi, czy zmienił się `requirements.txt`.

    Aktualizacja jest wszystko albo nic: gdy zapis albo kasowanie się nie uda (plik zajęty, brak miejsca, Ctrl+C), cofa
    to, co już zrobiła, i zgłasza błąd, więc ponowienie zaczyna od stanu sprzed aktualizacji. Kolejność ma znaczenie
    także, gdy cofnięcie się nie uda: najpierw reszta plików, potem kasowanie, a na końcu PLIKI.txt i VERSION, więc
    VERSION zmienia się jako ostatni.
    """
    root = Path(root)
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError("to nie jest poprawne archiwum zip") from None
    with archive:
        files = _entries(archive)
        for name in REQUIRED:
            if name not in files:
                raise ValueError("w wydaniu brakuje pliku %s" % name)
        if sum(info.file_size for info in files.values()) > MAX_UNPACKED_BYTES:
            raise ValueError("wydanie jest za duże po rozpakowaniu")
        _test(archive)
        try:
            new_listed = _listed(archive.read(files[LIST_NAME]).decode("utf-8-sig")) if LIST_NAME in files else []
        except UnicodeDecodeError:
            raise ValueError("lista %s w wydaniu nie jest tekstem UTF-8" % LIST_NAME) from None
        old_listed = _listed((_read_bytes(root / LIST_NAME) or b"").decode("utf-8-sig", errors="replace"))
        wanted = next((rel for rel in files if _key(rel) == "requirements.txt"), None)
        requirements = wanted is not None and archive.read(files[wanted]) != _read_bytes(root / "requirements.txt")

        def put(rel: str, undo: list) -> int:
            payload = archive.read(files[rel])
            dest = root.joinpath(*rel.split("/"))
            if _same(dest, payload):
                return 0
            undo.append((dest, _read_bytes(dest)))   # None: plik jest nowy
            dest.parent.mkdir(parents=True, exist_ok=True)
            _write(dest, payload)
            return 1

        undo = []
        try:
            changed = sum(put(rel, undo) for rel in sorted(files) if rel not in LAST)
            removed = _drop(root, old_listed, {_key(name) for name in set(files) | set(new_listed)}, undo)
            changed += sum(put(rel, undo) for rel in LAST if rel in files)
        except BaseException:
            _rollback(root, undo)
            raise
    _make_executable(root / "trial.sh")
    return {"zmienione": changed, "usuniete": removed, "wymagania": requirements}


def upgrade(info: dict, root) -> dict:
    """Pobiera zip wydania do pliku tymczasowego (poza folderem klienta), podmienia kod i na końcu sprząta plik."""
    fd, name = tempfile.mkstemp(prefix="trial-reels-", suffix=".zip")
    os.close(fd)
    try:
        download(info["zip_url"], name)
        try:
            return apply(name, root)
        except ValueError as e:
            raise config.UserError("Pobrane wydanie nie przeszło sprawdzenia (%s). Niczego nie zmieniłem." % config.line(e)) \
                from None
        except OSError as e:
            raise config.UserError("Nie udało się podmienić plików programu (%s). Zamknij programy, które mogą ich "
                                   "używać, i uruchom komendę aktualizuj --tak jeszcze raz: dokończy przerwaną "
                                   "aktualizację." % config.line(e)) from None
    finally:
        _remove(Path(name))


def installed_version(root) -> str:
    """Numer wersji z pliku VERSION w folderze programu (0.0.0, gdy pliku nie ma)."""
    try:
        return (Path(root) / "VERSION").read_text(encoding="utf-8-sig").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


# --- pakiety i doktor po aktualizacji -------------------------------------------

def venv_python(root) -> Path:
    """Python ze środowiska klienta (.venv). Gdy go nie ma, ten, którym właśnie działamy."""
    relative = ("Scripts", "python.exe") if sys.platform == "win32" else ("bin", "python")
    candidate = Path(root, ".venv", *relative)
    return candidate if candidate.is_file() else Path(sys.executable)


def _again() -> str:
    return "Pliki programu są już zaktualizowane. Uruchom jeszcze raz krok „Programy”, a doinstaluje pakiety."


def install_requirements(root) -> None:
    """Doinstalowuje pakiety z requirements.txt do środowiska klienta (uv). Porażka to `UserError` z jedną linią."""
    uv = config.uv_exe()
    if uv is None:
        raise config.UserError("Wymagane pakiety się zmieniły, ale nie znajduję programu uv. " + _again())
    command = [uv, "pip", "install", "-r", "requirements.txt", "--python", str(venv_python(root))]
    try:
        done = subprocess.run(command, cwd=root, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=INSTALL_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise config.UserError("Instalacja pakietów trwa za długo, więc ją przerwałem. " + _again()) from None
    except OSError as e:
        raise config.UserError("Nie mogę uruchomić uv (%s). %s" % (config.line(e), _again())) from None
    if done.returncode != 0:
        lines = [line for line in (done.stderr or done.stdout or "").splitlines() if line.strip()]
        raise config.UserError("Instalacja pakietów się nie udała (kod %d)%s. %s"
                               % (done.returncode, ": " + config.line(lines[-1]) if lines else "", _again()))


def run_doctor(root) -> int:
    """Uruchamia doktora w nowym procesie (nowy kod i nowe pakiety) i zwraca jego kod wyjścia. Jego wynik idzie na ekran."""
    command = [str(venv_python(root)), "-m", "trial_reels", "doktor"]
    env = {**os.environ, "PYTHONUTF8": "1"}
    try:
        return subprocess.run(command, cwd=root, env=env, timeout=DOCTOR_TIMEOUT_S, stdin=subprocess.DEVNULL).returncode
    except subprocess.TimeoutExpired:
        raise config.UserError("Doktor działa za długo, więc go przerwałem. Uruchom komendę doktor jeszcze raz.") from None
    except OSError as e:
        raise config.UserError("Nie mogę uruchomić doktora (%s). Uruchom komendę doktor jeszcze raz." % config.line(e)) from None
