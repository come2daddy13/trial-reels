"""Testy doktora: kontrola komputera przed pierwszym użyciem i wykrywanie folderów synchronizowanych w chmurze."""
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest

from trial_reels import config, doctor, render

SETTINGS_ROW = "Ustawienia (dane/config.json)"
ROWS = ["Python 3.12 lub nowszy", "Pakiety Pythona", "ffmpeg z kodekiem H.264", "Font Poppins",
        "Emotki (co najmniej 25)", "Zapis w folderze dane", "Wolne miejsce (co najmniej 5 GB)",
        "Folder poza iCloud i OneDrive", SETTINGS_ROW, "Strefa czasowa"]


def by_name(rows):
    return {r["nazwa"]: r for r in rows}


@pytest.fixture
def plenty_of_space(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "disk_usage",
                        lambda path: SimpleNamespace(total=10**12, used=10**11, free=9 * 10**11))


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "dom"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


# --- foldery synchronizowane ----------------------------------------------------

def test_synced_folder(fake_home):
    icloud = PurePosixPath("/home/ala/Library/Mobile Documents/com~apple~CloudDocs/trial-reels")
    assert doctor.synced_folder(icloud) == "iCloud"
    assert doctor.synced_folder(PureWindowsPath(r"C:\Users\x\OneDrive\Dokumenty\a")) == "OneDrive"
    assert doctor.synced_folder(Path.home() / "trial-reels") is None


@pytest.mark.parametrize("path,expected", [
    (PureWindowsPath(r"C:\Users\x\iCloudDrive\trial-reels"), "iCloud"),
    (PurePosixPath("/home/ala/iCloud Drive (Archive)/trial-reels"), "iCloud"),
    (PurePosixPath("/home/ala/Library/Mobile Documents/com~apple~CloudDocs/Documents/a"), "iCloud"),
    (PureWindowsPath(r"C:\Users\x\OneDrive - Firma Przykład\Pulpit\trial-reels"), "OneDrive"),
    (PurePosixPath("/home/ala/Library/CloudStorage/OneDrive-Personal/trial-reels"), "OneDrive"),
    (PureWindowsPath(r"D:\onedrive\trial-reels"), "OneDrive"),
    (PureWindowsPath(r"C:\Users\Łukasz Ząb\trial-reels"), None),
    (PurePosixPath("/home/ala/Library/Application Support/trial-reels"), None),
    (PurePosixPath("/home/ala/Mobile Documents/trial-reels"), None),   # bez Library to zwykły folder
])
def test_synced_folder_recognizes_cloud_folders_by_their_names(path, expected, fake_home):
    assert doctor.synced_folder(path) == expected


def test_synced_folder_accepts_text_paths(fake_home):
    assert doctor.synced_folder("/home/ala/Library/Mobile Documents/com~apple~CloudDocs/a") == "iCloud"
    assert doctor.synced_folder(str(fake_home / "trial-reels")) is None


def test_synced_folder_sees_documents_and_desktop_synced_by_icloud(fake_home):
    """Synchronizacja Biurka i Dokumentów nie zmienia ścieżki, więc poznajemy ją po folderach iCloud w Bibliotece."""
    cloud = fake_home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    assert doctor.synced_folder(fake_home / "Documents" / "trial-reels") is None   # iCloud nie synchronizuje Dokumentów
    (cloud / "Documents").mkdir(parents=True)
    assert doctor.synced_folder(fake_home / "Documents" / "trial-reels") == "iCloud"
    assert doctor.synced_folder(fake_home / "Documents") == "iCloud"
    assert doctor.synced_folder(PurePath(fake_home / "Documents" / "a" / "b")) == "iCloud"  # sama ścieżka, bez dysku
    assert doctor.synced_folder(fake_home / "Desktop" / "trial-reels") is None     # Biurko nie jest w iCloud
    (cloud / "Desktop").mkdir()
    assert doctor.synced_folder(fake_home / "Desktop" / "trial-reels") == "iCloud"
    assert doctor.synced_folder(fake_home / "trial-reels") is None                 # folder obok to zwykły folder
    assert doctor.synced_folder(fake_home / "Downloads" / "trial-reels") is None


def test_synced_folder_ignores_letter_case_of_documents_folder(fake_home):
    (fake_home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Documents").mkdir(parents=True)
    assert doctor.synced_folder(PurePath(str(fake_home).lower()) / "documents" / "trial-reels") == "iCloud"


# --- tabela kontroli ------------------------------------------------------------

def test_checks_pass_on_a_healthy_install(plenty_of_space):
    rows = doctor.checks()
    assert [r["nazwa"] for r in rows] == ROWS
    assert all(set(r) == {"nazwa", "ok", "info"} for r in rows)
    assert all(isinstance(r["ok"], bool) and isinstance(r["info"], str) and r["info"] for r in rows)
    failing = [(r["nazwa"], r["info"]) for r in rows if not r["ok"]]
    assert failing == []


def test_checks_leave_no_trace_in_the_data_folder(plenty_of_space):
    doctor.checks()
    assert config.DATA.is_dir() and list(config.DATA.iterdir()) == []


def test_old_python_is_reported(monkeypatch, plenty_of_space):
    monkeypatch.setattr(doctor, "_python_version", lambda: (3, 11, 9))
    row = by_name(doctor.checks())["Python 3.12 lub nowszy"]
    assert row["ok"] is False and "3.11.9" in row["info"] and "3.12" in row["info"]
    monkeypatch.setattr(doctor, "_python_version", lambda: (3, 12, 0))
    assert by_name(doctor.checks())["Python 3.12 lub nowszy"]["ok"] is True


def test_a_package_that_does_not_import_is_named(monkeypatch, plenty_of_space):
    real = doctor.importlib.import_module

    def broken(name, *args, **kwargs):
        if name == "av":
            raise ImportError("DLL load failed while importing av")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(doctor.importlib, "import_module", broken)
    row = by_name(doctor.checks())["Pakiety Pythona"]
    assert row["ok"] is False and "av" in row["info"] and "DLL load failed" in row["info"]


def test_ffmpeg_without_libx264_is_reported(monkeypatch, plenty_of_space):
    def only_x265(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=" V..... libx265  libx265 H.265 / HEVC\n", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", only_x265)
    row = by_name(doctor.checks())["ffmpeg z kodekiem H.264"]
    assert row["ok"] is False and "libx264" in row["info"]


def test_ffmpeg_that_will_not_start_is_reported(monkeypatch, plenty_of_space):
    def missing(*args, **kwargs):
        raise FileNotFoundError("nie ma pliku ffmpeg")

    monkeypatch.setattr(doctor.subprocess, "run", missing)
    row = by_name(doctor.checks())["ffmpeg z kodekiem H.264"]
    assert row["ok"] is False and "ffmpeg" in row["info"]


def test_missing_font_is_reported_in_polish(monkeypatch, tmp_path, plenty_of_space):
    monkeypatch.setattr(config, "ASSETS", tmp_path / "pusto")
    rows = by_name(doctor.checks())
    assert rows["Font Poppins"]["ok"] is False and "Brak fontu" in rows["Font Poppins"]["info"]
    assert rows["Emotki (co najmniej 25)"]["ok"] is False


def test_emoji_need_at_least_25_files(monkeypatch, tmp_path, plenty_of_space):
    assets = tmp_path / "paczka"
    (assets / "emoji").mkdir(parents=True)
    names = ["%x" % (0x1F600 + i) for i in range(25)]
    for name in names[:24]:
        (assets / "emoji" / ("%s.png" % name)).write_bytes(b"png")
    monkeypatch.setattr(config, "ASSETS", assets)
    row = by_name(doctor.checks())["Emotki (co najmniej 25)"]
    assert row["ok"] is False and "24" in row["info"]
    (assets / "emoji" / ("%s.png" % names[24])).write_bytes(b"png")
    assert by_name(doctor.checks())["Emotki (co najmniej 25)"]["ok"] is True


def test_unwritable_data_folder_is_reported(monkeypatch, tmp_path, plenty_of_space):
    blocker = tmp_path / "plik"
    blocker.write_text("to jest plik, a nie folder", encoding="utf-8")
    monkeypatch.setattr(config, "DATA", blocker / "dane")
    row = by_name(doctor.checks())["Zapis w folderze dane"]
    assert row["ok"] is False and "dane" in row["info"]


def test_free_space_limit_is_5_gb(monkeypatch):
    """Model (1,6 GB), filmy źródłowe i tygodniowa paczka wersji (ok. 1,3 GB) razem nie mieszczą się w 3 GB."""
    def free(n):
        return lambda path: SimpleNamespace(total=10**12, used=0, free=n)

    assert doctor.MIN_FREE_BYTES == 5 * 10**9
    monkeypatch.setattr(doctor.shutil, "disk_usage", free(4_900_000_000))
    row = by_name(doctor.checks())["Wolne miejsce (co najmniej 5 GB)"]
    assert row["ok"] is False and "4,9 GB" in row["info"] and "co najmniej 5 GB" in row["info"] and "co najmniej 3 GB" not in row["info"]
    monkeypatch.setattr(doctor.shutil, "disk_usage", free(3_000_000_000))                 # to dawny próg: już za mało
    assert by_name(doctor.checks())["Wolne miejsce (co najmniej 5 GB)"]["ok"] is False
    monkeypatch.setattr(doctor.shutil, "disk_usage", free(5_000_000_000))
    row = by_name(doctor.checks())["Wolne miejsce (co najmniej 5 GB)"]
    assert row["ok"] is True and "5,0 GB" in row["info"]


def test_free_space_is_measured_on_an_existing_folder(monkeypatch):
    seen = []

    def spy(path):
        seen.append(Path(path))
        return SimpleNamespace(total=10**12, used=0, free=10**12)

    monkeypatch.setattr(doctor.shutil, "disk_usage", spy)
    assert not config.DATA.exists()
    ok, _ = doctor.check_space()
    assert ok is True and seen and seen[0].is_dir()


def test_folder_inside_onedrive_or_icloud_is_reported(tmp_path, plenty_of_space):
    config.use_root(tmp_path / "OneDrive - Firma" / "trial-reels")
    row = by_name(doctor.checks())["Folder poza iCloud i OneDrive"]
    assert row["ok"] is False and "OneDrive" in row["info"]
    config.use_root(tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "trial-reels")
    row = by_name(doctor.checks())["Folder poza iCloud i OneDrive"]
    assert row["ok"] is False and "iCloud" in row["info"]


def test_folder_with_polish_letters_and_spaces_is_fine(tmp_path, plenty_of_space):
    config.use_root(tmp_path / "Łukasz Ząb" / "Łódź ąę" / "trial-reels")
    rows = doctor.checks()
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]


def test_time_zone_check_accepts_a_known_zone_and_says_which(plenty_of_space):
    assert doctor.check_timezone() == (True, "Europe/Warsaw")                       # domyślna z ustawień
    config.save_settings({"timezone": "America/New_York"})
    assert by_name(doctor.checks())["Strefa czasowa"] == {"nazwa": "Strefa czasowa", "ok": True,
                                                         "info": "America/New_York"}


@pytest.mark.parametrize("bad", ["Marsjańska/Olympus", "", "../etc/passwd", 7, None, ["Europe/Warsaw"]])
def test_time_zone_check_reports_a_bad_zone_with_the_place_to_fix_it(plenty_of_space, bad):
    config.save_settings({"timezone": bad})
    row = by_name(doctor.checks())["Strefa czasowa"]
    assert row["ok"] is False
    for part in ("dane/config.json", "timezone", "Europe/Warsaw"):
        assert part in row["info"], part
    assert "\n" not in row["info"]


def test_settings_check_is_happy_with_a_missing_or_a_good_file(plenty_of_space):
    ok, info = doctor.check_settings()
    assert ok is True and "domyślne" in info                                   # nie ma pliku: działają ustawienia domyślne
    config.save_settings({"daily_max": 4})
    ok, info = doctor.check_settings()
    assert ok is True and info and "\n" not in info
    assert by_name(doctor.checks())[SETTINGS_ROW]["ok"] is True


@pytest.mark.parametrize("text", ["{nie json", "[]", '"tekst"', "null"])
def test_a_damaged_settings_file_is_a_failed_row_with_a_polish_hint(plenty_of_space, text):
    config.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS.write_text(text, encoding="utf-8")
    rows = doctor.checks()
    assert [r["nazwa"] for r in rows] == ROWS
    bad = by_name(rows)[SETTINGS_ROW]
    assert bad["ok"] is False and "\n" not in bad["info"]
    for part in ("dane/config.json", "popraw", "usuń", "komendą konto"):
        assert part in bad["info"], part
    assert "Traceback" not in bad["info"] and "JSONDecodeError" not in bad["info"]


def test_a_damaged_settings_file_is_the_only_problem_the_doctor_reports(plenty_of_space):
    """Strefy nie da się wtedy sprawdzić, ale to ten sam jeden problem: nie liczymy go dwa razy."""
    config.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS.write_text("{nie json", encoding="utf-8")
    rows = by_name(doctor.checks())
    assert [name for name, row in rows.items() if not row["ok"]] == [SETTINGS_ROW]
    zone = rows["Strefa czasowa"]
    assert zone["ok"] is True and config.DEFAULTS["timezone"] in zone["info"] and "uszkodzony" in zone["info"]


def test_the_settings_row_comes_right_before_the_time_zone_row(plenty_of_space):
    names = [r["nazwa"] for r in doctor.checks()]
    assert names[-2:] == [SETTINGS_ROW, "Strefa czasowa"]


def test_one_broken_check_does_not_hide_the_others(monkeypatch, plenty_of_space):
    def boom():
        raise RuntimeError("coś dziwnego")

    monkeypatch.setattr(doctor, "check_font", boom)
    rows = doctor.checks()
    assert [r["nazwa"] for r in rows] == ROWS
    bad = by_name(rows)["Font Poppins"]
    assert bad["ok"] is False and "coś dziwnego" in bad["info"]
    assert all(r["ok"] for r in rows if r["nazwa"] != "Font Poppins")


def test_bundled_assets_pass_the_doctor_checks():
    """Font i emotki w paczce wystarczą doktorowi (to samo, co zobaczy klient po pobraniu wydania)."""
    assert doctor.check_font()[0] is True
    assert doctor.check_emoji()[0] is True and len(render.emoji_set()) >= 25
