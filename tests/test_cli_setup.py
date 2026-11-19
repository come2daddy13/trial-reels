"""Testy komend konfiguracji: doktor, konto, kandydaci, pula, pobieranie, transkrypcja, sprawdzanie puli i kadr.

Sieć, Zernio i model Whispera są atrapami: żaden test nie łączy się z prawdziwym serwisem ani niczego nie zapisuje
poza własnym folderem klienta. Kody rolek i nicki są wymyślone.
"""
import json
import os
import socket
import ssl
import subprocess
import sys
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

import faster_whisper
import numpy as np
import pytest
from PIL import Image

from trial_reels import __main__ as cli
from trial_reels import candidates, config, doctor, planner, render, stats, transcribe, zernio

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
CODE = "Cabc123XYZ_"
A, B, C, D, E = "Aaaaaa1", "Bbbbbb2", "Cccccc3", "Ddddd44", "Eeeee55"
ACCOUNTS = [{"_id": "acc-1", "username": "przyklad.konto", "platform": "instagram"}]
OLD = "2026-09-01T08:00:00.000Z"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline_and_fixed_clock(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("sieć w testach tylko przez atrapę")

    monkeypatch.setattr(zernio, "_urlopen", refuse)
    monkeypatch.setattr(zernio.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(cli, "now", lambda: NOW.astimezone(planner.TZ))


@pytest.fixture
def run(capsys):
    def go(*argv):
        rc = cli.main(list(argv))
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    return go


def with_account(handle="przyklad.konto"):
    config.save_settings({"ig_account_id": "acc-1", "ig_handle": handle})


def fake_zernio(monkeypatch, posts=(), accounts=()):
    """Atrapa Zernio: konta i statystyki z listy, każde wywołanie `analytics` zapisane do `calls`."""
    calls = []
    monkeypatch.setattr(zernio, "accounts", lambda: list(accounts))

    def analytics(account_id, from_date, to_date):
        calls.append((account_id, from_date, to_date))
        return list(posts)

    monkeypatch.setattr(zernio, "analytics", analytics)
    return calls


def cand(code, views, follows=None, **extra):
    c = {"code": code, "url": "https://www.instagram.com/reel/%s/" % code, "pk": candidates.media_id(code),
         "views": views, "likes": 0, "comments": 0, "shares": 0, "saves": 0, "published": OLD,
         "caption": "Podpis rolki %s" % code, "media_url": "https://cdn.example.com/%s.mp4" % code}
    if follows is not None:
        c["panel_follows"] = follows
    c.update(extra)
    return c


def pool_codes():
    return [r["code"] for r in candidates.load_pool()]


# --- doktor ---------------------------------------------------------------------

def test_doktor_prints_a_table_and_fails_on_a_problem(monkeypatch, run):
    rows = [{"nazwa": "Jeden", "ok": True, "info": "działa"}, {"nazwa": "Dwa", "ok": False, "info": "nie działa"}]
    monkeypatch.setattr(doctor, "checks", lambda: rows)
    rc, out, err = run("doktor")
    assert rc == 1
    assert "✓ Jeden: działa" in out and "✗ Dwa: nie działa" in out


def test_doktor_succeeds_when_everything_is_fine(monkeypatch, run):
    monkeypatch.setattr(doctor, "checks", lambda: [{"nazwa": "Jeden", "ok": True, "info": "działa"}])
    rc, out, err = run("doktor")
    assert rc == 0 and "✓ Jeden: działa" in out and "✗" not in out


# --- klucz ----------------------------------------------------------------------

SECRET = "klucz-testowy-" + "x9" * 10          # wymyślony, tylko do sprawdzenia, że nigdzie się nie pojawia


@pytest.fixture
def editor(monkeypatch):
    """Atrapa edytora: zapisuje, jakie pliki otworzyłby klientowi."""
    opened = []
    monkeypatch.setattr(cli, "_open_editor", lambda path: opened.append(Path(path)) or True)
    return opened


def rights(path):
    return path.stat().st_mode & 0o777


def put_key_file(text, name=".env"):
    config.DATA.mkdir(parents=True, exist_ok=True)
    path = config.DATA / name
    path.write_text(text, encoding="utf-8")
    return path


def test_klucz_creates_the_key_file_with_owner_only_rights_and_opens_it(run, editor):
    rc, out, err = run("klucz")
    assert rc == 0 and err == ""
    assert config.ENV.read_text(encoding="utf-8") == "ZERNIO_API_KEY=\n"
    if os.name != "nt":
        assert rights(config.ENV) == 0o600                     # inne konta na tym Macu pliku nie przeczytają
    assert editor == [config.ENV]
    assert "za znakiem =" in out and "czatu" in out and "krok" in out


def test_klucz_never_overwrites_or_shows_an_existing_key(run, editor):
    path = put_key_file("ZERNIO_API_KEY=%s\n" % SECRET)
    if os.name != "nt":
        os.chmod(path, 0o644)
    rc, out, err = run("klucz")
    assert rc == 0 and SECRET not in out + err
    assert path.read_text(encoding="utf-8") == "ZERNIO_API_KEY=%s\n" % SECRET
    if os.name != "nt":
        assert rights(path) == 0o600
    assert "jest już klucz" in out and editor == [config.ENV]


def test_klucz_moves_a_key_that_notepad_saved_as_env_txt(run, editor):
    put_key_file("ZERNIO_API_KEY=\n")
    put_key_file("ZERNIO_API_KEY=%s\r\n" % SECRET, ".env.txt")
    rc, out, err = run("klucz")
    assert rc == 0 and SECRET not in out + err and ".env.txt" in out
    assert not (config.DATA / ".env.txt").exists() and config.env()["ZERNIO_API_KEY"] == SECRET
    if os.name != "nt":
        assert rights(config.ENV) == 0o600
    assert editor == []                                             # klucz już jest, edytor nie jest potrzebny


def test_klucz_leaves_env_txt_alone_when_the_key_file_already_has_a_key(run, editor):
    put_key_file("ZERNIO_API_KEY=%s\n" % SECRET)
    other = put_key_file("ZERNIO_API_KEY=inny-klucz\n", ".env.txt")
    rc, out, err = run("klucz")
    assert rc == 0 and other.is_file() and config.env()["ZERNIO_API_KEY"] == SECRET and editor == [config.ENV]


def test_klucz_without_an_editor_is_one_polish_line_and_the_file_stays(run, monkeypatch):
    monkeypatch.setattr(cli, "_open_editor", lambda path: False)
    rc, out, err = run("klucz")
    assert rc == 1 and one_plain_line(err) and "dane/.env" in err and config.ENV.is_file()


@pytest.mark.parametrize("platform,program", [("darwin", ["open", "-e"]), ("win32", ["notepad.exe"])])
def test_the_editor_is_textedit_on_a_mac_and_notepad_on_windows(monkeypatch, tmp_path, platform, program):
    seen = []

    class Done:
        returncode = 0

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return Done()

    def fake_popen(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return Done()

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    path = tmp_path / "dane" / ".env"
    assert cli._open_editor(path) is True
    (cmd, kwargs), = seen
    assert cmd == program + [str(path)]
    assert all(kwargs.get(stream) is subprocess.DEVNULL for stream in ("stdin", "stdout", "stderr"))  # nie czeka


def test_the_editor_is_not_guessed_on_other_systems(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    assert cli._open_editor(tmp_path / ".env") is False


# --- konto ----------------------------------------------------------------------

def test_konto_saves_the_only_account_and_tests_reading(monkeypatch, run, make_post):
    posts = [make_post(A, published=OLD), make_post(B, published=OLD, product="FEED", media_type="IMAGE")]
    calls = fake_zernio(monkeypatch, posts=posts, accounts=ACCOUNTS)
    rc, out, err = run("konto")
    assert rc == 0 and err == ""
    settings = config.settings()
    assert settings["ig_account_id"] == "acc-1" and settings["ig_handle"] == "przyklad.konto"
    assert "@przyklad.konto" in out and "Rolek z ostatnich 30 dni: 1" in out
    account, since, until = calls[0]
    assert account == "acc-1" and until == date(2026, 11, 18) and (until - since).days == 30


def test_konto_with_several_accounts_lists_them_and_asks_for_a_nick(monkeypatch, run):
    accounts = ACCOUNTS + [{"_id": "acc-2", "username": "drugie.konto", "platform": "instagram"}]
    fake_zernio(monkeypatch, accounts=accounts)
    rc, out, err = run("konto")
    assert rc == 0
    assert "@przyklad.konto" in out and "@drugie.konto" in out and "--nick" in out
    assert config.settings()["ig_account_id"] is None


def test_konto_nick_picks_an_account_ignoring_at_sign_and_case(monkeypatch, run):
    accounts = ACCOUNTS + [{"_id": "acc-2", "username": "drugie.konto", "platform": "instagram"}]
    fake_zernio(monkeypatch, accounts=accounts)
    rc, out, err = run("konto", "--nick", "@Drugie.KONTO")
    assert rc == 0
    assert config.settings()["ig_account_id"] == "acc-2" and config.settings()["ig_handle"] == "drugie.konto"


def test_konto_unknown_nick_names_the_connected_accounts(monkeypatch, run):
    fake_zernio(monkeypatch, accounts=ACCOUNTS)
    rc, out, err = run("konto", "--nick", "nie.ma.takiego")
    assert rc == 1 and "@nie.ma.takiego" in err and "@przyklad.konto" in err
    assert config.settings()["ig_account_id"] is None


def test_konto_without_any_account_says_how_to_connect(monkeypatch, run):
    fake_zernio(monkeypatch, accounts=[])
    rc, out, err = run("konto")
    assert rc == 1 and "nie ma podłączonego konta Instagrama" in err


def test_konto_keeps_the_account_when_the_reading_test_fails(monkeypatch, run):
    fake_zernio(monkeypatch, accounts=ACCOUNTS)

    def refused(account_id, from_date, to_date):
        raise zernio.ZernioError("GET /analytics -> 402: plan", 402)

    monkeypatch.setattr(zernio, "analytics", refused)
    rc, out, err = run("konto")
    assert rc == 0 and config.settings()["ig_account_id"] == "acc-1"
    assert "Uwaga" in out and "test odczytu" in out


def test_konto_changes_only_the_account_settings(monkeypatch, run):
    config.save_settings({"timezone": "Europe/Berlin", "ig_account_id": "stare", "ig_handle": "stare.konto"})
    fake_zernio(monkeypatch, accounts=ACCOUNTS)
    rc, out, err = run("konto")
    assert rc == 0
    settings = config.settings()
    assert settings["timezone"] == "Europe/Berlin" and settings["ig_account_id"] == "acc-1"


# --- uruchomienie z wiersza poleceń ---------------------------------------------

def run_cli(tmp_path, *argv, shadow=None):
    """Uruchamia `python -m trial_reels ...` w osobnym procesie na pustym folderze klienta (bez sieci)."""
    env = {**os.environ, "PYTHONUTF8": "1", "TRIAL_REELS_ROOT": str(tmp_path / "klient")}
    if shadow:
        env["PYTHONPATH"] = str(shadow)
    return subprocess.run([sys.executable, "-m", "trial_reels", *argv], cwd=REPO, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=180)


def test_doktor_passes_on_this_computer(tmp_path):
    done = run_cli(tmp_path, "doktor")
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.count("✓") == 10 and "✗" not in done.stdout and "Wszystko gra" in done.stdout


def test_doktor_still_reports_when_a_package_is_broken(tmp_path):
    """Zepsuty pakiet (tu PyAV) nie może wywrócić doktora, bo to on ma o tym powiedzieć."""
    shadow = tmp_path / "zepsute"
    shadow.mkdir()
    (shadow / "av.py").write_text("raise ImportError('DLL load failed while importing av')\n", encoding="utf-8")
    done = run_cli(tmp_path, "doktor", shadow=shadow)
    assert done.returncode == 1 and "Traceback" not in done.stderr, done.stderr
    assert "✗ Pakiety Pythona" in done.stdout and "DLL load failed" in done.stdout
    assert "✓ Python 3.12 lub nowszy" in done.stdout and "✓ ffmpeg z kodekiem H.264" in done.stdout


def test_commands_that_need_no_heavy_packages_start_without_them(tmp_path):
    shadow = tmp_path / "zepsute"
    shadow.mkdir()
    for name in ("av", "PIL", "numpy"):
        (shadow / (name + ".py")).write_text("raise ImportError('zepsuty pakiet')\n", encoding="utf-8")
    for argv in (("wersja",), ("js-odczyt",), ("pula",)):
        done = run_cli(tmp_path, *argv, shadow=shadow)
        assert done.returncode == 0, (argv, done.stderr)


# --- błędy jako jedna linia -----------------------------------------------------

def one_plain_line(err):
    lines = [line for line in err.splitlines() if line.strip()]
    return len(lines) == 1 and "Traceback" not in err


def test_missing_key_is_one_plain_line_without_a_stack_trace(run):
    rc, out, err = run("konto")
    assert rc == 1 and one_plain_line(err)
    assert "klucza Zernio" in err and "dane/.env" in err and "klucz" in err


def test_a_key_with_forbidden_characters_is_one_plain_line_that_never_shows_the_key(run, monkeypatch):
    secret = "zly klucz-" + "x9" * 8
    monkeypatch.setenv("ZERNIO_API_KEY", secret)
    rc, out, err = run("konto")
    assert rc == 1 and one_plain_line(err) and "x9x9" not in out + err
    assert err.startswith("Klucz Zernio") and "komendę klucz" in err


def test_a_key_problem_stops_a_batch_like_a_missing_key():
    from trial_reels import versions

    assert versions.is_systemic(zernio.ZernioError("klucz Zernio ma niedozwolone znaki", key=True))
    assert versions.is_systemic(zernio.ZernioError("brak klucza Zernio w dane/.env", key=True))
    assert not versions.is_systemic(zernio.ZernioError("PUT 418"))


def test_network_failure_is_one_plain_line(monkeypatch, run):
    def offline():
        raise urllib.error.URLError("nodename nor servname provided, or not known")

    monkeypatch.setattr(zernio, "accounts", offline)
    rc, out, err = run("konto")
    assert rc == 1 and one_plain_line(err) and "internet" in err


@pytest.mark.parametrize("status,needle", [(401, "klucz"), (403, "klucz"), (402, "płatn"), (429, "poczekaj"),
                                           (503, "awari")])
def test_zernio_refusals_are_explained_in_plain_polish(monkeypatch, run, status, needle):
    def refused():
        raise zernio.ZernioError("GET /accounts -> %d: {\"error\": \"x\"}" % status, status)

    monkeypatch.setattr(zernio, "accounts", refused)
    rc, out, err = run("konto")
    assert rc == 1 and one_plain_line(err) and needle in err.lower()
    assert "{" not in err                                          # surowa odpowiedź serwera nie trafia do klienta


@pytest.mark.parametrize("problem", [ssl.SSLError("certificate verify failed"), socket.gaierror(8, "no such host"),
                                     ConnectionResetError("reset"), TimeoutError("timed out")])
def test_other_network_failures_are_explained_as_no_connection(monkeypatch, run, problem):
    def broken():
        raise problem

    monkeypatch.setattr(zernio, "accounts", broken)
    rc, out, err = run("konto")
    assert rc == 1 and one_plain_line(err) and "internet" in err


def test_other_zernio_errors_keep_their_message(monkeypatch, run):
    def odd():
        raise zernio.ZernioError("GET /accounts -> 418: czajniczek", 418)

    monkeypatch.setattr(zernio, "accounts", odd)
    rc, out, err = run("konto")
    assert rc == 1 and one_plain_line(err) and "418" in err


def test_a_damaged_data_file_is_one_plain_line_naming_the_file(run):
    config.POOL.parent.mkdir(parents=True, exist_ok=True)
    config.POOL.write_text("{to nie jest json", encoding="utf-8")
    rc, out, err = run("pula")
    assert rc == 1 and one_plain_line(err) and "pula.json" in err


def test_a_bug_is_not_hidden_behind_a_friendly_message(monkeypatch):
    def broken():
        raise RuntimeError("błąd w kodzie")

    monkeypatch.setattr(doctor, "checks", broken)
    with pytest.raises(RuntimeError, match="błąd w kodzie"):
        cli.main(["doktor"])


def test_ctrl_c_ends_quietly(monkeypatch, run):
    def interrupted():
        raise KeyboardInterrupt

    monkeypatch.setattr(doctor, "checks", interrupted)
    rc, out, err = run("doktor")
    assert rc == 130 and "Przerwano" in err


# --- kandydaci ------------------------------------------------------------------

def test_kandydaci_saves_the_list_and_prints_the_table(monkeypatch, run, make_post):
    with_account()
    posts = [make_post(A, 500, published=OLD, caption="Pierwszy podpis"),
             make_post(B, 12345, published="2026-06-30T10:00:00.000Z", caption="Drugi podpis\nz nową linią", media=False),
             make_post(C, 700, published=OLD, product="FEED", media_type="IMAGE"),
             make_post(D, 99999, published="2026-11-17T10:00:00.000Z")]
    calls = fake_zernio(monkeypatch, posts=posts)
    rc, out, err = run("kandydaci", "--ile", "5")
    assert rc == 0
    saved = json.loads(config.CANDIDATES.read_text(encoding="utf-8"))
    assert [c["code"] for c in saved] == [B, A]
    assert saved[0]["views"] == 12345 and saved[0]["media_url"] is None
    rows = [line for line in out.splitlines() if line.startswith((B, A))]
    assert len(rows) == 2
    assert "2026-06-30" in rows[0] and "12 345" in rows[0] and "nie" in rows[0] and "Drugi podpis z nową linią" in rows[0]
    assert "2026-09-01" in rows[1] and "tak" in rows[1] and "Pierwszy podpis" in rows[1]
    account, since, until = calls[0]
    assert account == "acc-1" and until == date(2026, 11, 18) and since == date(2025, 11, 18)


def test_kandydaci_takes_months_and_count_from_the_options(monkeypatch, run, make_post):
    with_account()
    posts = [make_post("Aaaaaa%d" % i, 100 + i, published=OLD) for i in range(6)]
    calls = fake_zernio(monkeypatch, posts=posts)
    rc, out, err = run("kandydaci", "--miesiace", "3", "--ile", "4")
    assert rc == 0 and calls[0][1] == date(2026, 8, 18)
    assert len(json.loads(config.CANDIDATES.read_text(encoding="utf-8"))) == 4


def test_kandydaci_default_is_25_reels_from_12_months(monkeypatch, run, make_post):
    with_account()
    posts = [make_post("Aaaaa%02d" % i, 100 + i, published=OLD) for i in range(30)]
    calls = fake_zernio(monkeypatch, posts=posts)
    assert run("kandydaci")[0] == 0
    assert len(json.loads(config.CANDIDATES.read_text(encoding="utf-8"))) == 25 and calls[0][1] == date(2025, 11, 18)


def test_kandydaci_needs_an_account(monkeypatch, run):
    fake_zernio(monkeypatch)
    rc, out, err = run("kandydaci")
    assert rc == 1 and "konto" in err and not config.CANDIDATES.exists()


def test_kandydaci_keeps_panel_readings_from_the_previous_list(monkeypatch, run, make_post):
    with_account()
    candidates.save_candidates([cand(A, 400, follows=9, panel_views=12345, panel_read_at="2026-11-17T10:00")])
    fake_zernio(monkeypatch, posts=[make_post(A, 450, published=OLD), make_post(B, 300, published=OLD)])
    rc, out, err = run("kandydaci")
    assert rc == 0
    saved = {c["code"]: c for c in candidates.load_candidates()}
    assert saved[A]["views"] == 450 and saved[A]["panel_follows"] == 9 and saved[A]["panel_views"] == 12345
    assert "panel_follows" not in saved[B]
    assert "Obserwujący" in out                                    # tabela pokazuje kolumnę, gdy są odczyty


def test_kandydaci_without_readings_has_no_follows_column(monkeypatch, run, make_post):
    with_account()
    fake_zernio(monkeypatch, posts=[make_post(A, 450, published=OLD)])
    rc, out, err = run("kandydaci")
    assert rc == 0 and "Obserwujący" not in out


def test_kandydaci_explains_an_empty_result_and_keeps_the_old_list(monkeypatch, run, make_post):
    with_account()
    candidates.save_candidates([cand(A, 400)])
    fake_zernio(monkeypatch, posts=[make_post(B, 300, published="2026-11-16T10:00:00.000Z")])  # za świeża
    rc, out, err = run("kandydaci")
    assert rc == 1 and "Nie ma rolek" in err
    assert [c["code"] for c in candidates.load_candidates()] == [A]


# --- wynik-kandydata ------------------------------------------------------------

def test_wynik_kandydata_reads_abbreviated_numbers(run):
    candidates.save_candidates([cand(A, 400), cand(B, 300)])
    rc, out, err = run("wynik-kandydata", A, "--wyswietlenia", "12,3 tys.", "--obserwujacy", "9")
    assert rc == 0 and A in out and "12 300" in out and "9" in out
    saved = {c["code"]: c for c in candidates.load_candidates()}
    assert saved[A]["panel_views"] == 12300 and saved[A]["panel_follows"] == 9 and saved[A]["panel_read_at"]
    assert "panel_follows" not in saved[B]


def test_wynik_kandydata_overwrites_an_older_reading_and_accepts_a_link(run):
    candidates.save_candidates([cand(A, 400, follows=3, panel_views=1000)])
    link = "https://www.instagram.com/reel/%s/?igsh=abc" % A
    rc, out, err = run("wynik-kandydata", link, "--wyswietlenia", "1,2 mln", "--obserwujacy", "1\u00a0234")
    assert rc == 0
    saved = candidates.load_candidates()[0]
    assert saved["panel_views"] == 1200000 and saved["panel_follows"] == 1234


def test_wynik_kandydata_unknown_reel_and_bad_number_are_plain_errors(run):
    candidates.save_candidates([cand(A, 400)])
    rc, out, err = run("wynik-kandydata", B, "--wyswietlenia", "10", "--obserwujacy", "1")
    assert rc == 1 and B in err and "kandydaci" in err
    rc, out, err = run("wynik-kandydata", A, "--wyswietlenia", "bardzo dużo", "--obserwujacy", "1")
    assert rc == 1 and "Nie rozumiem liczby" in err and "bardzo dużo" in err
    assert "panel_follows" not in candidates.load_candidates()[0]


def test_wynik_kandydata_needs_the_candidate_list(run):
    rc, out, err = run("wynik-kandydata", A, "--wyswietlenia", "10", "--obserwujacy", "1")
    assert rc == 1 and "kandydaci" in err


# --- js-odczyt ------------------------------------------------------------------

def test_js_odczyt_prints_the_script_and_nothing_else(run):
    rc, out, err = run("js-odczyt")
    assert rc == 0 and out.strip() == stats.JS_ODCZYT.strip() and err == ""


# --- pula -----------------------------------------------------------------------

def test_pula_adds_candidates_without_duplicates(run):
    candidates.save_candidates([cand(A, 400), cand(B, 300), cand(C, 200)])
    rc, out, err = run("pula", A, B, A)
    assert rc == 0 and pool_codes() == [A, B]
    entry = candidates.load_pool()[0]
    assert entry == {"code": A, "name": "Podpis rolki Aaaaaa1", "media_id": candidates.media_id(A),
                     "caption": "Podpis rolki %s" % A, "active": True, "hook_y": 0.17}
    rc, out, err = run("pula", B, C)
    assert rc == 0 and pool_codes() == [A, B, C] and "Już jest w puli: %s" % B in out


def test_pula_never_touches_an_entry_the_client_already_edited(run):
    candidates.save_candidates([cand(A, 400)])
    candidates.save_pool([{"code": A, "name": "Moja nazwa", "media_id": "1", "caption": "x", "active": False,
                           "hook_y": 0.4, "cta": "coś"}])
    rc, out, err = run("pula", A)
    assert rc == 0 and candidates.load_pool()[0]["name"] == "Moja nazwa" and candidates.load_pool()[0]["hook_y"] == 0.4


def test_pula_accepts_a_link_instead_of_a_code(run):
    candidates.save_candidates([cand(A, 400)])
    rc, out, err = run("pula", "https://www.instagram.com/reel/%s/" % A)
    assert rc == 0 and pool_codes() == [A]


def test_pula_unknown_code_is_reported_but_the_rest_is_added(run):
    candidates.save_candidates([cand(A, 400)])
    rc, out, err = run("pula", B, A)
    assert rc == 1 and B in err and "kandydaci" in err
    assert pool_codes() == [A]


def test_pula_needs_the_candidate_list(run):
    rc, out, err = run("pula", A)
    assert rc == 1 and "kandydaci" in err and not config.POOL.exists()


def test_pool_auto_prefers_follows_then_views(run):
    candidates.save_candidates([cand(A, 5000), cand(B, 100, follows=9), cand(C, 900, follows=9),
                                cand(D, 10, follows=30), cand(E, 8000, follows=0)])
    rc, out, err = run("pula", "--auto", "3")
    assert rc == 0 and pool_codes() == [D, C, B]
    assert "słabsza miara" not in out and "słabsza miara" not in err


def test_pula_auto_without_readings_goes_by_views_and_says_it_is_weaker(run):
    candidates.save_candidates([cand(A, 100), cand(B, 900), cand(C, 500)])
    rc, out, err = run("pula", "--auto", "2")
    assert rc == 0 and pool_codes() == [B, C]
    assert "to słabsza miara" in out


def test_pula_auto_without_a_number_fills_the_pool_to_twelve(run):
    candidates.save_candidates([cand("Aaaaa%02d" % i, 1000 - i) for i in range(15)])
    rc, out, err = run("pula", "--auto")
    assert rc == 0 and len(pool_codes()) == 12 and pool_codes()[0] == "Aaaaa00"


def test_pula_auto_fills_the_pool_up_to_the_goal(run):
    candidates.save_candidates([cand(A, 900), cand(B, 800), cand(C, 700), cand(D, 600)])
    candidates.save_pool([candidates.pool_entry(cand(C, 700))])
    rc, out, err = run("pula", "--auto", "3")
    assert rc == 0 and pool_codes() == [C, A, B]
    rc, out, err = run("pula", "--auto", "3")
    assert rc == 0 and pool_codes() == [C, A, B] and "Nic nie dopisuję" in out


def test_pula_auto_counts_only_active_reels(run):
    candidates.save_candidates([cand(A, 900), cand(B, 800)])
    off = candidates.pool_entry(cand(C, 700))
    off["active"] = False
    candidates.save_pool([off])
    rc, out, err = run("pula", "--auto", "1")
    assert rc == 0 and pool_codes() == [C, A]


def test_pula_without_arguments_shows_the_pool(run):
    rc, out, err = run("pula")
    assert rc == 0 and "Pula jest pusta" in out
    candidates.save_pool([candidates.pool_entry(cand(A, 400))])
    config.SRC.mkdir(parents=True)
    (config.SRC / ("%s.mp4" % A)).write_bytes(b"film")
    rc, out, err = run("pula")
    assert rc == 0 and A in out and "Rolek w puli: 1" in out


# --- pobierz --------------------------------------------------------------------

def pool_of(*codes):
    entries = [candidates.pool_entry(cand(code, 100)) for code in codes]
    candidates.save_pool(entries)
    return entries


def fake_downloads(monkeypatch, failing=()):
    """Atrapa pobierania: zapisuje plik z napisem „film” i zapamiętuje (adres, plik). `failing` to kody z błędem."""
    done = []

    def download(url, dest, tries=3):
        if any(code in url for code in failing):
            raise zernio.ZernioError("nie udało się pobrać pliku z %s: zerwane połączenie" % url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"film " + url.encode())
        done.append((url, dest))
        return dest

    monkeypatch.setattr(zernio, "download", download)
    return done


def test_pobierz_marks_missing_file(monkeypatch, run, make_post):
    with_account()
    pool_of(A, B, C)
    config.SRC.mkdir(parents=True)
    (config.SRC / ("%s.mp4" % C)).write_bytes(b"juz jest")
    posts = [make_post(A, published=OLD), make_post(B, published=OLD, media=False), make_post(C, published=OLD)]
    calls = fake_zernio(monkeypatch, posts=posts)
    done = fake_downloads(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 0
    assert [url for url, _ in done] == ["https://cdn.example.com/%s.mp4" % A]
    assert (config.SRC / ("%s.mp4" % A)).is_file() and not (config.SRC / ("%s.mp4" % B)).exists()
    assert (config.SRC / ("%s.mp4" % C)).read_bytes() == b"juz jest"
    pool = {r["code"]: r for r in candidates.load_pool()}
    assert pool[B]["brak_pliku"] is True and "brak_pliku" not in pool[A] and "brak_pliku" not in pool[C]
    assert all(r["active"] is True for r in pool.values())                  # pobierz nie wyłącza rolek
    assert "wrzuć oryginał jako dane/src/%s.mp4 albo wyłącz rolkę" % B in out
    assert len(calls) == 1 and calls[0][0] == "acc-1"                         # jedno odczytanie statystyk dla wszystkich


def test_pobierz_clears_a_stale_missing_flag_after_a_download(monkeypatch, run, make_post):
    with_account()
    entries = pool_of(A)
    entries[0]["brak_pliku"] = True
    candidates.save_pool(entries)
    fake_zernio(monkeypatch, posts=[make_post(A, published=OLD)])
    fake_downloads(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 0 and "brak_pliku" not in candidates.load_pool()[0]


def test_pobierz_clears_the_flag_when_the_client_dropped_the_original_in(monkeypatch, run):
    with_account()
    entries = pool_of(A)
    entries[0]["brak_pliku"] = True
    candidates.save_pool(entries)
    config.SRC.mkdir(parents=True)
    (config.SRC / ("%s.mp4" % A)).write_bytes(b"wlasny oryginal")
    calls = fake_zernio(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 0 and calls == [] and "brak_pliku" not in candidates.load_pool()[0]
    assert "mają już pliki" in out


def test_pobierz_goes_on_after_a_failed_download(monkeypatch, run, make_post):
    with_account()
    pool_of(A, B)
    fake_zernio(monkeypatch, posts=[make_post(A, published=OLD), make_post(B, published=OLD)])
    done = fake_downloads(monkeypatch, failing=(A,))
    rc, out, err = run("pobierz")
    assert rc == 1 and not (config.SRC / ("%s.mp4" % A)).exists() and (config.SRC / ("%s.mp4" % B)).is_file()
    assert A in err and "nie udało się pobrać" in err.lower()
    assert [url for url, _ in done] == ["https://cdn.example.com/%s.mp4" % B]
    assert "brak_pliku" not in candidates.load_pool()[0]                     # chwilowy błąd sieci to nie brak pliku


def test_pobierz_marks_a_reel_that_zernio_does_not_know(monkeypatch, run, make_post):
    with_account()
    pool_of(A, B)
    fake_zernio(monkeypatch, posts=[make_post(A, published=OLD)])
    fake_downloads(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 0 and candidates.load_pool()[1]["brak_pliku"] is True


def test_pobierz_skips_switched_off_reels_and_reels_with_files(monkeypatch, run):
    with_account()
    entries = pool_of(A, B)
    entries[0]["active"] = False
    candidates.save_pool(entries)
    config.SRC.mkdir(parents=True)
    (config.SRC / ("%s.mp4" % B)).write_bytes(b"film")
    calls = fake_zernio(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 0 and calls == [] and "mają już pliki" in out


def test_pobierz_window_reaches_back_to_old_reels(monkeypatch, run):
    """Rolka sprzed lat musi się mieścić w oknie statystyk, więc okno sięga czasu zapisanego w ID mediów."""
    with_account()
    old_pk = str(((int(datetime(2023, 5, 1, tzinfo=timezone.utc).timestamp() * 1000) - candidates.IG_EPOCH_MS) << 23) | 7)
    entries = pool_of(A)
    entries[0]["media_id"] = old_pk
    candidates.save_pool(entries)
    calls = fake_zernio(monkeypatch)
    fake_downloads(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 0
    account, since, until = calls[0]
    assert since <= date(2023, 5, 1) and (date(2023, 5, 1) - since).days <= 10 and until == date(2026, 11, 18)


def test_pobierz_window_is_at_least_a_year_for_recent_or_unknown_reels(monkeypatch, run):
    with_account()
    entries = pool_of(A, B)
    entries[0]["media_id"] = "nie-liczba"
    del entries[1]["media_id"]
    candidates.save_pool(entries)
    calls = fake_zernio(monkeypatch)
    fake_downloads(monkeypatch)
    run("pobierz")
    assert calls[0][1] == date(2025, 11, 18)


def test_pobierz_needs_an_account_and_a_pool(monkeypatch, run):
    fake_zernio(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 1 and "pula" in err.lower()
    pool_of(A)
    rc, out, err = run("pobierz")
    assert rc == 1 and "konto" in err


def test_commands_skip_pool_entries_whose_code_is_not_a_reel_code(monkeypatch, run, make_post):
    """Kod trafia do nazwy pliku, więc wpis z adresem zamiast kodu nie dostaje pliku i nie psuje reszty."""
    with_account()
    bad = candidates.pool_entry(cand(A, 100))
    bad["code"] = "https://www.instagram.com/reel/%s/" % B
    candidates.save_pool([bad, candidates.pool_entry(cand(C, 100))])
    fake_zernio(monkeypatch, posts=[make_post(C, published=OLD)])
    done = fake_downloads(monkeypatch)
    rc, out, err = run("pobierz")
    assert rc == 0 and [url for url, _ in done] == ["https://cdn.example.com/%s.mp4" % C]
    assert [p.name for p in config.SRC.iterdir()] == ["%s.mp4" % C]
    rc, out, err = run("sprawdz-pule")
    assert rc == 1 and "niedozwolone znaki" in out


# --- transkrybuj ----------------------------------------------------------------

class FakeModel:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        FakeModel.instances.append(self)

    def transcribe(self, audio, **kwargs):
        return iter([]), None


@pytest.fixture
def fake_whisper(monkeypatch):
    FakeModel.instances = []
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    monkeypatch.setattr(transcribe, "_MODEL_CACHE", {})
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(1600, dtype=np.float32))
    monkeypatch.setattr(transcribe, "model_cached", lambda model=transcribe.DEFAULT_MODEL: True)
    return FakeModel


def put_video(code):
    config.SRC.mkdir(parents=True, exist_ok=True)
    (config.SRC / ("%s.mp4" % code)).write_bytes(b"film")


def put_transcript(code, text="stara transkrypcja"):
    config.write_json(config.TRANSCRIPTS / ("%s.json" % code), {"segments": [], "uwaga": text})


def test_transkrybuj_does_only_what_is_missing_and_loads_the_model_once(run, fake_whisper):
    entries = pool_of(A, B, C, D, E)
    entries[3]["active"] = False                       # D jest wyłączona
    candidates.save_pool(entries)
    for code in (A, B, D, E):
        put_video(code)                                # C nie ma pliku
    put_transcript(A)                                  # A ma już transkrypcję
    rc, out, err = run("transkrybuj")
    assert rc == 0
    assert json.loads((config.TRANSCRIPTS / ("%s.json" % A)).read_text(encoding="utf-8"))["uwaga"] == "stara transkrypcja"
    assert (config.TRANSCRIPTS / ("%s.json" % B)).is_file() and (config.TRANSCRIPTS / ("%s.json" % E)).is_file()
    assert not (config.TRANSCRIPTS / ("%s.json" % C)).exists() and not (config.TRANSCRIPTS / ("%s.json" % D)).exists()
    assert len(fake_whisper.instances) == 1                                # model ładuje się raz na cały przebieg
    assert "Transkrypcja 1 z 2" in out and "Transkrypcja 2 z 2" in out
    assert "%s: nie ma pliku" % C in out and "pobierz" in out


def test_transkrybuj_warns_before_the_first_model_download(monkeypatch, run, capsys, fake_whisper):
    monkeypatch.setattr(transcribe, "model_cached", lambda model=transcribe.DEFAULT_MODEL: False)
    pool_of(A)
    put_video(A)
    seen = []
    real = transcribe.transcribe

    def spy(src, out, *args, **kwargs):
        seen.append(capsys.readouterr().out)           # to, co wydrukowano, zanim zaczęła się praca
        return real(src, out, *args, **kwargs)

    monkeypatch.setattr(transcribe, "transcribe", spy)
    rc = cli.main(["transkrybuj"])
    assert rc == 0 and "1,6 GB" in seen[0] and "minut" in seen[0]


def test_transkrybuj_stays_quiet_when_the_model_is_already_on_disk(run, fake_whisper):
    pool_of(A)
    put_video(A)
    rc, out, err = run("transkrybuj")
    assert rc == 0 and "1,6 GB" not in out and "1,6 GB" not in err


def test_transkrybuj_reports_a_reel_without_sound_and_goes_on(monkeypatch, run, fake_whisper):
    pool_of(A, B)
    put_video(A)
    put_video(B)
    real = transcribe.transcribe

    def maybe(src, out, *args, **kwargs):
        if A in str(src):
            raise RuntimeError("W pliku %s nie ma dźwięku, więc nie da się zrobić transkrypcji." % src)
        return real(src, out, *args, **kwargs)

    monkeypatch.setattr(transcribe, "transcribe", maybe)
    rc, out, err = run("transkrybuj")
    assert rc == 1 and "nie ma dźwięku" in err and A in err
    assert (config.TRANSCRIPTS / ("%s.json" % B)).is_file() and not (config.TRANSCRIPTS / ("%s.json" % A)).exists()


def test_transkrybuj_model_problem_is_one_plain_line(monkeypatch, run, fake_whisper):
    pool_of(A, B)
    put_video(A)
    put_video(B)
    attempts = []

    def no_model(src, out, *args, **kwargs):
        attempts.append(src)
        raise OSError("Cannot reach the model server")

    monkeypatch.setattr(transcribe, "transcribe", no_model)
    rc, out, err = run("transkrybuj")
    assert rc == 1 and one_plain_line(err) and "modelu" in err and "internet" in err
    assert len(attempts) == 1                                  # nie męczymy sieci przy każdej rolce z osobna


def test_transkrybuj_with_nothing_to_do(run, fake_whisper):
    rc, out, err = run("transkrybuj")
    assert rc == 1 and "puli" in err
    pool_of(A)
    put_video(A)
    put_transcript(A)
    rc, out, err = run("transkrybuj")
    assert rc == 0 and "gotowe" in out and fake_whisper.instances == []


# --- sprawdz-pule ---------------------------------------------------------------

def test_sprawdz_pule_says_the_pool_is_ready(run, make_reel, make_hooks, put_reel_files):
    candidates.save_pool([make_reel(CODE), make_reel("Dddddd44")])
    config.write_json(config.HOOKS, {CODE: make_hooks(), "Dddddd44": make_hooks(4)})
    put_reel_files(CODE)
    put_reel_files("Dddddd44")
    rc, out, err = run("sprawdz-pule")
    assert rc == 0 and "Pula gotowa: 2 rolek" in out


def test_sprawdz_pule_lists_the_problems(run, make_reel, make_hooks, put_reel_files):
    candidates.save_pool([make_reel(CODE), make_reel("Dddddd44")])
    config.write_json(config.HOOKS, {CODE: make_hooks(), "Dddddd44": make_hooks(1)})
    put_reel_files(CODE)
    put_reel_files("Dddddd44", transcript=False)
    rc, out, err = run("sprawdz-pule")
    assert rc == 1 and "Pula gotowa" not in out
    problem_lines = [line for line in out.splitlines() if line.startswith("- ")]
    assert len(problem_lines) >= 2 and all("Dddddd44" in line for line in problem_lines)
    assert any("transkrypcji" in line for line in problem_lines) and any("hooków" in line for line in problem_lines)


def speechless_pool(make_reel, make_hooks, put_reel_files):
    """Pula z jedną rolką bez mowy (pusta transkrypcja) i bez pól strong i cuts."""
    reel = make_reel(CODE)
    del reel["strong"], reel["cuts"]
    candidates.save_pool([reel])
    config.write_json(config.HOOKS, {CODE: make_hooks()})
    put_reel_files(CODE, transcript=False)
    config.write_json(config.TRANSCRIPTS / ("%s.json" % CODE), {"segments": []})


def test_sprawdz_pule_passes_a_reel_without_speech_and_says_so(run, make_reel, make_hooks, put_reel_files):
    speechless_pool(make_reel, make_hooks, put_reel_files)
    rc, out, err = run("sprawdz-pule")
    assert rc == 0 and err == "" and "Pula gotowa: 1 rolek" in out
    info = [line for line in out.splitlines() if "bez mowy" in line]
    assert len(info) == 1 and info[0].startswith("Informacja: ") and CODE in info[0]
    assert "W puli są problemy" not in out


def test_sprawdz_pule_keeps_the_speech_note_next_to_real_problems(run, make_reel, make_hooks, put_reel_files):
    speechless_pool(make_reel, make_hooks, put_reel_files)
    config.write_json(config.HOOKS, {CODE: make_hooks(1)})                   # za mało hooków
    rc, out, err = run("sprawdz-pule")
    assert rc == 1 and "W puli są problemy:" in out and "Pula gotowa" not in out
    assert any(line.startswith("- ") and "hooków" in line for line in out.splitlines())
    assert any(line.startswith("Informacja: ") and "bez mowy" in line for line in out.splitlines())


def test_sprawdz_pule_does_not_mention_speech_for_a_reel_that_has_it(run, make_reel, make_hooks, put_reel_files):
    candidates.save_pool([make_reel(CODE)])
    config.write_json(config.HOOKS, {CODE: make_hooks()})
    put_reel_files(CODE)
    rc, out, err = run("sprawdz-pule")
    assert rc == 0 and "Informacja" not in out and "bez mowy" not in out


def test_sprawdz_pule_counts_only_active_reels(run, make_reel, make_hooks, put_reel_files):
    off = make_reel("Dddddd44")
    off["active"] = False
    candidates.save_pool([make_reel(CODE), off])
    config.write_json(config.HOOKS, {CODE: make_hooks()})
    put_reel_files(CODE)
    rc, out, err = run("sprawdz-pule")
    assert rc == 0 and "Pula gotowa: 1 rolek" in out


def test_sprawdz_pule_with_no_active_reels_is_a_problem(run, make_reel):
    rc, out, err = run("sprawdz-pule")
    assert rc == 1 and "Pula jest pusta" in out
    off = make_reel()
    off["active"] = False
    candidates.save_pool([off])
    rc, out, err = run("sprawdz-pule")
    assert rc == 1 and "Pula jest pusta" in out


# --- kadr -----------------------------------------------------------------------

def make_clip(path, seconds=2, size="360x640"):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([config.ffmpeg_exe(), "-nostdin", "-hide_banner", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=s=%s:r=30:d=%s" % (size, seconds),
                    "-f", "lavfi", "-i", "sine=f=440:d=%s" % seconds,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   check=True, capture_output=True, encoding="utf-8", errors="replace")
    return path


def test_kadr_writes_a_still_with_the_hook(run):
    pool_of(CODE)
    make_clip(config.SRC / ("%s.mp4" % CODE))
    rc, out, err = run("kadr", CODE, "--hook", "Hook na próbę", "--emoji", "🔥", "--t", "0.5")
    still = config.OUT / ("kadr_%s.jpg" % CODE)
    assert rc == 0 and out.strip() == str(still) and still.is_file()
    with Image.open(still) as im:
        assert im.size == (1080, 1920)


def test_kadr_default_hook_is_the_first_one_from_the_bank(monkeypatch, run, make_hooks):
    entries = pool_of(CODE)
    config.write_json(config.HOOKS, {CODE: make_hooks(3)})
    put_video(CODE)
    seen = {}

    def spy(reel, text, emoji, t, out):
        seen.update(reel=reel, text=text, emoji=emoji, t=t, out=out)
        out.write_bytes(b"jpg")
        return out

    monkeypatch.setattr(render, "hook_frame", spy)
    rc, out, err = run("kadr", CODE)
    first = make_hooks(1)[0]
    assert rc == 0 and seen["text"] == first["text"] and seen["emoji"] == first["emoji"] and seen["t"] == 1.0
    assert seen["reel"]["code"] == CODE and seen["out"] == config.OUT / ("kadr_%s.jpg" % CODE)
    assert entries[0]["hook_y"] == seen["reel"]["hook_y"]


def test_kadr_takes_the_hook_text_and_emoji_by_id_from_the_bank(monkeypatch, run, make_hooks):
    """D2: tekst z & albo % nie przechodzi przez wiersz poleceń (cmd.exe w PowerShellu), tylko z dane/hooki.json."""
    pool_of(CODE)
    bank = make_hooks(3)
    bank[1]["text"] = "50% taniej & szybciej"
    config.write_json(config.HOOKS, {CODE: bank})
    put_video(CODE)
    seen = {}

    def spy(reel, text, emoji, t, out):
        seen.update(text=text, emoji=emoji)
        out.write_bytes(b"jpg")
        return out

    monkeypatch.setattr(render, "hook_frame", spy)
    rc, out, err = run("kadr", CODE, "--hook-id", "h02")
    assert rc == 0 and seen == {"text": "50% taniej & szybciej", "emoji": bank[1]["emoji"]}
    rc, out, err = run("kadr", CODE, "--hook-id", "h02", "--emoji", bank[0]["emoji"])
    assert rc == 0 and seen == {"text": "50% taniej & szybciej", "emoji": bank[0]["emoji"]}


def test_kadr_with_an_unknown_hook_id_names_the_ids_it_knows(run, make_hooks):
    pool_of(CODE)
    put_video(CODE)
    rc, out, err = run("kadr", CODE, "--hook-id", "h01")
    assert rc == 1 and one_plain_line(err) and "hooki.json" in err
    config.write_json(config.HOOKS, {CODE: make_hooks(2)})
    rc, out, err = run("kadr", CODE, "--hook-id", "h09")
    assert rc == 1 and one_plain_line(err) and "h09" in err and "h01, h02" in err


def test_kadr_takes_either_a_hook_text_or_a_hook_id():
    with pytest.raises(SystemExit) as caught:
        cli.build_parser().parse_args(["kadr", CODE, "--hook", "Hook", "--hook-id", "h01"])
    assert caught.value.code == 2


def test_kadr_without_a_hook_bank_uses_a_sample_text(monkeypatch, run):
    pool_of(CODE)
    put_video(CODE)
    seen = {}

    def spy(reel, text, emoji, t, out):
        seen.update(text=text, emoji=emoji)
        out.write_bytes(b"jpg")
        return out

    monkeypatch.setattr(render, "hook_frame", spy)
    rc, out, err = run("kadr", CODE, "--hook", "Własny hook")
    assert rc == 0 and seen["text"] == "Własny hook"
    rc, out, err = run("kadr", CODE)
    assert rc == 0 and seen["text"] and len(seen["text"]) <= 50 and seen["emoji"] in render.emoji_set()


def test_kadr_warns_about_an_emoji_that_is_not_in_the_set(monkeypatch, run):
    pool_of(CODE)
    put_video(CODE)
    monkeypatch.setattr(render, "hook_frame", lambda reel, text, emoji, t, out: out.write_bytes(b"jpg") and out)
    rc, out, err = run("kadr", CODE, "--hook", "Hook", "--emoji", "🦄")
    assert rc == 0 and "Uwaga" in out and "🦄" in out and "assets/emoji" in out


def test_kadr_reports_missing_pieces_in_plain_polish(run):
    rc, out, err = run("kadr", CODE)
    assert rc == 1 and CODE in err and "pula" in err
    pool_of(CODE)
    rc, out, err = run("kadr", CODE)
    assert rc == 1 and "dane/src/%s.mp4" % CODE in err and "pobierz" in err


def test_kadr_past_the_end_of_the_clip_is_a_plain_error(run):
    pool_of(CODE)
    clip = make_clip(config.SRC / ("%s.mp4" % CODE), seconds=1)
    rc, out, err = run("kadr", CODE, "--t", "30")
    assert rc == 1 and one_plain_line(err) and out == ""
    assert "Film ma tylko %s s" % render.fmt(render.probe(clip)) in err and "klatki z 30 s" in err and "--t" in err


def test_kadr_past_the_end_prints_exactly_one_polish_line_and_no_ffmpeg_noise(capfd):
    """Sprawdzamy prawdziwe wyjście procesu (także to, co pisze podproces ffmpeg), a nie tylko sys.stderr."""
    pool_of(CODE)
    clip = make_clip(config.SRC / ("%s.mp4" % CODE), seconds=1)
    assert cli.main(["kadr", CODE, "--t", "8"]) == 1
    captured = capfd.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert captured.out == "" and len(lines) == 1, captured.err
    assert lines[0].startswith("Film ma tylko %s s" % render.fmt(render.probe(clip)))
    assert "ffmpeg" not in lines[0].lower() and "Traceback" not in captured.err
    assert not (config.OUT / ("kadr_%s.jpg" % CODE)).exists()


def test_kadr_that_fails_keeps_the_previous_frame_of_the_same_reel(run):
    pool_of(CODE)
    make_clip(config.SRC / ("%s.mp4" % CODE), seconds=1)
    still = config.OUT / ("kadr_%s.jpg" % CODE)
    assert run("kadr", CODE, "--t", "0.5")[0] == 0
    before = still.read_bytes()
    rc, out, err = run("kadr", CODE, "--t", "30")
    assert rc == 1 and one_plain_line(err) and still.read_bytes() == before
    assert [p.name for p in config.OUT.iterdir()] == [still.name]


def test_kadr_refuses_a_code_that_could_leave_the_data_folder(run):
    """D6: kod z argumentu i z puli trafia do nazwy klatki (kadr_KOD.jpg) i do ścieżki źródła."""
    candidates.save_pool([{"code": "../../poza", "name": "x", "active": True}])
    rc, out, err = run("kadr", "../../poza")
    assert rc == 1 and one_plain_line(err) and "kod" in err.lower()
    assert not list(config.ROOT.parent.rglob("kadr_*"))


def test_kadr_accepts_a_link_instead_of_a_code(monkeypatch, run):
    pool_of(CODE)
    put_video(CODE)
    monkeypatch.setattr(render, "hook_frame", lambda reel, text, emoji, t, out: out.write_bytes(b"jpg") and out)
    rc, out, err = run("kadr", "https://www.instagram.com/reel/%s/" % CODE, "--hook", "Hook")
    assert rc == 0 and out.strip().endswith("kadr_%s.jpg" % CODE)
