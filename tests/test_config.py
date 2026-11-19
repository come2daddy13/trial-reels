"""Testy ustawień, ścieżek danych oraz odczytu i zapisu plików klienta."""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trial_reels import config

CODE = Path(__file__).resolve().parents[1]

# Nazwa stałej w config -> nazwa pliku albo folderu w dane/.
DATA_NAMES = {
    "SRC": "src",
    "OUT": "wersje",
    "TRANSCRIPTS": "transkrypcje",
    "REPORTS": "raporty",
    "STATE": "stan.json",
    "POOL": "pula.json",
    "HOOKS": "hooki.json",
    "CANDIDATES": "kandydaci.json",
    "WIZARD": "kreator.json",
    "SETTINGS": "config.json",
    "ENV": ".env",
}


def write_env(text: str) -> None:
    config.ENV.parent.mkdir(parents=True, exist_ok=True)
    config.ENV.write_text(text, encoding="utf-8")


def root_in_fresh_process(extra_env: dict) -> str:
    """Wartość config.ROOT w nowym procesie, czyli tuż po imporcie modułu."""
    env = {**os.environ, "PYTHONUTF8": "1", **extra_env}
    out = subprocess.run(
        [sys.executable, "-c", "from trial_reels import config; print(config.ROOT)"],
        cwd=CODE, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


# --- ścieżki ---------------------------------------------------------------

def test_use_root_moves_all_data_paths(tmp_path):
    config.use_root(tmp_path)
    assert config.DATA == tmp_path / "dane" and config.STATE == tmp_path / "dane" / "stan.json"
    assert config.OUT == tmp_path / "dane" / "wersje"


def test_every_data_path_lives_in_dane(tmp_path):
    config.use_root(tmp_path)
    assert config.ROOT == tmp_path
    for attr, name in DATA_NAMES.items():
        assert getattr(config, attr) == tmp_path / "dane" / name, attr


def test_use_root_leaves_code_paths_alone(tmp_path):
    config.use_root(tmp_path)
    assert config.CODE == Path(config.__file__).resolve().parents[1]
    assert config.PKG == config.CODE / "trial_reels" and config.PKG.is_dir()
    assert config.ASSETS == config.CODE / "assets"


def test_use_root_makes_relative_root_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config.use_root("wzgledny")
    assert config.ROOT == tmp_path / "wzgledny"
    assert config.DATA.is_absolute()


def test_root_defaults_to_code_folder_and_follows_env_variable(tmp_path):
    assert root_in_fresh_process({}) == str(CODE)
    wanted = tmp_path / "Mój folder"
    assert root_in_fresh_process({"TRIAL_REELS_ROOT": str(wanted)}) == str(wanted)


def test_paths_with_polish_letters(tmp_path):
    config.use_root(tmp_path / "Łukasz Ząb" / "trial-reels")
    config.write_json(config.POOL, [{"name": "Zażółć gęślą jaźń 🔥"}])
    assert config.read_json(config.POOL, [])[0]["name"] == "Zażółć gęślą jaźń 🔥"


# --- stałe i ustawienia ----------------------------------------------------

def test_constants_hold_documented_values():
    assert config.LEVELS == ("subtelna", "srednia", "mocna")
    assert config.LEVEL_MIX == {"subtelna": 0.5, "srednia": 0.3, "mocna": 0.2}
    assert sum(config.LEVEL_MIX.values()) == pytest.approx(1.0)
    assert config.LEVEL_LABEL == {"subtelna": "Subtelna", "srednia": "Średnia", "mocna": "Mocna"}
    assert config.STATUS_LABEL == {
        "do_akceptacji": "Do akceptacji",
        "zaakceptowana": "Zaakceptowana",
        "odrzucona": "Odrzucona",
        "zaplanowana": "Zaplanowana",
        "opublikowana": "Opublikowana",
        "blad": "Błąd",
    }
    assert (config.MIN_LEAD_MIN, config.STATS_MIN_AGE_DAYS, config.BRAKE_DROP) == (20, 3, 0.30)
    assert config.ZERNIO_BASE == "https://zernio.com/api/v1"
    # Adres zastępczy: podkreśleń nie ma w nazwach kont na GitHubie, więc nigdy nie wskaże cudzego repozytorium.
    # Przed pierwszym wydaniem podmienia się go w config.py, README.md i tutaj (wydanie z nim się nie zbuduje).
    assert config.REPO_SLUG == "come2daddy13/trial-reels"


@pytest.mark.parametrize("slug", ["przyklad-org/trial-reels", "Org1/trial-reels", "a/trial-reels",
                                  "a" * 39 + "/trial-reels", "org/trial.reels_2"])
def test_repo_problem_accepts_names_that_github_allows(slug):
    assert config.repo_problem(slug) is None


@pytest.mark.parametrize("slug", ["__PRZYKLAD__/trial-reels", "-org/trial-reels", "org-/trial-reels",
                                  "or--g/trial-reels", "a" * 40 + "/trial-reels", "org", "org/", "/trial-reels",
                                  "org/trial reels", "org/..", "org/a/b", "", 123])
def test_repo_problem_rejects_names_that_cannot_be_a_github_repository(slug):
    problem = config.repo_problem(slug)
    assert problem and "\n" not in problem and "opiekun" in problem


def test_repo_problem_checks_the_programs_own_address_by_default(monkeypatch):
    monkeypatch.setattr(config, "REPO_SLUG", "__PRZYKLAD__/trial-reels")
    assert config.repo_problem() is not None
    monkeypatch.setattr(config, "REPO_SLUG", "przyklad-org/trial-reels")
    assert config.repo_problem() is None


def test_defaults_hold_documented_values():
    expected = {
        "timezone": "Europe/Warsaw",
        "day_window": ["07:15", "22:00"],
        "hours": ["09:00", "21:00"],
        "daily_max": 10,
        "brake_slot": "13:00",
    }
    for key, value in expected.items():
        assert config.DEFAULTS[key] == value, key
    assert "ig_account_id" in config.DEFAULTS and config.DEFAULTS["ig_account_id"] is None
    assert "ig_handle" in config.DEFAULTS and config.DEFAULTS["ig_handle"] is None


def test_settings_defaults_and_save_roundtrip():
    s = config.settings()
    assert s["timezone"] == "Europe/Warsaw" and s["daily_max"] == 10 and s["day_window"] == ["07:15", "22:00"]
    config.save_settings({"ig_handle": "żółć.test"})
    assert config.settings()["ig_handle"] == "żółć.test"


def test_settings_returns_independent_copy():
    s = config.settings()
    s["day_window"].append("23:00")
    assert config.settings()["day_window"] == ["07:15", "22:00"]
    assert config.DEFAULTS["day_window"] == ["07:15", "22:00"]


def test_settings_file_overrides_defaults_and_keeps_unknown_keys():
    config.write_json(config.SETTINGS, {"daily_max": 4, "inna_opcja": True})
    s = config.settings()
    assert s["daily_max"] == 4 and s["inna_opcja"] is True and s["brake_slot"] == "13:00"


def test_save_settings_stores_only_changes_and_returns_merged():
    out = config.save_settings({"daily_max": 3})
    assert out["daily_max"] == 3 and out["timezone"] == "Europe/Warsaw"
    assert config.read_json(config.SETTINGS, None) == {"daily_max": 3}
    config.save_settings({"ig_handle": "@przyklad.konto"})
    assert config.read_json(config.SETTINGS, None) == {"daily_max": 3, "ig_handle": "@przyklad.konto"}


def write_settings_text(text: str, encoding: str = "utf-8") -> None:
    config.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS.write_bytes(text.encode(encoding) if isinstance(text, str) else text)


def test_a_damaged_settings_file_is_one_plain_polish_error_with_the_place_and_the_fix():
    write_settings_text('{\n "daily_max": 4\n "hours": []\n}')              # brakuje przecinka w linii 2
    with pytest.raises(config.UserError) as caught:
        config.settings()
    message = str(caught.value)
    assert "dane/config.json" in message and "uszkodzony" in message and "linia 3" in message
    assert "popraw" in message and "usuń" in message and "komendą konto" in message
    assert "\n" not in message and "Expecting" not in message              # po polsku, bez angielskiego komunikatu parsera


@pytest.mark.parametrize("text", ["[]", "[1, 2]", '"tekst"', "5", "null", "true"])
def test_a_settings_file_that_is_not_an_object_is_a_plain_error_too(text):
    write_settings_text(text)
    with pytest.raises(config.UserError, match="zły układ"):
        config.settings()


def test_a_settings_file_that_is_not_utf8_is_a_plain_error_too():
    write_settings_text('{"ig_handle": "żółć"}', encoding="cp1250")
    with pytest.raises(config.UserError, match="UTF-8"):
        config.settings()


def test_save_settings_does_not_overwrite_a_damaged_file():
    write_settings_text("{nie json")
    with pytest.raises(config.UserError, match="uszkodzony"):
        config.save_settings({"ig_handle": "przyklad.konto"})
    assert config.SETTINGS.read_text(encoding="utf-8") == "{nie json"


def test_stored_settings_of_a_missing_or_empty_file_are_an_empty_dict():
    assert config.stored_settings() == {}
    write_settings_text("{}")
    assert config.stored_settings() == {}
    write_settings_text("\ufeff" + '{"daily_max": 4}')                       # BOM z Notatnika nie szkodzi
    assert config.stored_settings() == {"daily_max": 4}


# --- JSON ------------------------------------------------------------------

def test_read_json_returns_default_for_missing_file(tmp_path):
    assert config.read_json(tmp_path / "nie-ma.json", {"a": 1}) == {"a": 1}


def test_read_json_reports_broken_file_with_its_path(tmp_path):
    broken = tmp_path / "zepsuty.json"
    broken.write_text("{nie json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError, match="zepsuty.json"):
        config.read_json(broken, {})


def test_read_json_accepts_bom(tmp_path):
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + '{"a": "żółć"}'.encode("utf-8"))
    assert config.read_json(path, None) == {"a": "żółć"}


def test_write_json_format_and_creates_folders(tmp_path):
    target = tmp_path / "a" / "b" / "plik.json"
    obj = {"imię": "Zażółć", "lista": [1, 2]}
    config.write_json(target, obj)
    assert target.read_text(encoding="utf-8") == json.dumps(obj, ensure_ascii=False, indent=1)
    assert b"\r" not in target.read_bytes()  # LF także na Windowsie
    assert "Zażółć".encode("utf-8") in target.read_bytes()


def test_write_json_failure_keeps_old_file_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "stan.json"
    config.write_json(target, {"v": 1})
    with pytest.raises(TypeError):
        config.write_json(target, {"v": object()})
    assert config.read_json(target, None) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["stan.json"]


def test_write_json_replaces_atomically_and_cleans_up_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "stan.json"
    config.write_json(target, {"v": 1})
    calls = []

    def blocked(src, dst):
        calls.append((Path(src).name, Path(dst).name))
        raise OSError("plik zablokowany")

    with monkeypatch.context() as m:
        m.setattr(config.os, "replace", blocked)
        with pytest.raises(OSError):
            config.write_json(target, {"v": 2})
    assert len(calls) == 1 and calls[0][1] == "stan.json" and calls[0][0] != "stan.json"
    assert config.read_json(target, None) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["stan.json"]


def blocked_then_free(monkeypatch, failures):
    """Atrapa `os.replace`: pierwsze `failures` wywołań kończy się PermissionError, potem podmienia plik naprawdę.

    Zwraca listę czasów oczekiwania, które kod zamówił między próbami (czas nie płynie naprawdę).
    """
    real_replace, waits, attempts = config.os.replace, [], []

    def replace(src, dst):
        attempts.append(1)
        if len(attempts) <= failures:
            raise PermissionError("plik jest otwarty w innym programie")
        return real_replace(src, dst)

    monkeypatch.setattr(config.os, "replace", replace)
    monkeypatch.setattr(config.time, "sleep", waits.append)
    return waits, attempts


def test_write_json_retries_a_blocked_replace_five_times_every_tenth_of_a_second(tmp_path, monkeypatch):
    target = tmp_path / "stan.json"
    config.write_json(target, {"v": 1})
    waits, attempts = blocked_then_free(monkeypatch, failures=5)
    config.write_json(target, {"v": 2})
    assert len(attempts) == 6 and waits == [0.1] * 5
    assert config.read_json(target, None) == {"v": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["stan.json"]


def test_write_json_gives_up_after_the_fifth_retry_and_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "stan.json"
    config.write_json(target, {"v": 1})
    waits, attempts = blocked_then_free(monkeypatch, failures=99)
    with pytest.raises(PermissionError):
        config.write_json(target, {"v": 2})
    assert len(attempts) == 6 and waits == [0.1] * 5
    assert config.read_json(target, None) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["stan.json"]


def test_write_json_does_not_wait_when_the_first_replace_works(tmp_path, monkeypatch):
    waits, attempts = blocked_then_free(monkeypatch, failures=0)
    config.write_json(tmp_path / "stan.json", {"v": 1})
    assert len(attempts) == 1 and waits == []


def test_every_file_replacement_goes_through_the_one_function_with_retries():
    """Na Windowsie podmiana świeżo zapisanego pliku bywa odrzucona (antywirus, indeksator), więc każda podmiana idzie przez
    `config._replace`. Test szuka w kodzie programu i narzędzi wywołań, które podmieniają albo przenoszą plik same."""
    found = []
    for path in sorted([*CODE.joinpath("trial_reels").glob("*.py"), *CODE.joinpath("tools").glob("*.py")]):
        if path.name == "config.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            name, owner = node.func.attr, node.func.value
            own_module = isinstance(owner, ast.Name) and owner.id in ("os", "shutil")
            one_path_argument = len(node.args) == 1 and not node.keywords      # Path.replace(cel) i Path.rename(cel)
            if (own_module and name in ("replace", "rename", "move")) or (one_path_argument and name in ("replace", "rename")):
                found.append("%s:%d" % (path.name, node.lineno))
    assert found == []


def test_one_line_helper_and_say_have_one_definition_each():
    from trial_reels import __main__ as cli
    from trial_reels import update, versions

    assert config.line("a\n  b\t c ") == "a b c" and config.line(ValueError("dwie\nlinie")) == "dwie linie"
    for module in (cli, versions, update):
        assert not hasattr(module, "_line"), module.__name__
    assert cli.say is versions.say


# --- .env ------------------------------------------------------------------

def test_env_reads_key_without_quotes():
    config.ENV.parent.mkdir(parents=True, exist_ok=True)
    config.ENV.write_text('ZERNIO_API_KEY="abc123"\n', encoding="utf-8")
    assert config.env()["ZERNIO_API_KEY"] == "abc123"


def test_env_parsing_edge_cases():
    write_env("# komentarz\n\n  A = 1 \nB='dwa'\nC=trzy=cztery\nD=\"\"\nbez_rownosci\n")
    assert config.env() == {"A": "1", "B": "dwa", "C": "trzy=cztery", "D": ""}


def test_env_tolerates_bom_and_windows_line_endings():
    config.ENV.parent.mkdir(parents=True, exist_ok=True)
    config.ENV.write_bytes(b"\xef\xbb\xbfZERNIO_API_KEY=abc123\r\nINNE=2\r\n")
    assert config.env() == {"ZERNIO_API_KEY": "abc123", "INNE": "2"}


@pytest.mark.skipif(os.name == "nt", reason="prawa 600 dotyczą Maca i Linuksa")
def test_reading_the_key_file_narrows_its_rights_to_the_owner():
    """D5: plik utworzony ręcznie (umask 022) czytają inne konta komputera, więc odczyt zawęża prawa do 600."""
    write_env("ZERNIO_API_KEY=abc123\n")
    os.chmod(config.ENV, 0o644)
    assert config.env()["ZERNIO_API_KEY"] == "abc123"
    assert config.ENV.stat().st_mode & 0o777 == 0o600


def test_create_env_makes_the_template_once_and_never_overwrites():
    assert config.create_env() is True
    assert config.ENV.read_bytes() == b"ZERNIO_API_KEY=\n"
    config.ENV.write_text("ZERNIO_API_KEY=abc123\n", encoding="utf-8")
    assert config.create_env() is False and config.env()["ZERNIO_API_KEY"] == "abc123"
    if os.name != "nt":
        assert config.ENV.stat().st_mode & 0o777 == 0o600


def test_env_without_file_is_empty(monkeypatch):
    monkeypatch.setenv("INNA_ZMIENNA", "x")
    assert config.env() == {}


def test_env_prefers_key_from_environment(monkeypatch):
    write_env("ZERNIO_API_KEY=z-pliku\nINNE=1\n")
    monkeypatch.setenv("ZERNIO_API_KEY", "ze-zmiennej")
    assert config.env() == {"ZERNIO_API_KEY": "ze-zmiennej", "INNE": "1"}


def test_key_from_the_environment_loses_spaces_and_line_ends(monkeypatch):
    """D3: koniec linii z wartości zmiennej trafiłby do nagłówka, a błąd nagłówka pokazałby cały klucz."""
    monkeypatch.setenv("ZERNIO_API_KEY", "  klucz-ze-zmiennej\r\n")
    assert config.env()["ZERNIO_API_KEY"] == "klucz-ze-zmiennej"


def test_blank_key_in_the_environment_does_not_hide_the_key_file(monkeypatch):
    write_env("ZERNIO_API_KEY=z-pliku\n")
    monkeypatch.setenv("ZERNIO_API_KEY", " \n")
    assert config.env()["ZERNIO_API_KEY"] == "z-pliku"


def test_env_takes_key_from_environment_when_file_is_missing(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "ze-zmiennej")
    assert config.env() == {"ZERNIO_API_KEY": "ze-zmiennej"}


# --- narzędzia -------------------------------------------------------------

def test_ffmpeg_exe_points_to_existing_binary():
    assert Path(config.ffmpeg_exe()).is_file()


def fake_home(monkeypatch, tmp_path, suffix=""):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(config, "EXE_SUFFIX", suffix)


def touch_uv(tmp_path, folder, name="uv"):
    path = tmp_path / folder / "bin" / name
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")
    return path


def test_uv_exe_prefers_the_one_on_path(monkeypatch, tmp_path):
    fake_home(monkeypatch, tmp_path)
    touch_uv(tmp_path, ".local")
    monkeypatch.setattr(config.shutil, "which", lambda name: "/jakies/miejsce/uv" if name == "uv" else None)
    assert config.uv_exe() == "/jakies/miejsce/uv"


def test_uv_exe_falls_back_to_local_bin_then_cargo_bin(monkeypatch, tmp_path):
    fake_home(monkeypatch, tmp_path)
    assert config.uv_exe() is None
    cargo = touch_uv(tmp_path, ".cargo")
    assert config.uv_exe() == str(cargo)
    local = touch_uv(tmp_path, ".local")
    assert config.uv_exe() == str(local)


def test_uv_exe_uses_exe_suffix_on_windows(monkeypatch, tmp_path):
    fake_home(monkeypatch, tmp_path, suffix=".exe")
    touch_uv(tmp_path, ".local", "uv")  # bez .exe to nie jest uv z Windowsa
    assert config.uv_exe() is None
    exe = touch_uv(tmp_path, ".cargo", "uv.exe")
    assert config.uv_exe() == str(exe)


# --- D6: dane, które trafiają do ścieżek -----------------------------------

@pytest.mark.parametrize("code", ["T1", "Cabc123XYZ_", "a-b_c", "A" * 64])
def test_codes_that_may_become_part_of_a_file_name(code):
    assert config.code_ok(code) and config.checked_code(code) == code


@pytest.mark.parametrize("code", ["", "A" * 65, "../x", "a/b", "a\\b", "a.b", "kod z spacja", "C:x", "ą", None, 12])
def test_codes_that_may_not_become_part_of_a_file_name(code):
    assert not config.code_ok(code)
    with pytest.raises(config.UserError) as caught:
        config.checked_code(code)
    assert "\n" not in str(caught.value) and "dane/pula.json" in str(caught.value)


@pytest.mark.parametrize("vid", ["TR-001", "TR-999", "TR-1000"])
def test_version_ids_that_may_become_part_of_a_file_name(vid):
    assert config.version_id_ok(vid) and config.checked_version_id(vid) == vid


@pytest.mark.parametrize("vid", ["TR-01", "TR-001x", "tr-001", "TR-001/..", "../TR-001", "TR-\u0661\u0662\u0663", "", None, 1])
def test_version_ids_that_may_not_become_part_of_a_file_name(vid):
    assert not config.version_id_ok(vid)
    with pytest.raises(config.UserError) as caught:
        config.checked_version_id(vid)
    assert "\n" not in str(caught.value) and "TR-001" in str(caught.value)


def test_within_resolves_dots_and_links_before_it_says_a_path_is_inside(tmp_path):
    folder = tmp_path / "dane" / "wersje"
    folder.mkdir(parents=True)
    outside = tmp_path / "prywatne.jpg"
    outside.write_bytes(b"x")
    assert config.within(folder / "TR-001.mp4", folder)                     # pliku jeszcze nie ma, ale leżałby w folderze
    assert not config.within(folder / ".." / ".." / "prywatne.jpg", folder)
    assert not config.within(outside, folder)
    if os.name != "nt":
        (folder / "TR-002.mp4").symlink_to(outside)
        assert not config.within(folder / "TR-002.mp4", folder)              # dowiązanie wyprowadza poza folder
