"""Testy aktualizacji z wydań GitHuba: numery wersji, dozwolone adresy, pobieranie, podmiana plików i komenda aktualizuj.

Sieć to atrapa (`update._urlopen`), a gniazda są zablokowane, więc żaden test nie łączy się z GitHubem. Polecenia uv
i doktor też są atrapami. Nazwy plików, kody i adresy są wymyślone.
"""
import ast
import io
import json
import os
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from trial_reels import __main__ as cli
from trial_reels import config, update

REPO = Path(__file__).resolve().parents[1]
NEW = "v99.0.0"        # zawsze nowsza niż VERSION z repo
OLD = "v0.0.1"         # zawsze starsza
NOTES = "- pierwsza poprawka\n- druga poprawka"


def api_url() -> str:
    return "https://api.github.com/repos/%s/releases/latest" % config.REPO_SLUG


def zip_url(tag: str = NEW) -> str:
    return "https://github.com/%s/releases/download/%s/trial-reels.zip" % (config.REPO_SLUG, tag)


# --- atrapy ---------------------------------------------------------------------

class FakeResponse:
    """Odpowiedź serwera: treść, nagłówek Content-Length (chyba że podano inną długość) i obsługa `with`."""

    def __init__(self, body: bytes, length=None):
        self._buffer = io.BytesIO(body)
        self.headers = {} if length is False else {"Content-Length": str(len(body) if length is None else length)}

    def read(self, n=-1):
        return self._buffer.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Net:
    """Atrapa sieci: odpowiedzi z tabeli adres -> bajty albo wyjątek. Każde żądanie ląduje w `calls`."""

    def __init__(self):
        self.routes = {}
        self.calls = []

    def __call__(self, req):
        url = req.full_url
        self.calls.append(url)
        item = self.routes.get(url)
        if item is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))
        if isinstance(item, BaseException):
            raise item
        return item() if callable(item) else FakeResponse(item)


# W repo stoi adres zastępczy repozytorium, z którym aktualizacja odmawia pracy. Testy pobierania i podmiany kodu
# udają więc program z wydania, czyli z prawdziwym (wymyślonym) adresem.
EXAMPLE_REPO = "przyklad-org/trial-reels"
PLACEHOLDER_REPO = "__PRZYKLAD__/trial-reels"       # podkreśleń nie ma w nazwach kont na GitHubie


@pytest.fixture(autouse=True)
def released_copy(monkeypatch):
    monkeypatch.setattr(config, "REPO_SLUG", EXAMPLE_REPO)


@pytest.fixture(autouse=True)
def net(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("sieć w testach tylko przez atrapę")

    monkeypatch.setattr(socket, "create_connection", refuse)
    fake = Net()
    monkeypatch.setattr(update, "_urlopen", fake)
    return fake


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com/x", code, "błąd", {}, io.BytesIO(b"{}"))


# --- wydania i instalacje -------------------------------------------------------

def make_zip(path, files: dict) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return Path(path)


def release_files(tag: str = NEW, **extra) -> dict:
    files = {"VERSION": tag.lstrip("v") + "\n", "trial_reels/__init__.py": "# kod %s\n" % tag,
             "requirements.txt": "pakiet==1\n", "trial.sh": "#!/usr/bin/env bash\n# %s\n" % tag}
    files.update(extra)
    if "PLIKI.txt" not in files:
        files["PLIKI.txt"] = "".join(name + "\n" for name in sorted(files))
    return files


def release_zip_bytes(tag: str = NEW, **extra) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in release_files(tag, **extra).items():
            zf.writestr(name, content)
    return buffer.getvalue()


def release_json(tag: str = NEW, notes: str = NOTES, assets=None) -> bytes:
    if assets is None:
        assets = [{"name": "trial-reels.zip", "browser_download_url": zip_url(tag)}]
    return json.dumps({"tag_name": tag, "name": tag, "body": notes, "assets": assets}).encode("utf-8")


def publish(net, tag: str = NEW, notes: str = NOTES, assets=None, **extra) -> None:
    """Wydanie na „GitHubie”: odpowiedź API i zip z kodem."""
    net.routes[api_url()] = release_json(tag, notes, assets)
    net.routes[zip_url(tag)] = release_zip_bytes(tag, **extra)


def put(root, name: str, text: str = "") -> Path:
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def tree(root) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


def install_old(root=None, requirements: str = "pakiet==1\n") -> Path:
    """Stara instalacja w folderze klienta: kod, lista plików, dane klienta i venv."""
    root = Path(root or config.ROOT)
    put(root, "VERSION", "0.1.0\n")
    put(root, "trial_reels/__init__.py", "# stary kod\n")
    put(root, "trial_reels/zbedny.py", "# wypada z wydania\n")
    put(root, "requirements.txt", requirements)
    put(root, "trial.sh", "#!/usr/bin/env bash\n# stary\n")
    put(root, "PLIKI.txt", "VERSION\nrequirements.txt\ntrial.sh\ntrial_reels/__init__.py\ntrial_reels/zbedny.py\n")
    put(root, "dane/pula.json", '[{"code": "Cabc123XYZ_"}]')
    put(root, "dane/.env", "ZERNIO_API_KEY=testowy-klucz\n")
    put(root, "dane/kreator.json", '{"powitanie": "tak"}')
    put(root, ".venv/znacznik.txt", "venv klienta")
    return root


class Runs:
    """Atrapa `subprocess.run`: zapisuje polecenia, a kod wyjścia bierze z `codes` (uv albo doktor)."""

    def __init__(self):
        self.calls = []
        self.codes = {}

    def __call__(self, cmd, **kwargs):
        cmd = [str(part) for part in cmd]
        self.calls.append((cmd, kwargs))
        kind = "uv" if "pip" in cmd else "doktor" if "doktor" in cmd else "inne"
        code = self.codes.get(kind, 0)
        return subprocess.CompletedProcess(cmd, code, stdout="", stderr="błąd instalacji\nostatnia linia" if code else "")

    def kinds(self):
        return ["uv" if "pip" in c else "doktor" for c, _ in self.calls]


@pytest.fixture
def runs(monkeypatch):
    fake = Runs()
    monkeypatch.setattr(update.subprocess, "run", fake)
    monkeypatch.setattr(config, "uv_exe", lambda: "/zmyslony/uv")
    return fake


@pytest.fixture
def run(capsys):
    def go(*argv):
        rc = cli.main(list(argv))
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    return go


# --- numery wersji --------------------------------------------------------------

def test_newer():
    assert update.newer("v0.2.0", "0.1.9") and update.newer("v0.10.0", "0.9.9")
    assert not update.newer("v0.1.0", "0.1.0")


@pytest.mark.parametrize("tag, current, expected", [
    ("v1.0.0", "0.99.99", True),
    ("v0.1.1", "0.1.0", True),
    ("V0.2.0", "0.1.0", True),                 # wielka litera V
    ("0.2.0", "0.1.0", True),                  # bez „v”
    (" v0.2.0 ", "0.1.0\n", True),             # białe znaki z pliku VERSION
    ("v0.1.0", "0.1.1", False),                # starsza
    ("v0.9.0", "0.10.0", False),               # liczby, nie napisy
    ("v1", "0.9.9", True),                     # krótszy zapis dopełniamy zerami
    ("v1.0", "1.0.0", False),
    ("v0.2.0-beta", "0.1.0", False),           # wydanie próbne nie jest oferowane
    ("nowa", "0.1.0", False),
    ("", "0.1.0", False),
    (None, "0.1.0", False),
    ("v0.0.1", "", True),                      # nieczytelna obecna wersja liczy się jak 0
    ("v0.0.1", "nie wiem", True),
])
def test_newer_compares_numbers_not_text(tag, current, expected):
    assert update.newer(tag, current) is expected


# --- dozwolone adresy (tylko GitHub, https) -------------------------------------

@pytest.mark.parametrize("url", [
    "https://api.github.com/repos/jakas-organizacja/trial-reels/releases/latest",
    "https://github.com/jakas-organizacja/trial-reels/releases/download/v1.0.0/trial-reels.zip",
    "https://objects.githubusercontent.com/github-production-release-asset/1",
    "https://release-assets.githubusercontent.com/github-production-release-asset/2?token=abc",
    "https://API.GitHub.com/x",                # wielkość liter w nazwie hosta nie gra roli
    "https://github.com:443/x",
])
def test_github_addresses_are_allowed(url):
    assert update.allowed(url)


@pytest.mark.parametrize("url", [
    "http://api.github.com/x",                          # bez https
    "http://api.github.com:443/x",                      # port nie zastąpi schematu
    "https://example.com/trial-reels.zip",
    "https://githubusercontent.com/x",                  # sama domena, bez subdomeny
    "https://evilgithubusercontent.com/x",              # to nie subdomena
    "https://notgithub.com/x",
    "https://github.com.example.net/x",
    "https://example.net/github.com/x",
    "https://" + "github.com" + "@" + "example.net/x",  # dane logowania przed @ nie robią z hosta GitHuba
    "https://user:haslo" + "@" + "github.com/x",
    "https://github.com:8443/x",
    "https://github.com./x",
    "https://.githubusercontent.com/x",
    "ftp://github.com/x",
    "file:///etc/passwd",
    "//github.com/x",
    "github.com/x",
    "https://",
    "",
    None,
    42,
])
def test_other_addresses_are_refused(url):
    assert not update.allowed(url)


def test_check_gives_a_plain_polish_message_for_foreign_addresses():
    with pytest.raises(config.UserError) as caught:
        update.check("https://example.net/trial-reels.zip")
    text = str(caught.value)
    assert "example.net" in text and "github.com" in text and "\n" not in text
    assert update.check("https://github.com/x") == "https://github.com/x"


LOCAL = "http://127.0.0.1:8123/repos/x"


def test_release_override_allows_only_its_own_origin(monkeypatch):
    assert not update.allowed(LOCAL + "/releases/latest")      # bez zmiennej obcy adres nie przechodzi
    monkeypatch.setenv("TRIAL_REELS_RELEASES_URL", LOCAL)
    assert update.allowed(LOCAL + "/releases/latest")
    assert update.allowed("http://127.0.0.1:8123/trial-reels.zip")
    assert update.allowed("https://api.github.com/x")           # GitHub nadal przechodzi
    for other in ("http://127.0.0.1:8124/trial-reels.zip",      # inny port
                  "https://127.0.0.1:8123/trial-reels.zip",     # inny schemat
                  "http://localhost:8123/trial-reels.zip",      # inny host
                  "http://example.net:8123/trial-reels.zip"):
        assert not update.allowed(other), other


def test_empty_release_override_changes_nothing(monkeypatch):
    monkeypatch.setenv("TRIAL_REELS_RELEASES_URL", "")
    assert update.default_base() == "https://api.github.com/repos/%s" % config.REPO_SLUG
    assert not update.allowed(LOCAL)


def test_a_copy_with_the_placeholder_repo_refuses_to_look_for_updates(monkeypatch, net):
    """K1: adres zastępczy mógłby wskazywać na cudze konto, więc taka kopia nie pyta GitHuba o nic."""
    monkeypatch.setattr(config, "REPO_SLUG", PLACEHOLDER_REPO)
    with pytest.raises(config.UserError) as caught:
        update.latest()
    text = str(caught.value)
    assert "\n" not in text and "opiekun" in text and PLACEHOLDER_REPO in text
    assert net.calls == []


@pytest.mark.parametrize("flags", [[], ["--sprawdz"], ["--tak"]])
def test_aktualizuj_with_the_placeholder_repo_is_one_polish_line(monkeypatch, net, capsys, flags):
    monkeypatch.setattr(config, "REPO_SLUG", PLACEHOLDER_REPO)
    root = install_old()
    before = tree(root)
    assert cli.main(["aktualizuj", *flags]) == 1
    out, err = capsys.readouterr()
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1 and "Traceback" not in err and "opiekun" in lines[0]
    assert net.calls == [] and tree(root) == before


def test_the_local_release_server_still_works_with_the_placeholder_repo(monkeypatch):
    """Test instalacji na własnym serwerze (TRIAL_REELS_RELEASES_URL) nie potrzebuje prawdziwego adresu repozytorium."""
    monkeypatch.setattr(config, "REPO_SLUG", PLACEHOLDER_REPO)
    monkeypatch.setenv("TRIAL_REELS_RELEASES_URL", LOCAL)
    assert update.default_base() == LOCAL


def test_redirects_are_checked_against_the_same_rule():
    handler = update._SafeRedirects()
    req = urllib.request.Request(zip_url())
    moved = handler.redirect_request(req, io.BytesIO(), 302, "Found", {},
                                     "https://release-assets.githubusercontent.com/plik")
    assert moved.full_url == "https://release-assets.githubusercontent.com/plik"
    for bad in ("https://example.net/plik", "http://objects.githubusercontent.com/plik"):
        with pytest.raises(config.UserError):
            handler.redirect_request(req, io.BytesIO(), 302, "Found", {}, bad)


# --- latest ---------------------------------------------------------------------

def test_latest_parses_release_json(net):
    net.routes[api_url()] = release_json("v0.2.0", "Co nowego:\r\n- poprawka\r\n")
    info = update.latest()
    assert info == {"tag": "v0.2.0", "notes": "Co nowego:\n- poprawka", "zip_url": zip_url("v0.2.0")}
    assert net.calls == [api_url()]                      # jedno zapytanie, bez pobierania zipa


def test_latest_without_the_zip_asset_is_an_error(net):
    for assets in ([], [{"name": "inny.zip", "browser_download_url": zip_url()}], None,
                   [{"name": "trial-reels.zip"}], ["to nie obiekt"]):
        net.routes[api_url()] = json.dumps({"tag_name": NEW, "body": "x", "assets": assets}).encode("utf-8")
        with pytest.raises(config.UserError, match="trial-reels.zip"):
            update.latest()


def test_latest_tolerates_missing_notes(net):
    net.routes[api_url()] = json.dumps({"tag_name": NEW, "body": None, "assets": [
        {"name": "trial-reels.zip", "browser_download_url": zip_url()}]}).encode("utf-8")
    assert update.latest()["notes"] == ""


def test_latest_uses_the_override_base_and_explicit_base(monkeypatch, net):
    monkeypatch.setenv("TRIAL_REELS_RELEASES_URL", LOCAL + "/")
    net.routes[LOCAL + "/releases/latest"] = release_json("v0.3.0").replace(
        b"https://github.com/", b"http://127.0.0.1:8123/")
    assert update.latest()["zip_url"].startswith("http://127.0.0.1:8123/")
    assert net.calls == [LOCAL + "/releases/latest"]
    net.routes["https://api.github.com/repos/inna/trial-reels/releases/latest"] = release_json("v0.4.0")
    assert update.latest("https://api.github.com/repos/inna/trial-reels/")["tag"] == "v0.4.0"


@pytest.mark.parametrize("base", ["https://example.net/repos/x", "http://api.github.com/repos/x", "ftp://example.net"])
def test_latest_refuses_foreign_base_without_touching_the_network(base, net):
    with pytest.raises(config.UserError, match="GitHub"):
        update.latest(base)
    assert net.calls == []


def test_latest_refuses_a_zip_address_outside_github(net):
    for evil in ("https://example.net/trial-reels.zip", "http://github.com/x/trial-reels.zip"):
        net.routes[api_url()] = release_json(assets=[{"name": "trial-reels.zip", "browser_download_url": evil}])
        with pytest.raises(config.UserError, match="GitHub"):
            update.latest()
    assert net.calls == [api_url()] * 2


@pytest.mark.parametrize("tag", ["nowa", "", "v1.2", "v1.2.3.4", "v1.2.3-beta", None, 7])
def test_latest_rejects_a_strange_version_number(net, tag):
    net.routes[api_url()] = json.dumps({"tag_name": tag, "body": "", "assets": [
        {"name": "trial-reels.zip", "browser_download_url": zip_url()}]}).encode("utf-8")
    with pytest.raises(config.UserError, match="numer"):
        update.latest()


@pytest.mark.parametrize("body", [b"to nie json", b"[1, 2]", b"\xff\xfe", b"null"])
def test_latest_rejects_unreadable_answers(net, body):
    net.routes[api_url()] = body
    with pytest.raises(config.UserError, match="nieczytelny"):
        update.latest()


@pytest.mark.parametrize("error, fragment", [
    (urllib.error.URLError("brak sieci"), "połączyć się z GitHubem"),
    (TimeoutError("czas minął"), "połączyć się z GitHubem"),
    (ConnectionResetError("zerwane"), "połączyć się z GitHubem"),
    (ssl.SSLError("certyfikat"), "połączyć się z GitHubem"),
    (socket.gaierror("dns"), "połączyć się z GitHubem"),
    (http_error(404), "Nie znalazłem"),
    (http_error(403), "limit"),
    (http_error(429), "limit"),
    (http_error(503), "awarię"),
    (http_error(418), "418"),
])
def test_network_problems_are_plain_one_line_messages(net, error, fragment):
    net.routes[api_url()] = error
    with pytest.raises(config.UserError) as caught:
        update.latest()
    text = str(caught.value)
    assert fragment in text and "\n" not in text and "Traceback" not in text
    assert "Zernio" not in text                          # to nie jest błąd Zernio


def test_latest_sends_a_user_agent_and_the_github_accept_header(monkeypatch):
    seen = []

    def spy(req):
        seen.append((req.get_header("User-agent"), req.get_header("Accept")))
        return FakeResponse(release_json())

    monkeypatch.setattr(update, "_urlopen", spy)
    update.latest()
    agent, accept = seen[0]
    assert agent.startswith("trial-reels") and "github" in accept


# --- pobieranie -----------------------------------------------------------------

def test_download_writes_the_archive_to_the_destination(tmp_path, net):
    net.routes[zip_url()] = b"PK-dane-zipa" * 10
    dest = tmp_path / "pobrane.zip"
    assert update.download(zip_url(), dest) == dest
    assert dest.read_bytes() == b"PK-dane-zipa" * 10


def test_download_refuses_foreign_hosts_before_connecting(tmp_path, net):
    with pytest.raises(config.UserError, match="GitHub"):
        update.download("https://example.net/trial-reels.zip", tmp_path / "x.zip")
    assert net.calls == [] and not (tmp_path / "x.zip").exists()


def test_download_detects_a_truncated_body(tmp_path, net):
    net.routes[zip_url()] = lambda: FakeResponse(b"krotko", length=1000)
    with pytest.raises(config.UserError, match="do końca"):
        update.download(zip_url(), tmp_path / "x.zip")
    assert not (tmp_path / "x.zip").exists()                      # niedokończony plik nie zostaje


def test_download_refuses_a_huge_archive_before_and_while_reading(tmp_path, net, monkeypatch):
    monkeypatch.setattr(update, "MAX_ZIP_BYTES", 10)
    net.routes[zip_url()] = lambda: FakeResponse(b"x" * 50)                      # nagłówek mówi 50
    with pytest.raises(config.UserError, match="za duże"):
        update.download(zip_url(), tmp_path / "a.zip")
    net.routes[zip_url()] = lambda: FakeResponse(b"x" * 50, length=False)       # serwer nie podał długości
    with pytest.raises(config.UserError, match="za duże"):
        update.download(zip_url(), tmp_path / "b.zip")
    assert not (tmp_path / "a.zip").exists() and not (tmp_path / "b.zip").exists()


def test_download_maps_network_errors(tmp_path, net):
    net.routes[zip_url()] = urllib.error.URLError("brak sieci")
    with pytest.raises(config.UserError, match="połączyć się z GitHubem"):
        update.download(zip_url(), tmp_path / "x.zip")
    net.routes[zip_url()] = http_error(404)
    with pytest.raises(config.UserError, match="Nie znalazłem"):
        update.download(zip_url(), tmp_path / "y.zip")
    assert not (tmp_path / "x.zip").exists() and not (tmp_path / "y.zip").exists()


def test_download_removes_the_partial_file_when_the_connection_breaks(tmp_path, net):
    class Breaking(FakeResponse):
        def read(self, n=-1):
            data = super().read(5)
            if not data:
                raise ConnectionResetError("zerwane w trakcie")
            return data

    net.routes[zip_url()] = lambda: Breaking(b"0123456789")
    dest = tmp_path / "x.zip"
    with pytest.raises(config.UserError, match="połączyć się z GitHubem"):
        update.download(zip_url(), dest)
    assert not dest.exists()


def test_download_to_an_unwritable_place_is_a_plain_message(tmp_path, net):
    net.routes[zip_url()] = b"PK-dane" * 10
    with pytest.raises(config.UserError, match="Nie mogę zapisać"):
        update.download(zip_url(), tmp_path / "nie-ma-takiego-folderu" / "x.zip")


# --- apply: podmiana kodu bez ruszania danych -----------------------------------

def test_apply_keeps_data_and_removes_dropped_files(tmp_path):
    root = tmp_path / "klient"
    put(root, "dane/pula.json", '[{"code": "Cabc123XYZ_"}]')
    put(root, "a.py", "stare a")
    put(root, "b.py", "stare b")
    put(root, "x.txt", "nieznany plik klienta")
    put(root, "PLIKI.txt", "a.py\nb.py\n")
    new = make_zip(tmp_path / "wydanie.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "",
                                              "a.py": "nowe a", "c.py": "nowe c", "PLIKI.txt": "a.py\nc.py\n"})
    result = update.apply(new, root)
    assert (root / "a.py").read_text(encoding="utf-8") == "nowe a"
    assert (root / "c.py").read_text(encoding="utf-8") == "nowe c"
    assert not (root / "b.py").exists()
    assert (root / "x.txt").read_text(encoding="utf-8") == "nieznany plik klienta"
    assert (root / "dane" / "pula.json").read_text(encoding="utf-8") == '[{"code": "Cabc123XYZ_"}]'
    assert (root / "PLIKI.txt").read_text(encoding="utf-8") == "a.py\nc.py\n"
    assert result == {"zmienione": 5, "usuniete": ["b.py"], "wymagania": False}   # a, c, VERSION, __init__, PLIKI


def test_apply_copies_every_file_with_launchers_and_requirements(tmp_path):
    root = tmp_path / "klient"
    files = {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "x", "requirements.txt": "pakiet==2\n",
             "trial.sh": "#!/usr/bin/env bash\necho hi\n", "trial.cmd": "@echo off\r\necho hi\r\n",
             "assets/emoji/1f525.png": "obraz", "assets/zażółć.txt": "polskie litery w nazwie",
             ".claude/skills/trial-reels/SKILL.md": "# skill\n", "CLAUDE.md": "# zasady\n"}
    update.apply(make_zip(tmp_path / "w.zip", files), root)
    assert tree(root) == {name: text.encode("utf-8") for name, text in files.items()}   # także CRLF w trial.cmd


def test_apply_ignores_directory_entries(tmp_path):
    root = tmp_path / "klient"
    zip_path = tmp_path / "w.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("assets/", "")
        zf.writestr("VERSION", "0.2.0\n")
        zf.writestr("trial_reels/", "")
        zf.writestr("trial_reels/__init__.py", "")
    assert update.apply(zip_path, root)["zmienione"] == 2
    assert sorted(tree(root)) == ["VERSION", "trial_reels/__init__.py"]


@pytest.mark.parametrize("evil", [
    "../evil.py", "a/../../evil.py", "a/b/../../../evil.py", "..\\evil.py", "a\\..\\..\\evil.py",
    "/abs/evil.py", "\\abs\\evil.py", "C:/evil.py", "C:\\evil.py", "\\\\serwer\\udzial\\evil.py",
    "dysk:strumien", "a/b:c", "..",
])
def test_apply_rejects_zip_slip(tmp_path, evil):
    root = tmp_path / "klient"
    put(root, "stary.py", "stary")
    before = tree(root)
    bad = make_zip(tmp_path / "zly.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "dobry.py": "ok",
                                          evil: "zly"})
    with pytest.raises(ValueError):
        update.apply(bad, root)
    assert tree(root) == before                      # nic nie zostało zapisane, także dobry.py sprzed złego wpisu
    assert not (tmp_path / "evil.py").exists()


@pytest.mark.parametrize("evil", [
    "dane/pula.json", "dane/", "dane", "Dane/Pula.json", "DANE/.env", "dane./x.json", "dane /x.json",
    ".venv/bin/python", ".venv/lib/x.py", ".VENV/x", ".venv",
])
def test_apply_rejects_data_paths(tmp_path, evil):
    root = tmp_path / "klient"
    put(root, "dane/pula.json", "[1]")
    put(root, ".venv/znacznik.txt", "venv")
    before = tree(root)
    bad = make_zip(tmp_path / "zly.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", evil: "nadpisanie"})
    with pytest.raises(ValueError):
        update.apply(bad, root)
    assert tree(root) == before


@pytest.mark.parametrize("evil", [
    "VENV~1/x.py", "DANE~1/pula.json", "trial_reels/MODUL~1.PY",             # krótkie nazwy 8.3 Windowsa
    ".../evil.py", ".. /evil.py", "a/. ./evil.py", "a/ /x.py", "a/../../x.py",  # „..” i nazwy z samych kropek i spacji
    "trial_reels/x.py:Zone.Identifier",                                        # strumień NTFS
])
def test_apply_rejects_windows_aliases_and_names_made_of_dots(tmp_path, evil):
    """D8: Windows ignoruje końcowe kropki i spacje, a VENV~1 to inna nazwa folderu .venv."""
    root = tmp_path / "klient"
    put(root, "stary.py", "stary")
    put(root, ".venv/znacznik.txt", "venv")
    before = tree(root)
    bad = make_zip(tmp_path / "zly.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", evil: "zly"})
    with pytest.raises(ValueError):
        update.apply(bad, root)
    assert tree(root) == before


@pytest.mark.parametrize("first,second", [
    ("a.py", "A.py"), ("a.py", "a.py."), ("a.py", "a.py "), ("dir/x.py", "DIR/X.PY"),
    ("zółw.py", "zo\u0301\u0142w.py"),                                     # ta sama nazwa w dwóch postaciach Unicode
])
def test_apply_rejects_two_entries_that_are_one_file_on_windows_or_a_mac(tmp_path, first, second):
    root = tmp_path / "klient"
    put(root, "stary.py", "stary")
    before = tree(root)
    bad = make_zip(tmp_path / "zly.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", first: "1", second: "2"})
    with pytest.raises(ValueError, match="dwa razy"):
        update.apply(bad, root)
    assert tree(root) == before


def test_apply_keeps_a_file_whose_old_name_differs_only_in_case(tmp_path):
    root = tmp_path / "klient"
    put(root, "VERSION", "0.1.0\n")
    put(root, "trial_reels/__init__.py", "# stary\n")
    put(root, "Modul.py", "stary")
    put(root, "PLIKI.txt", "Modul.py\nVERSION\ntrial_reels/__init__.py\n")
    new = make_zip(tmp_path / "w.zip", release_files("v0.2.0", **{"modul.py": "nowy"}))
    assert update.apply(new, root)["usuniete"] == []
    assert (root / "modul.py").read_text(encoding="utf-8") == "nowy"


def test_apply_notices_new_requirements_whatever_the_case_of_the_file_name(tmp_path):
    root = install_old(tmp_path / "klient")
    files = release_files("v0.2.0")
    del files["requirements.txt"]
    files["Requirements.txt"] = "pakiet==2\n"
    files["PLIKI.txt"] = "".join(name + "\n" for name in sorted(n for n in files if n != "PLIKI.txt"))
    assert update.apply(make_zip(tmp_path / "w.zip", files), root)["wymagania"] is True


def test_apply_error_messages_are_polish_and_one_line(tmp_path):
    bad = make_zip(tmp_path / "zly.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "../evil.py": "x"})
    with pytest.raises(ValueError) as caught:
        update.apply(bad, tmp_path / "klient")
    assert "evil.py" in str(caught.value) and "\n" not in str(caught.value)


@pytest.mark.parametrize("missing", ["VERSION", "trial_reels/__init__.py"])
def test_apply_requires_version_and_the_package_init(tmp_path, missing):
    root = tmp_path / "klient"
    put(root, "stary.py", "stary")
    before = tree(root)
    files = {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "nowy.py": "x"}
    del files[missing]
    with pytest.raises(ValueError, match=missing.split("/")[-1].replace(".", r"\.")):
        update.apply(make_zip(tmp_path / "w.zip", files), root)
    assert tree(root) == before


def test_apply_rejects_files_that_are_not_archives(tmp_path):
    junk = tmp_path / "smiec.zip"
    junk.write_bytes(b"<html>to nie jest zip</html>")
    root = tmp_path / "klient"
    put(root, "stary.py", "stary")
    before = tree(root)
    with pytest.raises(ValueError, match="zip"):
        update.apply(junk, root)
    assert tree(root) == before


def test_apply_rejects_a_damaged_archive_before_writing_anything(tmp_path):
    zip_path = tmp_path / "w.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("VERSION", "0.2.0\n")
        zf.writestr("trial_reels/__init__.py", "")
        zf.writestr("a.py", "abcdefghij")
    raw = zip_path.read_bytes()
    assert raw.count(b"abcdefghij") == 1
    zip_path.write_bytes(raw.replace(b"abcdefghij", b"abcdeXghij"))               # ten sam rozmiar, zły CRC
    root = tmp_path / "klient"
    put(root, "stary.py", "stary")
    before = tree(root)
    with pytest.raises(ValueError, match="uszkodzony"):
        update.apply(zip_path, root)
    assert tree(root) == before


def test_apply_rejects_a_duplicated_entry(tmp_path):
    zip_path = tmp_path / "w.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("VERSION", "0.2.0\n")
        zf.writestr("trial_reels/__init__.py", "")
        with pytest.warns(UserWarning):                                             # zipfile sam ostrzega o powtórce
            zf.writestr("a.py", "jeden")
            zf.writestr("a.py", "dwa")
    with pytest.raises(ValueError, match="dwa razy"):
        update.apply(zip_path, tmp_path / "klient")


def test_apply_refuses_an_absurdly_large_release(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "MAX_UNPACKED_BYTES", 100)
    root = tmp_path / "klient"
    bad = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "duzy.bin": "x" * 500})
    with pytest.raises(ValueError, match="duże"):
        update.apply(bad, root)
    assert not root.exists()


def test_apply_never_deletes_protected_or_foreign_paths_named_in_the_old_list(tmp_path):
    root = tmp_path / "klient"
    put(root, "dane/pula.json", "[1]")
    put(root, ".venv/lib/x.py", "venv")
    put(root, "a.py", "stare a")
    put(tmp_path, "poza.txt", "poza folderem klienta")
    absolute = put(tmp_path, "bezwzgledny.txt", "ścieżka bezwzględna")
    put(root, "PLIKI.txt", "dane/pula.json\n.venv/lib/x.py\n../poza.txt\n%s\nC:/x\na.py\n\n  \n" % absolute.as_posix())
    new = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "PLIKI.txt": "VERSION\n"})
    result = update.apply(new, root)
    assert (root / "dane" / "pula.json").is_file() and (root / ".venv" / "lib" / "x.py").is_file()
    assert (tmp_path / "poza.txt").is_file() and absolute.is_file()
    assert result["usuniete"] == ["a.py"] and not (root / "a.py").exists()


def test_apply_keeps_a_listed_file_that_the_new_release_ships(tmp_path):
    root = tmp_path / "klient"
    put(root, "PLIKI.txt", "stary.py\ndrugi.py\n")
    put(root, "stary.py", "stary")
    put(root, "drugi.py", "drugi")
    new = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "stary.py": "nowy",
                                        "PLIKI.txt": "VERSION\ntrial_reels/__init__.py\n"})   # stary.py nie ma na liście
    result = update.apply(new, root)
    assert (root / "stary.py").read_text(encoding="utf-8") == "nowy"               # plik z zipa nie może zniknąć
    assert result["usuniete"] == ["drugi.py"]


def test_apply_does_not_delete_a_file_renamed_only_by_case(tmp_path):
    root = tmp_path / "klient"
    put(root, "a.py", "stare")
    put(root, "PLIKI.txt", "a.py\n")
    new = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "A.py": "nowe",
                                        "PLIKI.txt": "A.py\n"})
    assert update.apply(new, root)["usuniete"] == []
    assert (root / "a.py").exists() and (root / "A.py").read_text(encoding="utf-8") == "nowe"   # na każdym systemie


def test_apply_prunes_folders_left_empty_by_removed_files(tmp_path):
    root = tmp_path / "klient"
    put(root, "stare/gleboko/x.py", "x")
    put(root, "zostaje/y.py", "y")
    put(root, "zostaje/z.py", "z")
    put(root, "PLIKI.txt", "stare/gleboko/x.py\nzostaje/y.py\nzostaje/z.py\n")
    new = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "",
                                        "zostaje/z.py": "z", "PLIKI.txt": "zostaje/z.py\n"})
    result = update.apply(new, root)
    assert result["usuniete"] == ["stare/gleboko/x.py", "zostaje/y.py"]
    assert not (root / "stare").exists()
    assert (root / "zostaje" / "z.py").is_file() and root.is_dir()


@pytest.mark.parametrize("old, new, expected", [
    ("pakiet==1\n", "pakiet==1\n", False),
    ("pakiet==1\n", "pakiet==2\n", True),
    (None, "pakiet==1\n", True),                 # pierwsza instalacja potrzebuje pakietów
    ("pakiet==1\n", None, False),                # wydanie bez listy niczego nie zmienia
])
def test_apply_reports_changed_requirements(tmp_path, old, new, expected):
    root = tmp_path / "klient"
    if old is not None:
        put(root, "requirements.txt", old)
    files = {"VERSION": "0.2.0\n", "trial_reels/__init__.py": ""}
    if new is not None:
        files["requirements.txt"] = new
    assert update.apply(make_zip(tmp_path / "w.zip", files), root)["wymagania"] is expected


def test_apply_skips_identical_files_and_does_not_touch_them(tmp_path):
    root = tmp_path / "klient"
    new = make_zip(tmp_path / "w.zip", release_files("v0.2.0"))
    assert update.apply(new, root)["zmienione"] == 5
    stamp = 1_000_000_000
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (stamp, stamp))
    again = update.apply(new, root)
    assert again == {"zmienione": 0, "usuniete": [], "wymagania": False}
    assert all(int(p.stat().st_mtime) == stamp for p in root.rglob("*") if p.is_file())


@pytest.mark.skipif(sys.platform == "win32", reason="bity wykonywania są tylko na Macu i Linuksie")
def test_apply_makes_the_launcher_executable_even_when_unchanged(tmp_path):
    root = tmp_path / "klient"
    files = release_files("v0.2.0")
    put(root, "trial.sh", files["trial.sh"]).chmod(0o644)                          # ta sama treść, brak bitu x
    update.apply(make_zip(tmp_path / "w.zip", files), root)
    assert (root / "trial.sh").stat().st_mode & 0o111 == 0o111


def test_apply_works_in_a_path_with_polish_letters_and_spaces(tmp_path):
    root = tmp_path / "Łukasz Ząb" / "Łódź ąę" / "trial-reels"
    put(root, "dane/pula.json", "[]")
    put(root, "PLIKI.txt", "stary-żółć.py\n")
    put(root, "stary-żółć.py", "x")
    new = make_zip(tmp_path / "wydanie ąę.zip", release_files("v0.2.0", **{"assets/zażółć gęślą.txt": "tekst"}))
    result = update.apply(new, root)
    assert result["usuniete"] == ["stary-żółć.py"]
    assert (root / "assets" / "zażółć gęślą.txt").read_text(encoding="utf-8") == "tekst"
    assert (root / "dane" / "pula.json").read_text(encoding="utf-8") == "[]"


def test_apply_leaves_no_temporary_files_even_when_a_replace_fails(tmp_path, monkeypatch):
    root = tmp_path / "klient"
    new = make_zip(tmp_path / "w.zip", release_files("v0.2.0"))
    real = config._replace

    def fail_on_version(src, dest):
        if Path(dest).name == "VERSION":
            raise PermissionError("plik jest otwarty w innym programie")
        real(src, dest)

    monkeypatch.setattr(config, "_replace", fail_on_version)
    with pytest.raises(PermissionError):
        update.apply(new, root)
    assert not [p for p in root.rglob("*") if p.name.endswith(update.TEMP_SUFFIX)]


@pytest.mark.parametrize("failing", ["a.py", "trial_reels/__init__.py", "requirements.txt", "PLIKI.txt", "VERSION"])
def test_a_failed_apply_puts_everything_back_and_a_second_run_finishes_the_job(tmp_path, monkeypatch, failing):
    root = tmp_path / "klient"
    put(root, "VERSION", "0.1.0\n")
    put(root, "trial_reels/__init__.py", "# stary\n")
    put(root, "requirements.txt", "pakiet==1\n")
    put(root, "b.py", "stary b")
    put(root, "PLIKI.txt", "VERSION\nb.py\nrequirements.txt\ntrial_reels/__init__.py\n")
    put(root, "dane/pula.json", "[1]")
    before = tree(root)
    new = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "# nowy\n", "a.py": "nowy a",
                                        "requirements.txt": "pakiet==2\n",
                                        "PLIKI.txt": "VERSION\na.py\nrequirements.txt\ntrial_reels/__init__.py\n"})
    real = config._replace

    def fail(src, dest):
        if Path(dest).as_posix().endswith(failing):
            raise PermissionError("plik jest otwarty w innym programie")
        real(src, dest)

    monkeypatch.setattr(config, "_replace", fail)
    with pytest.raises(PermissionError):
        update.apply(new, root)
    monkeypatch.setattr(config, "_replace", real)
    assert tree(root) == before                                         # wszystko jak przed aktualizacją
    assert update.installed_version(root) == "0.1.0" and not list(root.rglob("*" + update.TEMP_SUFFIX))
    result = update.apply(new, root)                                    # to samo wydanie jeszcze raz robi całą robotę
    assert result["wymagania"] is True and result["usuniete"] == ["b.py"]
    assert update.installed_version(root) == "0.2.0" and (root / "a.py").is_file() and not (root / "b.py").exists()


def test_version_and_the_file_list_are_written_last_even_when_the_rollback_cannot_help(tmp_path, monkeypatch):
    """Gdyby cofnięcie też się nie udało, VERSION nadal jest stary, więc `aktualizuj` da się ponowić."""
    root = tmp_path / "klient"
    put(root, "VERSION", "0.1.0\n")
    put(root, "PLIKI.txt", "VERSION\n")
    new = make_zip(tmp_path / "w.zip", release_files("v0.2.0"))
    real = config._replace

    def fail(src, dest):
        if Path(dest).as_posix().endswith("trial_reels/__init__.py"):
            raise PermissionError("zajęty")
        real(src, dest)

    monkeypatch.setattr(config, "_replace", fail)
    monkeypatch.setattr(update, "_rollback", lambda root, undo: None)
    with pytest.raises(PermissionError):
        update.apply(new, root)
    assert update.installed_version(root) == "0.1.0"
    assert (root / "PLIKI.txt").read_text(encoding="utf-8") == "VERSION\n"


def test_a_failure_while_removing_old_files_restores_the_ones_already_removed(tmp_path, monkeypatch):
    root = tmp_path / "klient"
    put(root, "b.py", "stary b")
    put(root, "c.py", "stary c")
    put(root, "PLIKI.txt", "b.py\nc.py\n")
    before = tree(root)
    new = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "a.py": "nowy a",
                                        "PLIKI.txt": "a.py\n"})
    real = Path.unlink

    def unlink(self, *args, **kwargs):
        if self.name == "c.py":
            raise PermissionError("zajęty")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(PermissionError):
        update.apply(new, root)
    monkeypatch.setattr(Path, "unlink", real)
    assert tree(root) == before


def test_ctrl_c_in_the_middle_of_apply_also_puts_everything_back(tmp_path, monkeypatch):
    root = tmp_path / "klient"
    put(root, "VERSION", "0.1.0\n")
    put(root, "PLIKI.txt", "VERSION\n")
    before = tree(root)
    new = make_zip(tmp_path / "w.zip", release_files("v0.2.0"))
    real = config._replace

    def interrupted(src, dest):
        if Path(dest).name == "VERSION":                                # reszta jest już na miejscu
            raise KeyboardInterrupt
        real(src, dest)

    monkeypatch.setattr(config, "_replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        update.apply(new, root)
    monkeypatch.setattr(config, "_replace", real)
    assert tree(root) == before and not (root / "trial_reels").exists()   # także nowe foldery znikają


def test_apply_removes_dropped_files_only_after_the_new_ones_are_in_place(tmp_path, monkeypatch):
    root = tmp_path / "klient"
    put(root, "b.py", "stary b")
    put(root, "PLIKI.txt", "b.py\n")
    new = make_zip(tmp_path / "w.zip", {"VERSION": "0.2.0\n", "trial_reels/__init__.py": "", "a.py": "nowy a",
                                        "PLIKI.txt": "a.py\n"})
    real = config._replace

    def fail_on_a(src, dest):
        if Path(dest).name == "a.py":
            raise PermissionError("zajęty")
        real(src, dest)

    monkeypatch.setattr(config, "_replace", fail_on_a)
    with pytest.raises(PermissionError):
        update.apply(new, root)
    assert (root / "b.py").is_file()                                    # stary plik zostaje, dopóki nowe nie weszły


def test_installed_version_reads_the_version_file(tmp_path):
    assert update.installed_version(tmp_path) == "0.0.0"
    put(tmp_path, "VERSION", "\ufeff1.2.3\r\n")
    assert update.installed_version(tmp_path) == "1.2.3"


# --- wspólny interpreter, uv i doktor -------------------------------------------

def test_venv_python_prefers_the_client_venv(tmp_path):
    assert update.venv_python(tmp_path) == Path(sys.executable)                     # brak .venv: bieżący interpreter
    relative = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    put(tmp_path, ".venv/" + relative)
    assert update.venv_python(tmp_path) == tmp_path / ".venv" / relative


def test_install_requirements_runs_uv_for_the_client_venv(tmp_path, runs):
    update.install_requirements(tmp_path)
    (cmd, kwargs), = runs.calls
    assert cmd == ["/zmyslony/uv", "pip", "install", "-r", "requirements.txt", "--python",
                   str(update.venv_python(tmp_path))]
    assert Path(kwargs["cwd"]) == tmp_path and kwargs["encoding"] == "utf-8" and kwargs["errors"] == "replace"


def test_install_requirements_failure_says_the_files_are_already_updated(tmp_path, runs):
    runs.codes["uv"] = 2
    with pytest.raises(config.UserError) as caught:
        update.install_requirements(tmp_path)
    text = str(caught.value)
    assert "zaktualizowane" in text and "ostatnia linia" in text and "\n" not in text


def test_install_requirements_without_uv_is_a_plain_message(tmp_path, runs, monkeypatch):
    monkeypatch.setattr(config, "uv_exe", lambda: None)
    with pytest.raises(config.UserError, match="uv"):
        update.install_requirements(tmp_path)
    assert runs.calls == []


def test_install_requirements_timeout_is_a_plain_message(tmp_path, monkeypatch):
    def hang(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(update.subprocess, "run", hang)
    monkeypatch.setattr(config, "uv_exe", lambda: "/zmyslony/uv")
    with pytest.raises(config.UserError, match="za długo"):
        update.install_requirements(tmp_path)


def test_run_doctor_starts_a_fresh_process_with_utf8(tmp_path, runs):
    assert update.run_doctor(tmp_path) == 0
    (cmd, kwargs), = runs.calls
    assert cmd[1:] == ["-m", "trial_reels", "doktor"] and cmd[0] == str(update.venv_python(tmp_path))
    assert Path(kwargs["cwd"]) == tmp_path and kwargs["env"]["PYTHONUTF8"] == "1"
    runs.codes["doktor"] = 1
    assert update.run_doctor(tmp_path) == 1


# --- komenda aktualizuj ---------------------------------------------------------

def test_aktualizuj_without_consent_shows_notes_and_changes_nothing(run, net, runs):
    install_old()
    publish(net)
    before = tree(config.ROOT)
    rc, out, err = run("aktualizuj")
    assert rc == 0 and err == ""
    assert NEW in out and "- pierwsza poprawka" in out and "- druga poprawka" in out
    assert "aktualizuj --tak" in out
    assert tree(config.ROOT) == before                  # nic nie zmienione, kreator.json bez nowego wpisu
    assert net.calls == [api_url()] and runs.calls == []   # zip nie został nawet pobrany


def test_aktualizuj_truncates_very_long_notes(run, net):
    install_old()
    publish(net, notes="Linia numer jeden\n" * 1000)
    rc, out, _ = run("aktualizuj")
    assert rc == 0 and len(out) < 6000 and "…" in out


def test_aktualizuj_check_saves_the_new_version_for_the_wizard(run, net, runs):
    install_old()
    publish(net)
    rc, out, err = run("aktualizuj", "--sprawdz")
    assert rc == 0 and err == "" and NEW in out
    assert config.read_json(config.WIZARD) == {"powitanie": "tak", "nowa_wersja": NEW}
    assert (config.ROOT / "VERSION").read_text(encoding="utf-8") == "0.1.0\n"
    assert net.calls == [api_url()] and runs.calls == []


def test_aktualizuj_check_creates_the_wizard_file_when_missing(run, net):
    publish(net)
    assert run("aktualizuj", "--sprawdz")[0] == 0
    assert config.read_json(config.WIZARD) == {"nowa_wersja": NEW}


def test_aktualizuj_check_clears_a_stale_note_when_up_to_date(run, net):
    install_old()
    config.write_json(config.WIZARD, {"powitanie": "tak", "nowa_wersja": "v0.0.5"})
    publish(net, tag=OLD)
    rc, out, _ = run("aktualizuj", "--sprawdz")
    assert rc == 0 and "najnowszą wersję" in out
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}


def test_aktualizuj_when_up_to_date_does_nothing(run, net, runs):
    install_old()
    publish(net, tag=OLD)
    before = tree(config.ROOT)
    rc, out, _ = run("aktualizuj", "--tak")
    assert rc == 0 and "najnowszą wersję" in out
    assert tree(config.ROOT) == before and runs.calls == [] and net.calls == [api_url()]


def test_a_damaged_wizard_file_does_not_stop_the_update(run, net, runs):
    root = install_old(requirements="pakiet==0\n")
    config.WIZARD.write_text("{nie json", encoding="utf-8")
    publish(net)
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 0, err
    assert (root / "VERSION").read_text(encoding="utf-8") == "99.0.0\n" and runs.kinds() == ["uv", "doktor"]


def test_a_damaged_wizard_file_does_not_hide_that_we_are_up_to_date(run, net):
    install_old()
    config.WIZARD.write_text("{nie json", encoding="utf-8")
    publish(net, tag=OLD)
    rc, out, err = run("aktualizuj")
    assert rc == 0 and "najnowszą wersję" in out


def damage_settings(text="{nie json"):
    config.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("bad", ["{nie json", "[]", '{"timezone": "Marsjańska/Olympus"}', '{"timezone": 7}'])
def test_aktualizuj_works_with_damaged_settings_or_a_bad_time_zone(run, net, bad):
    """Aktualizacja bywa właśnie lekarstwem na błąd, więc nie może zatrzymać się na pliku, który ma naprawić doktor."""
    install_old()
    damage_settings(bad)
    publish(net)
    rc, out, err = run("aktualizuj")
    assert rc == 0 and err == "" and NEW in out and "aktualizuj --tak" in out
    rc, out, err = run("aktualizuj", "--sprawdz")
    assert rc == 0 and err == "" and config.read_json(config.WIZARD) == {"powitanie": "tak", "nowa_wersja": NEW}
    assert config.SETTINGS.read_text(encoding="utf-8") == bad                 # plik klienta zostaje, jaki był


@pytest.mark.parametrize("bad", ["{nie json", '{"timezone": "Marsjańska/Olympus"}'])
def test_aktualizuj_yes_replaces_the_code_even_with_damaged_settings_or_a_bad_time_zone(run, net, runs, bad):
    root = install_old()
    damage_settings(bad)
    publish(net)
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 0, err
    assert (root / "VERSION").read_text(encoding="utf-8") == "99.0.0\n" and runs.kinds() == ["doktor"]
    assert config.SETTINGS.read_text(encoding="utf-8") == bad


def test_aktualizuj_check_and_yes_together_are_refused(run, net):
    publish(net)
    rc, out, err = run("aktualizuj", "--sprawdz", "--tak")
    assert rc == 1 and "--sprawdz" in err and "--tak" in err and "Traceback" not in err
    assert net.calls == []


def test_aktualizuj_yes_replaces_code_and_keeps_client_data(run, net, runs):
    root = install_old()
    publish(net)
    config.write_json(config.WIZARD, {"powitanie": "tak", "nowa_wersja": NEW})
    data_before = {k: v for k, v in tree(root).items() if k.startswith(("dane/", ".venv/"))}
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 0, err
    assert (root / "VERSION").read_text(encoding="utf-8") == "99.0.0\n"
    assert (root / "trial_reels" / "__init__.py").read_text(encoding="utf-8") == "# kod v99.0.0\n"
    assert not (root / "trial_reels" / "zbedny.py").exists()                       # był na starej liście, nie ma na nowej
    after = tree(root)
    assert json.loads(after.pop("dane/kreator.json").decode("utf-8")) == {"powitanie": "tak"}   # nowa_wersja zniknęło
    data_before.pop("dane/kreator.json")
    assert {k: v for k, v in after.items() if k.startswith(("dane/", ".venv/"))} == data_before
    assert "99.0.0" in out and "dane" in out
    assert runs.kinds() == ["doktor"]                                               # wymagania bez zmian: tylko doktor
    assert net.calls == [api_url(), zip_url()]


def test_aktualizuj_downloads_to_a_temporary_file_outside_the_client_folder(run, net, runs, monkeypatch):
    root = install_old()
    publish(net)
    seen = []
    real = update.download

    def spy(url, dest):
        seen.append(Path(dest))
        return real(url, dest)

    monkeypatch.setattr(update, "download", spy)
    assert run("aktualizuj", "--tak")[0] == 0
    (path,) = seen
    assert root not in path.parents and path.suffix == ".zip"
    assert not path.exists()                                                        # po podmianie plik znika
    assert not [p for p in root.rglob("*.zip")]


def test_aktualizuj_yes_installs_packages_when_requirements_changed(run, net, runs):
    root = install_old(requirements="pakiet==0\n")
    publish(net)
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 0, err
    assert runs.kinds() == ["uv", "doktor"]                                         # najpierw pakiety, na końcu doktor
    uv, doktor = (cmd for cmd, _ in runs.calls)
    assert uv[1:] == ["pip", "install", "-r", "requirements.txt", "--python", str(update.venv_python(root))]
    assert doktor[1:] == ["-m", "trial_reels", "doktor"]
    assert "pakiet" in out.lower() and "doktor" in out.lower()


def test_aktualizuj_failed_package_install_gives_code_1_and_skips_the_doctor(run, net, runs):
    install_old(requirements="pakiet==0\n")
    publish(net)
    runs.codes["uv"] = 1
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 1 and "zaktualizowane" in err and "Traceback" not in err
    assert runs.kinds() == ["uv"]
    assert (config.ROOT / "VERSION").read_text(encoding="utf-8") == "99.0.0\n"       # pliki są już nowe


def test_aktualizuj_doctor_problems_give_code_1(run, net, runs):
    install_old()
    publish(net)
    runs.codes["doktor"] = 1
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 1 and "doktor" in (out + err).lower()
    assert (config.ROOT / "VERSION").read_text(encoding="utf-8") == "99.0.0\n"


def test_aktualizuj_with_a_bad_archive_changes_nothing_and_cleans_up(run, net, runs, monkeypatch):
    root = install_old()
    net.routes[api_url()] = release_json()
    net.routes[zip_url()] = make_zip(root.parent / "zly.zip", {"VERSION": "99.0.0\n", "trial_reels/__init__.py": "",
                                                               "../evil.py": "x"}).read_bytes()
    seen = []
    real = update.download
    monkeypatch.setattr(update, "download", lambda url, dest: seen.append(Path(dest)) or real(url, dest))
    before = tree(root)
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 1 and "evil.py" in err and "Niczego nie zmieniłem" in err and "Traceback" not in err
    assert tree(root) == before and runs.calls == []
    assert seen and not seen[0].exists()


def test_aktualizuj_with_a_locked_file_says_so_and_a_second_run_finishes_the_job(run, net, runs, monkeypatch):
    root = install_old(requirements="pakiet==0\n")
    publish(net)
    seen = []
    real_download, real_replace = update.download, config._replace
    monkeypatch.setattr(update, "download", lambda url, dest: seen.append(Path(dest)) or real_download(url, dest))

    def locked(src, dest):
        if Path(dest).name == "trial.sh":
            raise PermissionError("[Errno 13] Permission denied: trial.sh")
        real_replace(src, dest)

    monkeypatch.setattr(config, "_replace", locked)
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 1 and "Nie udało się podmienić" in err and "aktualizuj --tak" in err and "Traceback" not in err
    assert len([line for line in err.splitlines() if line.strip()]) == 1
    assert (root / "VERSION").read_text(encoding="utf-8") == "0.1.0\n"        # wersja nie skoczyła, więc da się powtórzyć
    assert runs.calls == [] and not seen[0].exists()
    monkeypatch.setattr(config, "_replace", real_replace)
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 0, err
    assert (root / "VERSION").read_text(encoding="utf-8") == "99.0.0\n" and runs.kinds() == ["uv", "doktor"]


def test_aktualizuj_refuses_a_zip_outside_github_without_downloading(run, net, runs):
    install_old()
    net.routes[api_url()] = release_json(assets=[{"name": "trial-reels.zip",
                                                  "browser_download_url": "https://example.net/trial-reels.zip"}])
    before = tree(config.ROOT)
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 1 and "GitHub" in err and "example.net" in err
    assert net.calls == [api_url()] and tree(config.ROOT) == before and runs.calls == []


def test_aktualizuj_refuses_a_release_address_outside_github(run, net, monkeypatch):
    monkeypatch.setattr(update, "default_base", lambda: "https://example.net/repos/x")
    rc, out, err = run("aktualizuj")
    assert rc == 1 and "GitHub" in err and net.calls == []


def test_aktualizuj_accepts_a_local_test_server_from_the_environment(run, net, runs, monkeypatch):
    install_old()
    monkeypatch.setenv("TRIAL_REELS_RELEASES_URL", LOCAL)
    zip_local = "http://127.0.0.1:8123/trial-reels.zip"
    net.routes[LOCAL + "/releases/latest"] = json.dumps({"tag_name": NEW, "body": NOTES, "assets": [
        {"name": "trial-reels.zip", "browser_download_url": zip_local}]}).encode("utf-8")
    net.routes[zip_local] = release_zip_bytes()
    rc, out, err = run("aktualizuj", "--tak")
    assert rc == 0, err
    assert net.calls == [LOCAL + "/releases/latest", zip_local]
    assert (config.ROOT / "VERSION").read_text(encoding="utf-8") == "99.0.0\n"


@pytest.mark.parametrize("error, fragment", [
    (urllib.error.URLError("brak sieci"), "połączyć się z GitHubem"),
    (http_error(404), "Nie znalazłem"),
])
def test_aktualizuj_network_problems_are_one_plain_line(run, net, error, fragment):
    net.routes[api_url()] = error
    rc, out, err = run("aktualizuj")
    assert rc == 1 and fragment in err and "Traceback" not in err
    assert len([line for line in err.splitlines() if line.strip()]) == 1


def test_aktualizuj_is_listed_in_the_help(capsys):
    cli.main([])
    assert "aktualizuj" in capsys.readouterr().out


# --- tylko biblioteka standardowa -----------------------------------------------

def imports_of(path: Path, top_level_only: bool = False) -> set:
    tree_ = ast.parse(path.read_text(encoding="utf-8"))
    nodes = tree_.body if top_level_only else ast.walk(tree_)
    found = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_the_update_path_sources_import_only_the_standard_library():
    pkg = REPO / "trial_reels"
    for name in ("update.py", "wizard.py"):
        assert imports_of(pkg / name) <= set(sys.stdlib_module_names), name
    assert imports_of(pkg / "state.py", top_level_only=True) <= set(sys.stdlib_module_names)  # filelock dopiero w locked()


DRIVER = r'''
import json, os, subprocess, sys
repo, zip_path, flag = sys.argv[1:4]
sys.path.insert(0, repo)
before = set(sys.modules)
from trial_reels import __main__ as cli, config, update
config.REPO_SLUG = "przyklad-org/trial-reels"       # program z wydania ma prawdziwy adres repozytorium

class Resp:
    def __init__(self, body):
        self.body = body
        self.headers = {"Content-Length": str(len(body))}
    def read(self, n=-1):
        data, self.body = (self.body, b"") if n < 0 else (self.body[:n], self.body[n:])
        return data
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False

api = "https://api.github.com/repos/%s/releases/latest" % config.REPO_SLUG
zip_url = "https://github.com/%s/releases/download/v99.0.0/trial-reels.zip" % config.REPO_SLUG
routes = {
    api: json.dumps({"tag_name": "v99.0.0", "body": "- zmiana", "assets": [
        {"name": "trial-reels.zip", "browser_download_url": zip_url}]}).encode("utf-8"),
    zip_url: open(zip_path, "rb").read(),
}
update._urlopen = lambda req: Resp(routes[req.full_url])
update.subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", "")
config.uv_exe = lambda: "uv"
rc = cli.main(["aktualizuj", flag])
loaded = {name.split(".")[0] for name in set(sys.modules) - before}
third = sorted(loaded - set(sys.stdlib_module_names) - {"trial_reels"})
print("WYNIK " + json.dumps({"rc": rc, "obce": third}))
'''


@pytest.mark.parametrize("flag", ["--sprawdz", "--tak"])
def test_the_update_path_loads_no_packages_outside_the_standard_library(tmp_path, flag):
    """Na Windowsie uv nie podmieni bibliotek, które proces ma załadowane, więc aktualizacja nie może żadnej wczytać."""
    root = tmp_path / "klient"
    install_old(root, requirements="pakiet==0\n")
    driver = tmp_path / "sterownik.py"
    driver.write_text(DRIVER, encoding="utf-8")
    new = make_zip(tmp_path / "wydanie.zip", release_files(NEW))
    env = {**os.environ, "TRIAL_REELS_ROOT": str(root), "PYTHONUTF8": "1"}
    done = subprocess.run([sys.executable, "-I", str(driver), str(REPO), str(new), flag], env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout.split("WYNIK ", 1)[1])
    assert result["rc"] == 0
    foreign = {name for name in result["obce"] if not name.startswith("_sysconfigdata")}   # to moduł samego Pythona
    assert foreign <= {"tzdata"}, foreign                            # tzdata to same dane stref; zoneinfo ładuje go na Windowsie
    assert ((root / "VERSION").read_text(encoding="utf-8") == "99.0.0\n") is (flag == "--tak")
