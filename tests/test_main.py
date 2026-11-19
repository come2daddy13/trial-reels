"""Testy wejścia do komend: `python -m trial_reels` i skryptów startowych."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfoNotFoundError

import pytest

import trial_reels
from trial_reels import __main__ as cli
from trial_reels import config, doctor, planner

CODE = Path(__file__).resolve().parents[1]

# Komunikat skryptów startowych, gdy folder nie ma jeszcze środowiska Pythona (świeża instalacja przed krokiem 1).
NO_VENV_MESSAGE = "Brak środowiska Pythona (.venv). Najpierw krok 1: .claude/skills/trial-reels/kroki/01-programy.md"
# W `trial.cmd` bez polskich znaków (strona kodowa cmd.exe zepsułaby je w konsoli).
NO_VENV_MESSAGE_ASCII = "Brak srodowiska Pythona (.venv). Najpierw krok 1: .claude/skills/trial-reels/kroki/01-programy.md"
NO_VENV_CODE = 3


def _find_bash():
    """Bash do testów skryptu `trial.sh`. Na Windowsie to Git Bash, bo `bash.exe` z System32 jest launcherem WSL."""
    found = shutil.which("bash")
    if found and sys.platform == "win32" and "system32" in found.lower():
        git = shutil.which("git")
        candidate = Path(git).resolve().parents[1] / "bin" / "bash.exe" if git else None
        found = str(candidate) if candidate is not None and candidate.is_file() else None
    return found


def _run_launcher(command, cwd):
    return subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def test_version_comes_from_version_file():
    text = (CODE / "VERSION").read_text(encoding="utf-8").strip()
    assert trial_reels.VERSION == text
    assert re.fullmatch(r"\d+\.\d+\.\d+", text)


def test_version_falls_back_when_file_is_missing_or_empty(tmp_path):
    assert trial_reels._read_version(tmp_path / "nie-ma") == "0.0.0"
    assert trial_reels._read_version(tmp_path) == "0.0.0"  # katalog zamiast pliku
    empty = tmp_path / "VERSION"
    empty.write_text("\n", encoding="utf-8")
    assert trial_reels._read_version(empty) == "0.0.0"


def test_version_ignores_bom_and_line_ending(tmp_path):
    path = tmp_path / "VERSION"
    path.write_bytes(b"\xef\xbb\xbf1.2.3\r\n")
    assert trial_reels._read_version(path) == "1.2.3"


def test_wersja_prints_only_the_version(capsys):
    assert cli.main(["wersja"]) == 0
    assert capsys.readouterr().out == trial_reels.VERSION + "\n"


def test_no_command_prints_help_with_command_list(capsys):
    assert cli.main([]) == 0
    assert "wersja" in capsys.readouterr().out


def test_unknown_command_is_an_error():
    with pytest.raises(SystemExit) as caught:
        cli.main(["nie-ma-takiej-komendy"])
    assert caught.value.code == 2


def test_launcher_line_endings():
    assert b"\r" not in (CODE / "trial.sh").read_bytes()  # bash nie zniesie CRLF
    cmd = (CODE / "trial.cmd").read_bytes()
    assert cmd.count(b"\n") > 0 and cmd.count(b"\n") == cmd.count(b"\r\n")  # cmd.exe lubi tylko CRLF


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                    reason="trial.sh jest dla Maca i Git Bash; test używa dowiązania do venv")
def test_trial_sh_runs_from_path_with_spaces_and_polish_letters(tmp_path):
    dest = tmp_path / "Łukasz Ząb" / "Łódź ąę" / "trial-reels"
    dest.mkdir(parents=True)
    for name in ("trial.sh", "VERSION"):
        shutil.copy(CODE / name, dest / name)
    shutil.copytree(CODE / "trial_reels", dest / "trial_reels", ignore=shutil.ignore_patterns("__pycache__"))
    (dest / ".venv").symlink_to(Path(sys.prefix), target_is_directory=True)
    out = subprocess.run(
        ["bash", str(dest / "trial.sh"), "wersja"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == trial_reels.VERSION


# --- brak środowiska Pythona (.venv): przyjazny komunikat i kod 3 --------------------

def test_the_message_points_at_an_existing_step_file():
    assert (CODE / ".claude" / "skills" / "trial-reels" / "kroki" / "01-programy.md").is_file()


@pytest.mark.skipif(_find_bash() is None, reason="brak bash")
@pytest.mark.parametrize("layout", ["brak-folderu", "pusty-folder", "bin-bez-pythona", "scripts-bez-pythona"])
def test_trial_sh_without_python_in_venv_prints_the_message_and_exits_3(tmp_path, layout):
    dest = tmp_path / "Łukasz Ząb" / "trial-reels"
    dest.mkdir(parents=True)
    shutil.copy(CODE / "trial.sh", dest / "trial.sh")
    if layout != "brak-folderu":
        (dest / ".venv").mkdir()
    if layout == "bin-bez-pythona":
        (dest / ".venv" / "bin").mkdir()
    if layout == "scripts-bez-pythona":
        (dest / ".venv" / "Scripts").mkdir()
    out = _run_launcher([_find_bash(), (dest / "trial.sh").as_posix(), "wersja"], cwd=tmp_path)
    assert out.returncode == NO_VENV_CODE, out.stdout + out.stderr
    assert out.stderr.strip() == NO_VENV_MESSAGE
    assert out.stdout == ""


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                    reason="atrapa pythona jest skryptem bash, a Windows nie uruchomi takiego .exe")
def test_trial_sh_uses_the_windows_layout_when_only_scripts_python_exists(tmp_path):
    dest = tmp_path / "trial-reels"
    (dest / ".venv" / "Scripts").mkdir(parents=True)
    shutil.copy(CODE / "trial.sh", dest / "trial.sh")
    fake = dest / ".venv" / "Scripts" / "python.exe"
    fake.write_text('#!/bin/sh\necho "uruchomiono: $*"\nexit 7\n', encoding="utf-8")
    fake.chmod(0o755)
    out = _run_launcher(["bash", str(dest / "trial.sh"), "wersja", "--x"], cwd=tmp_path)
    assert out.returncode == 7, out.stderr                       # kod wyjścia programu przechodzi bez zmian
    assert out.stdout.strip() == "uruchomiono: -m trial_reels wersja --x"
    assert out.stderr == ""


def test_trial_cmd_is_plain_ascii_and_checks_the_venv_python():
    text = (CODE / "trial.cmd").read_bytes().decode("ascii")      # bez polskich znaków: wynik w konsoli cmd
    assert NO_VENV_MESSAGE_ASCII in text
    assert "exit /b %d" % NO_VENV_CODE in text
    assert r'if not exist ".venv\Scripts\python.exe"' in text
    assert "%~dp0" in text and "%*" in text


@pytest.mark.skipif(sys.platform != "win32", reason="trial.cmd jest tylko dla Windowsa")
def test_trial_cmd_without_python_in_venv_prints_the_message_and_exits_3(tmp_path):
    dest = tmp_path / "Łukasz Ząb" / "Łódź ąę" / "trial-reels"
    dest.mkdir(parents=True)
    shutil.copy(CODE / "trial.cmd", dest / "trial.cmd")
    (dest / ".venv").mkdir()
    out = _run_launcher([str(dest / "trial.cmd"), "wersja"], cwd=tmp_path)
    assert out.returncode == NO_VENV_CODE, out.stdout + out.stderr
    assert out.stderr.strip() == NO_VENV_MESSAGE_ASCII
    assert out.stdout == ""


@pytest.mark.skipif(sys.platform != "win32" or not (CODE / ".venv" / "Scripts" / "python.exe").is_file(),
                    reason="trial.cmd jest tylko dla Windowsa i potrzebuje .venv w folderze repo")
def test_trial_cmd_passes_the_program_exit_code(tmp_path):
    ok = _run_launcher([str(CODE / "trial.cmd"), "wersja"], cwd=tmp_path)
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == trial_reels.VERSION
    bad = _run_launcher([str(CODE / "trial.cmd"), "nie-ma-takiej-komendy"], cwd=tmp_path)
    assert bad.returncode == 2                                   # argparse: nieznana komenda


# --- strefa czasowa z ustawień --------------------------------------------------

def test_command_sets_the_planner_time_zone_from_the_settings(capsys):
    config.save_settings({"timezone": "Asia/Tokyo"})
    assert cli.main(["wersja"]) == 0
    assert planner.TZ.key == "Asia/Tokyo"


def test_time_zone_goes_back_after_each_test():
    """Poprzedni test ustawił Tokio. Fixture z conftest przywraca strefę, więc ten test startuje z domyślną."""
    assert planner.TZ.key == config.DEFAULTS["timezone"]


def test_unknown_time_zone_is_a_plain_polish_message_with_code_2(capsys):
    config.save_settings({"timezone": "Marsjańska/Olympus"})
    assert cli.main(["status"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Marsjańska/Olympus" in captured.err and "dane/config.json" in captured.err
    assert "Europe/Warsaw" in captured.err and "Traceback" not in captured.err
    assert len([line for line in captured.err.splitlines() if line.strip()]) == 1
    assert planner.TZ.key == config.DEFAULTS["timezone"]            # zła nazwa niczego nie zmienia


@pytest.mark.parametrize("bad", ["", "../etc/passwd", 7, None])
def test_malformed_time_zone_values_get_the_same_message(capsys, bad):
    config.save_settings({"timezone": bad})
    assert cli.main(["status"]) == 2
    assert "dane/config.json" in capsys.readouterr().err


OTHER_COMMANDS = ["status", "pula", "podglad", "raport", "hamulec", "sprawdz-pule", "pobierz", "transkrybuj", "paczka",
                  "konto"]                                   # wszystkie poza wersja, doktor, krok i aktualizuj


@pytest.mark.parametrize("command", OTHER_COMMANDS)
def test_every_other_command_still_stops_on_a_bad_time_zone(capsys, command):
    config.save_settings({"timezone": "Marsjańska/Olympus"})
    assert cli.main([command]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Marsjańska/Olympus" in captured.err and "Traceback" not in captured.err


# --- komputer bez bazy stref czasowych (Windows po nieudanej instalacji pakietu tzdata) ------------

def test_importing_the_program_survives_a_computer_without_a_time_zone_database(tmp_path):
    """Windows nie ma własnej bazy stref, więc bez pakietu tzdata import się wywracał, a `doktor` nie miał jak powiedzieć,
    co jest zepsute. Teraz strefą jest UTC do czasu, aż komenda ustawi właściwą."""
    code = ("import sys, zoneinfo\n"
            "zoneinfo.reset_tzpath(to=[])\n"
            "sys.modules['tzdata'] = None\n"                       # tak wygląda środowisko bez pakietu tzdata
            "import trial_reels.__main__ as m\n"
            "print(m.planner.TZ)")
    done = subprocess.run([sys.executable, "-c", code], cwd=CODE, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120,
                          env={**os.environ, "TRIAL_REELS_ROOT": str(tmp_path / "klient"), "PYTHONUTF8": "1"})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "UTC"


@pytest.fixture
def no_time_zone_database(monkeypatch):
    def missing(key):
        raise ZoneInfoNotFoundError("No time zone found with key %s" % key)

    for module in (planner, config, doctor):
        monkeypatch.setattr(module, "ZoneInfo", missing)


def test_a_missing_time_zone_database_is_reported_as_a_broken_install_not_as_a_bad_setting(capsys, no_time_zone_database):
    assert cli.main(["status"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Traceback" not in captured.err
    assert "tzdata" in captured.err and "doktor" in captured.err and "pakiety" in captured.err
    assert "Nieznana strefa" not in captured.err and "dane/config.json" not in captured.err
    assert len([line for line in captured.err.splitlines() if line.strip()]) == 1


def test_doktor_blames_the_install_when_there_is_no_time_zone_database(capsys, plenty_of_space, no_time_zone_database):
    assert cli.main(["doktor"]) == 1
    captured = capsys.readouterr()
    row = next(line for line in captured.out.splitlines() if "Strefa czasowa" in line)
    assert row.startswith("✗ Strefa czasowa: ") and "tzdata" in row and "Programy" in row
    assert "dane/config.json" not in row and "Traceback" not in captured.err


@pytest.mark.parametrize("command", ["wersja", "krok", "aktualizuj"])
def test_the_commands_that_work_with_damaged_settings_also_work_without_a_time_zone_database(
        capsys, monkeypatch, plenty_of_space, no_time_zone_database, command):
    monkeypatch.setattr(cli.update, "latest", lambda base=None: {"tag": "v0.0.1", "notes": "", "zip_url": ""})   # bez sieci
    assert cli.main([command]) == 0
    assert "Traceback" not in capsys.readouterr().err


@pytest.fixture
def plenty_of_space(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "disk_usage",
                        lambda path: SimpleNamespace(total=10**12, used=0, free=10**12))


def test_wersja_works_with_a_bad_time_zone(capsys):
    config.save_settings({"timezone": "Marsjańska/Olympus"})
    assert cli.main(["wersja"]) == 0
    captured = capsys.readouterr()
    assert captured.out == trial_reels.VERSION + "\n" and captured.err == ""
    assert planner.TZ.key == config.DEFAULTS["timezone"]            # zła nazwa niczego nie zmienia


def test_doktor_shows_a_bad_time_zone_as_a_failed_row_with_the_way_to_fix_it(capsys, plenty_of_space):
    config.save_settings({"timezone": "Marsjańska/Olympus"})
    assert cli.main(["doktor"]) == 1
    captured = capsys.readouterr()
    row = next(line for line in captured.out.splitlines() if "Strefa czasowa" in line)
    assert row.startswith("✗ Strefa czasowa: ")
    for part in ("Marsjańska/Olympus", "dane/config.json", "timezone", "Europe/Warsaw"):
        assert part in row, part
    assert "Do poprawienia: 1." in captured.out and "Traceback" not in captured.err
    others = [line for line in captured.out.splitlines() if line and line[0] in "✓✗" and "Strefa" not in line]
    assert len(others) == 9 and all(line.startswith("✓") for line in others)      # reszta kontroli przechodzi
    assert planner.TZ.key == config.DEFAULTS["timezone"]


@pytest.mark.parametrize("bad", ["", "../etc/passwd", 7, None])
def test_doktor_copes_with_malformed_time_zone_values(capsys, plenty_of_space, bad):
    config.save_settings({"timezone": bad})
    assert cli.main(["doktor"]) == 1
    captured = capsys.readouterr()
    assert "✗ Strefa czasowa" in captured.out and "dane/config.json" in captured.out and "Traceback" not in captured.err


def test_doktor_is_happy_with_a_good_time_zone(capsys, plenty_of_space):
    config.save_settings({"timezone": "Asia/Tokyo"})
    assert cli.main(["doktor"]) == 0
    out = capsys.readouterr().out
    assert "✓ Strefa czasowa: Asia/Tokyo" in out and "✗" not in out and planner.TZ.key == "Asia/Tokyo"


def test_krok_works_with_a_bad_time_zone_and_points_at_the_doctor(capsys, plenty_of_space):
    config.save_settings({"timezone": "Marsjańska/Olympus"})
    assert cli.main(["krok"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert captured.err == "" and len(data["kroki"]) == 12
    programs = next(k for k in data["kroki"] if k["id"] == "programy")
    assert programs["gotowy"] is False and "Strefa czasowa" in programs["szczegoly"] and "doktor" in programs["szczegoly"]
    assert cli.main(["krok", "--gotowe", "powitanie"]) == 0                  # zapis kroku też działa
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}


def test_krok_with_a_good_time_zone_does_not_complain_about_it(capsys, plenty_of_space):
    assert cli.main(["krok"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "Strefa czasowa" not in next(k for k in data["kroki"] if k["id"] == "programy")["szczegoly"]


# --- uszkodzony plik ustawień (dane/config.json) ---------------------------------

DAMAGED_SETTINGS = ["{nie json", "[]", "null", '"tekst"']


def damage_settings(text="{nie json"):
    config.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("command", OTHER_COMMANDS)
def test_every_other_command_stops_on_a_damaged_settings_file_with_one_plain_line(capsys, command):
    damage_settings()
    assert cli.main([command]) == 1
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert captured.out == "" and len(lines) == 1 and "dane/config.json" in lines[0] and "uszkodzony" in lines[0]
    assert "Traceback" not in captured.err and config.SETTINGS.read_text(encoding="utf-8") == "{nie json"


@pytest.mark.parametrize("text", DAMAGED_SETTINGS)
def test_wersja_works_with_a_damaged_settings_file(capsys, text):
    damage_settings(text)
    assert cli.main(["wersja"]) == 0
    captured = capsys.readouterr()
    assert captured.out == trial_reels.VERSION + "\n" and captured.err == ""
    assert planner.TZ.key == config.DEFAULTS["timezone"]                    # strefa zostaje domyślna


@pytest.mark.parametrize("text", DAMAGED_SETTINGS)
def test_doktor_shows_a_damaged_settings_file_as_a_failed_row_with_the_way_to_fix_it(capsys, plenty_of_space, text):
    damage_settings(text)
    assert cli.main(["doktor"]) == 1
    captured = capsys.readouterr()
    row = next(line for line in captured.out.splitlines() if "Ustawienia (dane/config.json)" in line)
    assert row.startswith("✗ Ustawienia (dane/config.json): ")
    for part in ("dane/config.json", "popraw", "usuń", "komendą konto"):
        assert part in row, part
    assert "Do poprawienia: 1." in captured.out and "Traceback" not in captured.err
    others = [line for line in captured.out.splitlines() if line and line[0] in "✓✗" and "Ustawienia (dane" not in line]
    assert len(others) == 9 and all(line.startswith("✓") for line in others)      # strefa i reszta nie dokładają problemów
    assert planner.TZ.key == config.DEFAULTS["timezone"]


@pytest.mark.parametrize("text", DAMAGED_SETTINGS)
def test_krok_works_with_a_damaged_settings_file_and_points_at_the_doctor(capsys, plenty_of_space, text):
    damage_settings(text)
    assert cli.main(["krok"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert captured.err == "" and len(data["kroki"]) == 12
    programs = next(k for k in data["kroki"] if k["id"] == "programy")
    assert programs["gotowy"] is False and programs["szczegoly"].startswith("Do poprawienia: Ustawienia (dane/config.json)")
    assert "Strefa czasowa" not in programs["szczegoly"] and "doktor" in programs["szczegoly"]
    account = next(k for k in data["kroki"] if k["id"] == "konto")
    assert account["gotowy"] is False and "dane/config.json" in account["szczegoly"]
    assert "uszkodzony" in account["szczegoly"] or "zły układ" in account["szczegoly"]
    assert data["nastepny"] == "powitanie"
    assert cli.main(["krok", "--gotowe", "powitanie"]) == 0                  # zapis kroku też działa
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}
    assert config.SETTINGS.read_text(encoding="utf-8") == text               # uszkodzonego pliku nie ruszamy


def test_help_without_a_command_does_not_need_settings(capsys):
    damage_settings()
    assert cli.main([]) == 0 and "doktor" in capsys.readouterr().out


def test_every_setup_command_is_listed_in_the_help(capsys):
    cli.main([])
    out = capsys.readouterr().out
    for name in ("doktor", "konto", "kandydaci", "wynik-kandydata", "js-odczyt", "pula", "pobierz",
                 "transkrybuj", "sprawdz-pule", "kadr"):
        assert name in out, name


def test_options_cannot_be_abbreviated():
    from trial_reels.__main__ import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(["aktualizuj", "--ta"])
    assert build_parser().parse_args(["aktualizuj", "--tak"]).tak is True
