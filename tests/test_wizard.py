"""Testy kreatora kroków: stan 12 kroków z plików w dane/, alerty i komenda `krok`.

Doktor jest atrapą (prawdziwy sprawdza komputer, na którym biegną testy), reszta to prawdziwe pliki w folderze klienta.
Kody rolek, nicki i klucz są wymyślone.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import trial_reels
from trial_reels import __main__ as cli
from trial_reels import candidates, config, doctor, planner, state, wizard

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)      # 13:00 w Warszawie, jutro to 2026-11-19
CODE = "Cabc123XYZ_"
OTHER = "Cdef456UVW-"
KEY = "klucz-testowy-123456"
BEFORE_WEEK = ("powitanie", "programy", "zernio", "konto", "zwyciezcy", "pliki", "ustawienia", "hooki", "pierwsze",
               "pomiar")
TOMORROW_SLOT = "2026-11-19T09:00:00"
TODAY_SLOT = "2026-11-18T18:00:00"


# --- pomocnicy ------------------------------------------------------------------

def good_doctor(monkeypatch, ok=True, names=("Pakiety Pythona",)):
    rows = [{"nazwa": name, "ok": ok, "info": "szczegóły %s" % name} for name in names]
    monkeypatch.setattr(doctor, "checks", lambda: rows)


def version(n, status, slot=TOMORROW_SLOT, **extra):
    return {"id": "TR-%03d" % n, "code": CODE, "level": "subtelna", "hook_id": "h01", "slot": slot,
            "status": status, **extra}


def save_versions(*items):
    state.save({"seq": len(items), "versions": {v["id"]: v for v in items}, "brake": {"on": False}})


def step(result, step_id):
    return next(k for k in result["kroki"] if k["id"] == step_id)


def ready_ids(result):
    return [k["id"] for k in result["kroki"] if k["gotowy"]]


class Client:
    """Kolejne etapy konfiguracji folderu klienta (każda metoda robi to, co zrobiłby krok kreatora)."""

    def __init__(self, make_reel, make_hooks, put_reel_files):
        self.make_reel, self.make_hooks, self.put_files = make_reel, make_hooks, put_reel_files

    def welcome(self):
        wizard.mark("powitanie")

    def key(self, value=KEY):
        config.ENV.parent.mkdir(parents=True, exist_ok=True)
        config.ENV.write_text("ZERNIO_API_KEY=%s\n" % value, encoding="utf-8")

    def account(self):
        config.save_settings({"ig_account_id": "acc-1", "ig_handle": "przyklad.konto"})

    def pool(self, *codes):
        candidates.save_pool([self.make_reel(code) for code in (codes or (CODE,))])

    def files(self, *codes):
        for code in codes or (CODE,):
            self.put_files(code)

    def settings(self):
        pool = candidates.load_pool()
        for reel in pool:
            reel["ustawienia_ok"] = True
        candidates.save_pool(pool)

    def hooks(self):
        pool = candidates.load_pool()
        for reel in pool:
            reel["hooki_ok"] = True
        candidates.save_pool(pool)
        config.write_json(config.HOOKS, {reel["code"]: self.make_hooks() for reel in pool})

    def started(self, slot=TOMORROW_SLOT):
        save_versions(version(1, "zaplanowana", slot))

    def until(self, last="pomiar"):
        """Wszystkie kroki do `last` włącznie (domyślnie do pomiaru, czyli wszystko przed zadaniem tygodniowym)."""
        order = [("powitanie", self.welcome), ("zernio", self.key), ("konto", self.account), ("zwyciezcy", self.pool),
                 ("pliki", self.files), ("ustawienia", self.settings), ("hooki", self.hooks),
                 ("pierwsze", self.started), ("pomiar", lambda: wizard.mark("pomiar"))]
        for name, action in order:
            action()
            if name == last:
                return


@pytest.fixture
def client(monkeypatch, make_reel, make_hooks, put_reel_files):
    good_doctor(monkeypatch)
    monkeypatch.setattr(cli, "now", lambda: NOW.astimezone(planner.TZ))
    return Client(make_reel, make_hooks, put_reel_files)


@pytest.fixture
def run(capsys):
    def go(*argv):
        rc = cli.main(list(argv))
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    return go


# --- lista kroków i kształt wyniku ----------------------------------------------

def test_steps_are_the_twelve_from_the_plan():
    assert wizard.STEPS == (
        ("powitanie", "Powitanie"), ("programy", "Programy"), ("zernio", "Zernio i klucz"),
        ("konto", "Konto Instagram"), ("zwyciezcy", "Zwycięskie rolki"), ("pliki", "Pliki i transkrypcje"),
        ("ustawienia", "Ustawienia rolek"), ("hooki", "Hooki i podpisy"), ("pierwsze", "Pierwsze wersje"),
        ("pomiar", "Pomiar wyników"), ("tydzien", "Paczka co tydzień"), ("codziennie", "Na co dzień"))


def test_status_has_the_promised_shape(client):
    result = wizard.status(NOW)
    assert set(result) == {"kroki", "nastepny", "alerty"}
    assert [k["id"] for k in result["kroki"]] == [i for i, _ in wizard.STEPS]
    assert [k["tytul"] for k in result["kroki"]] == [t for _, t in wizard.STEPS]
    for k in result["kroki"]:
        assert set(k) == {"id", "tytul", "gotowy", "szczegoly"}
        assert isinstance(k["gotowy"], bool) and isinstance(k["szczegoly"], str) and k["szczegoly"]
    assert isinstance(result["alerty"], list)
    assert json.loads(json.dumps(result, ensure_ascii=False)) == result


def test_status_reads_files_and_writes_nothing(client):
    result = wizard.status(NOW, run_doctor=False)
    assert result["nastepny"] == "powitanie"
    assert not config.DATA.exists()                       # pusty folder zostaje pusty


def test_status_does_not_change_existing_files(client):
    client.until("hooki")
    snapshot = {p: p.read_bytes() for p in config.DATA.rglob("*") if p.is_file()}
    wizard.status(NOW)
    assert {p: p.read_bytes() for p in config.DATA.rglob("*") if p.is_file()} == snapshot


# --- kolejność kroków (test z planu) --------------------------------------------

def test_wizard_walks_steps_in_order(client):
    def nxt():
        return wizard.status(NOW)["nastepny"]

    assert nxt() == "powitanie"                           # pusty folder
    client.welcome()
    assert nxt() == "zernio"                              # doktor (atrapa) mówi, że komputer jest gotowy
    client.key()
    assert nxt() == "konto"
    client.account()
    assert nxt() == "zwyciezcy"
    client.pool()
    assert nxt() == "pliki"
    client.files()
    assert nxt() == "ustawienia"
    client.settings()
    assert nxt() == "hooki"
    client.hooks()
    assert nxt() == "pierwsze"
    client.started()
    assert nxt() == "pomiar"
    wizard.mark("pomiar")
    assert nxt() == "tydzien"
    wizard.mark("tydzien")
    assert nxt() == "codziennie"
    wizard.mark("codziennie")
    result = wizard.status(NOW)
    assert result["nastepny"] is None and all(k["gotowy"] for k in result["kroki"])


def test_next_step_is_the_first_unfinished_one_even_when_later_ones_are_ready(client):
    client.until("hooki")
    wizard.mark("pomiar")
    config.ENV.unlink()
    result = wizard.status(NOW)
    assert result["nastepny"] == "zernio"
    assert step(result, "pomiar")["gotowy"] and step(result, "hooki")["gotowy"]


# --- kroki oparte o wpis w kreatorze --------------------------------------------

@pytest.mark.parametrize("step_id", ["powitanie", "pomiar", "tydzien", "codziennie"])
def test_entry_steps_are_ready_when_marked(client, step_id):
    assert not step(wizard.status(NOW), step_id)["gotowy"]
    wizard.mark(step_id)
    assert step(wizard.status(NOW), step_id)["gotowy"]
    assert config.read_json(config.WIZARD) == {step_id: "tak"}


def test_the_marked_value_is_shown_in_the_details(client):
    wizard.mark("pomiar", "reczny")
    details = step(wizard.status(NOW), "pomiar")["szczegoly"]
    assert "reczny" in details


def test_mark_keeps_earlier_entries_and_overwrites_the_same_step(client):
    wizard.mark("powitanie")
    wizard.mark("pomiar", "chrome")
    wizard.mark("pomiar", "reczny")
    assert config.read_json(config.WIZARD) == {"powitanie": "tak", "pomiar": "reczny"}


def test_mark_rejects_unknown_steps_and_blank_values(client):
    with pytest.raises(config.UserError) as caught:
        wizard.mark("nie-ma-takiego")
    assert "powitanie" in str(caught.value) and "codziennie" in str(caught.value)
    assert not config.WIZARD.exists()
    wizard.mark("powitanie", "   ")
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}


def test_mark_refuses_a_wizard_file_with_the_wrong_shape(client):
    config.write_json(config.WIZARD, ["to", "nie", "obiekt"])
    with pytest.raises(config.UserError, match="kreator.json"):
        wizard.mark("powitanie")


# --- programy -------------------------------------------------------------------

def test_programy_follow_the_doctor(client, monkeypatch):
    assert step(wizard.status(NOW), "programy")["gotowy"]
    good_doctor(monkeypatch, ok=False, names=("Pakiety Pythona", "Font Poppins"))
    result = wizard.status(NOW)
    details = step(result, "programy")["szczegoly"]
    assert not step(result, "programy")["gotowy"]
    assert "Pakiety Pythona" in details and "Font Poppins" in details and "doktor" in details


def test_programy_list_only_the_failed_checks(client, monkeypatch):
    rows = [{"nazwa": "Dobra kontrola", "ok": True, "info": "ok"}, {"nazwa": "Zła kontrola", "ok": False, "info": "x"}]
    monkeypatch.setattr(doctor, "checks", lambda: rows)
    details = step(wizard.status(NOW), "programy")["szczegoly"]
    assert "Zła kontrola" in details and "Dobra kontrola" not in details


def test_programy_without_the_doctor_need_an_entry(client, monkeypatch):
    def boom():
        raise AssertionError("doktor nie powinien się uruchomić")

    monkeypatch.setattr(doctor, "checks", boom)
    assert not step(wizard.status(NOW, run_doctor=False), "programy")["gotowy"]
    wizard.mark("programy")
    assert step(wizard.status(NOW, run_doctor=False), "programy")["gotowy"]


def test_the_entry_for_programy_does_not_hide_a_failing_doctor(client, monkeypatch):
    wizard.mark("programy")
    good_doctor(monkeypatch, ok=False)
    assert not step(wizard.status(NOW), "programy")["gotowy"]


def test_a_crashing_doctor_does_not_crash_the_wizard(client, monkeypatch):
    def broken():
        raise RuntimeError("coś poszło nie tak")

    monkeypatch.setattr(doctor, "checks", broken)
    result = wizard.status(NOW)
    assert not step(result, "programy")["gotowy"] and "Nie udało się sprawdzić" in step(result, "programy")["szczegoly"]
    assert result["nastepny"] == "powitanie"


# --- zernio, konto, zwycięzcy ---------------------------------------------------

def test_zernio_needs_a_key_and_never_shows_it(client):
    assert not step(wizard.status(NOW), "zernio")["gotowy"]
    client.key()
    result = wizard.status(NOW)
    assert step(result, "zernio")["gotowy"]
    assert KEY not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize("text", ["", "ZERNIO_API_KEY=\n", "ZERNIO_API_KEY=   \n", "# ZERNIO_API_KEY=cos\n", "INNY=cos\n"])
def test_zernio_is_not_ready_without_a_value(client, text):
    config.ENV.parent.mkdir(parents=True, exist_ok=True)
    config.ENV.write_text(text, encoding="utf-8")
    assert not step(wizard.status(NOW), "zernio")["gotowy"]


def test_zernio_counts_the_key_from_the_environment_too(client, monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", KEY)
    result = wizard.status(NOW)
    assert step(result, "zernio")["gotowy"] and KEY not in json.dumps(result)


def test_konto_needs_the_saved_account_id(client):
    assert not step(wizard.status(NOW), "konto")["gotowy"]
    config.save_settings({"ig_handle": "przyklad.konto"})                      # sam nick to za mało
    assert not step(wizard.status(NOW), "konto")["gotowy"]
    client.account()
    result = step(wizard.status(NOW), "konto")
    assert result["gotowy"] and "przyklad.konto" in result["szczegoly"]


def test_zwyciezcy_counts_only_active_reels_with_a_proper_code(client, make_reel):
    assert not step(wizard.status(NOW), "zwyciezcy")["gotowy"]
    inactive = {**make_reel(CODE), "active": False}
    broken = {**make_reel(OTHER), "code": "https://www.instagram.com/reel/%s/" % OTHER}
    candidates.save_pool([inactive, broken, "to nie rolka"])
    assert not step(wizard.status(NOW), "zwyciezcy")["gotowy"]
    candidates.save_pool([inactive, broken, make_reel(OTHER)])
    result = step(wizard.status(NOW), "zwyciezcy")
    assert result["gotowy"] and "1" in result["szczegoly"]


# --- pliki i transkrypcje -------------------------------------------------------

def test_pliki_need_a_video_and_a_transcript_for_every_active_reel(client):
    client.pool(CODE, OTHER)
    client.files(CODE)
    result = step(wizard.status(NOW), "pliki")
    assert not result["gotowy"] and OTHER in result["szczegoly"] and "pobierz" in result["szczegoly"]
    assert CODE not in result["szczegoly"]
    client.files(OTHER)
    assert step(wizard.status(NOW), "pliki")["gotowy"]


def test_pliki_name_the_reels_that_only_lack_a_transcript(client, put_reel_files):
    client.pool(CODE)
    put_reel_files(CODE, transcript=False)
    result = step(wizard.status(NOW), "pliki")
    assert not result["gotowy"] and "transkrybuj" in result["szczegoly"] and CODE in result["szczegoly"]
    assert "pobierz" not in result["szczegoly"]


def test_pliki_explain_reels_that_zernio_has_no_file_for(client):
    client.pool(CODE, OTHER)
    client.files(CODE)
    pool = candidates.load_pool()
    pool[1]["brak_pliku"] = True                                              # tak oznacza ją `pobierz`
    candidates.save_pool(pool)
    result = step(wizard.status(NOW), "pliki")
    assert not result["gotowy"]
    assert OTHER in result["szczegoly"] and "dane/src" in result["szczegoly"] and "active" in result["szczegoly"]


def test_pliki_switching_a_reel_off_unblocks_the_step(client):
    client.pool(CODE, OTHER)
    client.files(CODE)
    pool = candidates.load_pool()
    pool[1].update(brak_pliku=True, active=False)
    candidates.save_pool(pool)
    assert step(wizard.status(NOW), "pliki")["gotowy"]


def test_pliki_are_not_ready_for_an_empty_pool(client):
    assert not step(wizard.status(NOW), "pliki")["gotowy"]
    candidates.save_pool([])
    assert not step(wizard.status(NOW), "pliki")["gotowy"]


def test_pliki_list_at_most_a_few_reels_and_count_the_rest(client):
    codes = ["Crolka%02d" % n for n in range(12)]
    client.pool(*codes)
    details = step(wizard.status(NOW), "pliki")["szczegoly"]
    assert codes[0] in details and codes[-1] not in details and "jeszcze" in details and len(details) < 400


# --- ustawienia i hooki ---------------------------------------------------------

def test_ustawienia_need_the_flag_on_every_active_reel(client):
    client.pool(CODE, OTHER)
    result = step(wizard.status(NOW), "ustawienia")
    assert not result["gotowy"] and CODE in result["szczegoly"] and OTHER in result["szczegoly"]
    pool = candidates.load_pool()
    pool[0]["ustawienia_ok"] = True
    pool[1]["ustawienia_ok"] = "tak"                                           # tylko prawdziwe true się liczy
    candidates.save_pool(pool)
    result = step(wizard.status(NOW), "ustawienia")
    assert not result["gotowy"] and OTHER in result["szczegoly"] and CODE not in result["szczegoly"]
    pool[1]["ustawienia_ok"] = True
    candidates.save_pool(pool)
    assert step(wizard.status(NOW), "ustawienia")["gotowy"]


def test_ustawienia_skip_inactive_reels_and_need_at_least_one_active(client):
    assert not step(wizard.status(NOW), "ustawienia")["gotowy"]
    client.pool(CODE, OTHER)
    pool = candidates.load_pool()
    pool[0]["ustawienia_ok"] = True
    pool[1]["active"] = False
    candidates.save_pool(pool)
    assert step(wizard.status(NOW), "ustawienia")["gotowy"]


def test_hooki_need_the_flag_and_a_clean_pool_check(client):
    client.until("ustawienia")
    result = step(wizard.status(NOW), "hooki")
    assert not result["gotowy"] and CODE in result["szczegoly"]
    client.hooks()
    assert step(wizard.status(NOW), "hooki")["gotowy"]


def test_hooki_are_not_ready_when_the_pool_check_reports_problems(client):
    client.until("hooki")
    hooks = config.read_json(config.HOOKS)
    hooks[CODE][0]["text"] = "x" * 60                                          # ponad limit 50 znaków
    config.write_json(config.HOOKS, hooks)
    result = step(wizard.status(NOW), "hooki")
    assert not result["gotowy"] and "sprawdz-pule" in result["szczegoly"] and "limit" in result["szczegoly"]


def test_hooki_are_ready_for_a_reel_without_speech_that_has_no_strong_and_no_cuts(client):
    client.until("hooki")
    pool = candidates.load_pool()
    for reel in pool:
        reel.pop("strong", None)
        reel.pop("cuts", None)
    candidates.save_pool(pool)
    config.write_json(config.TRANSCRIPTS / ("%s.json" % CODE), {"segments": []})      # nikt w tej rolce nie mówi
    result = step(wizard.status(NOW), "hooki")
    assert result["gotowy"] and "Pula przechodzi sprawdzenie" in result["szczegoly"]


def test_hooki_are_not_ready_without_a_transcript_even_with_the_flag(client):
    client.until("hooki")
    (config.TRANSCRIPTS / ("%s.json" % CODE)).unlink()
    assert not step(wizard.status(NOW), "hooki")["gotowy"]


def test_hooki_survive_a_crashing_pool_check(client, monkeypatch):
    client.until("hooki")

    def boom(pool, hooks):
        raise ImportError("PIL nie działa")

    monkeypatch.setattr(candidates, "validate", boom)
    result = wizard.status(NOW)
    assert not step(result, "hooki")["gotowy"] and "Nie udało się sprawdzić" in step(result, "hooki")["szczegoly"]


# --- pierwsze wersje ------------------------------------------------------------

@pytest.mark.parametrize("status, ready", [("zaplanowana", True), ("opublikowana", True), ("do_akceptacji", False),
                                           ("zaakceptowana", False), ("odrzucona", False), ("blad", False)])
def test_pierwsze_need_a_version_that_reached_zernio(client, status, ready):
    save_versions(version(1, status))
    assert step(wizard.status(NOW), "pierwsze")["gotowy"] is ready


def test_pierwsze_details_say_what_waits_for_acceptance(client):
    save_versions(version(1, "do_akceptacji"), version(2, "do_akceptacji"), version(3, "zaakceptowana"))
    details = step(wizard.status(NOW), "pierwsze")["szczegoly"]
    assert "2" in details and "1" in details


def test_a_damaged_state_file_does_not_crash_the_wizard(client):
    config.STATE.parent.mkdir(parents=True, exist_ok=True)
    config.STATE.write_text("{nie json", encoding="utf-8")
    result = wizard.status(NOW)
    assert not step(result, "pierwsze")["gotowy"] and "stan.json" in step(result, "pierwsze")["szczegoly"]
    assert result["alerty"] == []


def test_a_damaged_pool_file_does_not_crash_the_wizard(client):
    client.until("konto")
    config.POOL.write_text("{nie json", encoding="utf-8")
    result = wizard.status(NOW)
    assert not step(result, "zwyciezcy")["gotowy"] and "pula.json" in step(result, "zwyciezcy")["szczegoly"]
    assert result["nastepny"] == "zwyciezcy"


# --- alerty ---------------------------------------------------------------------

def alerts(now=NOW):
    return wizard.status(now)["alerty"]


def test_alert_no_trials_tomorrow(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TODAY_SLOT), version(2, "opublikowana", "2026-11-17T09:00:00"))
    (alert,) = alerts()
    assert alert.startswith("Na jutro nie ma żadnego triala. Zrób paczkę")
    assert "paczka --dni 7" in alert


def test_no_alert_when_tomorrow_has_a_planned_trial(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TOMORROW_SLOT))
    assert alerts() == []


@pytest.mark.parametrize("status", ["do_akceptacji", "zaakceptowana", "odrzucona", "blad", "opublikowana"])
def test_only_planned_trials_count_for_tomorrow(client, status):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TODAY_SLOT), version(2, status, TOMORROW_SLOT))
    assert any(a.startswith("Na jutro nie ma żadnego triala") for a in alerts())


def test_tomorrow_is_counted_in_the_client_time_zone(client):
    client.until("pomiar")
    late = datetime(2026, 11, 18, 23, 30, tzinfo=timezone.utc)                 # w Warszawie już 19.11, 00:30
    save_versions(version(1, "zaplanowana", TOMORROW_SLOT))                    # 19.11 to już „dziś”
    assert any(a.startswith("Na jutro nie ma żadnego triala") for a in alerts(now=late))
    save_versions(version(1, "zaplanowana", TOMORROW_SLOT), version(2, "zaplanowana", "2026-11-20T09:00:00"))
    assert alerts(now=late) == []


def test_alert_accepts_a_naive_now(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TODAY_SLOT))
    assert any("Na jutro" in a for a in alerts(now=datetime(2026, 11, 18, 13, 0)))


@pytest.mark.parametrize("missing", ["powitanie", "zernio", "konto", "zwyciezcy", "pliki", "ustawienia", "hooki",
                                     "pierwsze", "pomiar"])
def test_no_tomorrow_alert_while_an_earlier_step_is_unfinished(client, missing):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TODAY_SLOT))
    undo = {
        "powitanie": lambda: config.WIZARD.write_text('{"pomiar": "tak"}', encoding="utf-8"),
        "zernio": lambda: config.ENV.unlink(),
        "konto": lambda: config.save_settings({"ig_account_id": None}),
        "zwyciezcy": lambda: candidates.save_pool([]),
        "pliki": lambda: (config.SRC / ("%s.mp4" % CODE)).unlink(),
        "ustawienia": lambda: candidates.save_pool([{**candidates.load_pool()[0], "ustawienia_ok": False}]),
        "hooki": lambda: candidates.save_pool([{**candidates.load_pool()[0], "hooki_ok": False}]),
        "pierwsze": lambda: save_versions(version(1, "do_akceptacji", TODAY_SLOT)),
        "pomiar": lambda: config.WIZARD.write_text('{"powitanie": "tak"}', encoding="utf-8"),
    }
    undo[missing]()
    assert [a for a in alerts() if a.startswith("Na jutro")] == []


def test_the_weekly_step_itself_does_not_have_to_be_ready_for_the_alert(client):
    client.until("pomiar")                                                     # „tydzien” jeszcze niezrobiony
    save_versions(version(1, "zaplanowana", TODAY_SLOT))
    assert not step(wizard.status(NOW), "tydzien")["gotowy"]
    assert any(a.startswith("Na jutro") for a in alerts())


@pytest.mark.parametrize("count, phrase", [(1, "1 wersja z błędem"), (2, "2 wersje z błędem"), (4, "4 wersje z błędem"),
                                           (5, "5 wersji z błędem"), (12, "12 wersji z błędem"),
                                           (22, "22 wersje z błędem")])
def test_alert_counts_versions_with_an_error(client, count, phrase):
    client.until("pomiar")
    save_versions(version(100, "zaplanowana"), *[version(n, "blad", TODAY_SLOT) for n in range(1, count + 1)])
    (alert,) = [a for a in alerts() if "z błędem" in a]
    assert phrase in alert and "status" in alert and "\n" not in alert


def test_alert_ignores_errors_that_already_have_a_replacement(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana"), version(2, "blad", replaced_by="TR-003"), version(3, "zaplanowana"))
    assert alerts() == []
    save_versions(version(1, "zaplanowana"), version(2, "blad", replaced_by="TR-003"), version(4, "blad"))
    (alert,) = alerts()
    assert "1 wersja z błędem" in alert


def test_error_alert_does_not_need_the_earlier_steps(client):
    save_versions(version(1, "blad"))
    assert any("1 wersja z błędem" in a for a in alerts())


def add_reel_without_hooks(client, code=OTHER, name="Nowa rolka"):
    """Rolka dodana komendą pula: ma kod i nazwę, ale nikt nie napisał jej hooków (a kroki 5-7 znów są niegotowe)."""
    reel = client.make_reel(code)
    reel["name"] = name
    candidates.save_pool([*candidates.load_pool(), reel])


def hooks_alerts():
    return [a for a in alerts() if "nie ma hooków" in a or "nie mają hooków" in a]


def test_alert_names_the_reel_that_has_no_hooks_once_trials_are_running(client):
    """Po dodaniu rolki w rozmowie, która się urwała, `paczka` ją pomija, a „Na jutro…” milczy (krok hooki znów niegotowy)."""
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TOMORROW_SLOT))
    assert hooks_alerts() == []
    add_reel_without_hooks(client)
    assert not step(wizard.status(NOW), "hooki")["gotowy"]
    (alert,) = alerts()
    assert alert == ("Rolka Nowa rolka (%s) nie ma hooków w dane/hooki.json, więc paczka ją pomija. Dopisz co najmniej "
                     "3 hooki i uruchom sprawdz-pule (dla nowej rolki to krok 7)." % OTHER)


def test_alert_lists_several_reels_without_hooks_in_the_plural(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TOMORROW_SLOT))
    add_reel_without_hooks(client, OTHER, "Pierwsza")
    add_reel_without_hooks(client, "Cghi789RST_", "Druga")
    (alert,) = hooks_alerts()
    assert alert.startswith("Rolki Pierwsza (%s), Druga (Cghi789RST_) nie mają hooków" % OTHER)
    assert "paczka je pomija" in alert and "sprawdz-pule" in alert


def test_no_hooks_alert_while_the_first_versions_are_not_in_zernio_yet(client):
    """W trakcie konfiguracji brak hooków to po prostu krok 7, a nie awaria."""
    client.until("ustawienia")
    add_reel_without_hooks(client)
    assert hooks_alerts() == []
    save_versions(version(1, "do_akceptacji", TOMORROW_SLOT))
    assert hooks_alerts() == []
    save_versions(version(1, "zaplanowana", TOMORROW_SLOT))
    assert len(hooks_alerts()) == 1


def test_no_hooks_alert_ignores_switched_off_reels_and_reels_that_have_hooks(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TOMORROW_SLOT))
    reel = client.make_reel(OTHER)
    reel["active"] = False
    candidates.save_pool([*candidates.load_pool(), reel])
    assert hooks_alerts() == []
    reel["active"] = True
    candidates.save_pool([*candidates.load_pool()[:1], reel])
    config.write_json(config.HOOKS, {CODE: client.make_hooks(), OTHER: client.make_hooks()})
    assert hooks_alerts() == []


def test_the_hooks_alert_comes_after_the_error_alert_and_before_the_new_version_alert(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TODAY_SLOT), version(2, "blad", TODAY_SLOT))
    add_reel_without_hooks(client)
    wizard.remember("nowa_wersja", "v99.0.0")
    first, second, third = alerts()
    assert "1 wersja z błędem" in first and "nie ma hooków" in second and third.startswith("Jest nowa wersja v99.0.0")


def test_alert_about_a_new_version_only_when_it_is_newer(client):
    wizard.remember("nowa_wersja", "v99.0.0")
    (alert,) = alerts()
    assert alert.startswith("Jest nowa wersja v99.0.0") and "aktualizuj" in alert and trial_reels.VERSION in alert
    for stale in ("v0.0.1", trial_reels.VERSION, "v" + trial_reels.VERSION):
        wizard.remember("nowa_wersja", stale)
        assert alerts() == [], stale
    wizard.remember("nowa_wersja", "coś dziwnego")                               # nieczytelnej wartości nie ukrywamy
    assert alerts() and alerts()[0].startswith("Jest nowa wersja coś dziwnego")


def test_forget_removes_only_that_entry(client):
    wizard.mark("powitanie")
    wizard.remember("nowa_wersja", "v99.0.0")
    wizard.forget("nowa_wersja")
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}
    before = config.WIZARD.read_bytes()
    wizard.forget("nowa_wersja")                                                # nie ma czego usuwać: bez zapisu
    assert config.WIZARD.read_bytes() == before
    config.WIZARD.unlink()
    wizard.forget("nowa_wersja")
    assert not config.WIZARD.exists()


def test_alerts_come_in_a_fixed_order(client):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TODAY_SLOT), version(2, "blad", TODAY_SLOT))
    wizard.remember("nowa_wersja", "v99.0.0")
    first, second, third = alerts()
    assert first.startswith("Na jutro") and "1 wersja z błędem" in second
    assert third.startswith("Jest nowa wersja v99.0.0 (masz %s)" % trial_reels.VERSION)


# --- komenda krok ---------------------------------------------------------------

def test_krok_prints_json_with_polish_letters_unescaped(client, run):
    rc, out, err = run("krok")
    assert rc == 0 and err == ""
    data = json.loads(out)
    assert data["nastepny"] == "powitanie" and len(data["kroki"]) == 12
    assert "Zwycięskie rolki" in out and "\\u" not in out


def test_krok_runs_the_doctor_once(client, run, monkeypatch):
    calls = []
    monkeypatch.setattr(doctor, "checks", lambda: calls.append(1) or [{"nazwa": "x", "ok": True, "info": ""}])
    assert run("krok")[0] == 0
    assert calls == [1]


def test_krok_never_prints_the_key(client, run):
    client.key()
    rc, out, err = run("krok")
    assert rc == 0 and KEY not in out + err


def test_krok_uses_the_clock_of_the_command(client, run):
    client.until("pomiar")
    save_versions(version(1, "zaplanowana", TODAY_SLOT))
    rc, out, err = run("krok")
    assert any(a.startswith("Na jutro") for a in json.loads(out)["alerty"])


def test_krok_gotowe_marks_the_step(client, run):
    rc, out, err = run("krok", "--gotowe", "powitanie")
    assert rc == 0 and err == "" and "Powitanie" in out
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}
    rc, out, _ = run("krok", "--gotowe", "pomiar", "--wartosc", "chrome")
    assert rc == 0 and config.read_json(config.WIZARD) == {"powitanie": "tak", "pomiar": "chrome"}


@pytest.mark.parametrize("step_id", ["powitanie", "pomiar", "tydzien", "codziennie"])
def test_krok_gotowe_for_a_marked_step_has_no_warning(client, run, step_id):
    rc, out, err = run("krok", "--gotowe", step_id)
    assert rc == 0 and err == ""


@pytest.mark.parametrize("step_id", ["programy", "zernio", "konto", "zwyciezcy", "pliki", "ustawienia", "hooki",
                                     "pierwsze"])
def test_krok_gotowe_for_a_step_the_wizard_checks_itself_saves_nothing_and_says_so(client, run, step_id):
    """Pierwsza linia nie może mówić „Zapisałem”, skoro kolejna twierdzi, że zapis niczego nie zmienia."""
    rc, out, err = run("krok", "--gotowe", step_id)
    assert rc == 0 and out == "" and "Traceback" not in err
    assert [line for line in err.splitlines() if line.strip()] == [err.strip()]                  # jedna linia
    assert err.startswith("Nic nie zapisałem: krok „%s”" % wizard.TITLES[step_id]) and "Zapisałem" not in err
    assert "sprawdzam sam" in err and "powitanie, pomiar, tydzien, codziennie" in err
    assert not config.WIZARD.exists()                                                           # nic nie trafiło do pliku
    assert not step(json.loads(run("krok")[1]), step_id)["gotowy"] or step_id == "programy"


def test_krok_gotowe_for_a_step_the_wizard_checks_itself_keeps_the_other_entries(client, run):
    wizard.mark("powitanie")
    before = config.WIZARD.read_bytes()
    assert run("krok", "--gotowe", " Pierwsze ")[0] == 0
    assert config.WIZARD.read_bytes() == before and config.read_json(config.WIZARD) == {"powitanie": "tak"}
    assert run("krok", "--gotowe", "pierwsze", "--wartosc", "tak")[0] == 0                       # z wartością też nic
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}


def test_krok_gotowe_accepts_the_step_id_in_any_case(client, run):
    assert run("krok", "--gotowe", " Powitanie ")[0] == 0
    assert config.read_json(config.WIZARD) == {"powitanie": "tak"}


def test_krok_gotowe_with_an_unknown_step_lists_the_known_ones(client, run):
    rc, out, err = run("krok", "--gotowe", "cokolwiek")
    assert rc == 1 and "powitanie" in err and "codziennie" in err and "Traceback" not in err
    assert not config.WIZARD.exists()


def test_krok_wartosc_without_gotowe_is_an_error(client, run):
    rc, out, err = run("krok", "--wartosc", "chrome")
    assert rc == 1 and "--gotowe" in err and out == ""


def test_krok_with_a_damaged_wizard_file_is_a_plain_message(client, run):
    config.WIZARD.parent.mkdir(parents=True, exist_ok=True)
    config.WIZARD.write_text("{nie json", encoding="utf-8")
    rc, out, err = run("krok")
    assert rc == 1 and "kreator.json" in err and "Traceback" not in err


def test_krok_is_listed_in_the_help(capsys):
    cli.main([])
    assert "krok" in capsys.readouterr().out


def test_krok_works_with_the_real_doctor_on_an_empty_folder(run, monkeypatch):
    monkeypatch.setattr(cli, "now", lambda: NOW.astimezone(planner.TZ))
    rc, out, err = run("krok")
    data = json.loads(out)
    assert rc == 0 and data["nastepny"] == "powitanie" and len(data["kroki"]) == 12


# --- lekkie importy -------------------------------------------------------------

def test_importing_the_wizard_loads_no_heavy_packages():
    code = ("import sys; sys.path.insert(0, %r); import trial_reels.wizard; "
            "bad = [m for m in ('PIL', 'av', 'numpy', 'faster_whisper', 'filelock', 'imageio_ffmpeg') "
            "if m in sys.modules]; print(bad)" % str(REPO))
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_zernio_step_rejects_key_that_api_calls_would_refuse():
    config.ENV.parent.mkdir(parents=True, exist_ok=True)
    config.ENV.write_text("ZERNIO_API_KEY=abc def\n", encoding="utf-8")
    ok, info = wizard._zernio({})
    assert ok is False and "klucz" in info and "abc" not in info
    config.ENV.write_text("ZERNIO_API_KEY=abc_def-123\n", encoding="utf-8")
    assert wizard._zernio({})[0] is True
