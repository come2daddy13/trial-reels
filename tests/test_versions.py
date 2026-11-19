"""Testy cyklu wersji: pierwsze wersje, akceptacja, planowanie w Zernio, paczka tygodniowa, sprawdzanie i wyniki.

Render i Zernio są atrapami liczącymi wywołania, a przeglądarka też. Żaden test nie łączy się z siecią, nie renderuje
prawdziwego filmu i nie zapisuje niczego poza własnym folderem klienta. Kody rolek i nicki są wymyślone.
"""
import json
import os
import re
import subprocess
import sys
import webbrowser
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trial_reels import __main__ as cli
from trial_reels import candidates, config, planner, render, state, versions, wizard, zernio

WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=WARSAW)        # sobota, południe
ACCOUNT = "acc-1"
LIVE = planner.LIVE


class World:
    """Atrapy renderu, Zernio i przeglądarki z licznikami wywołań oraz zegar ustawiony na NOW.

    Atrapy wyjątków wstawia się przez `before_render`, `before_upload` i `before_create`: dostają numer wywołania
    (od 1) i mogą rzucić dowolny wyjątek.
    """

    def __init__(self, monkeypatch, make_reel, make_hooks):
        self.monkeypatch, self.make_reel, self.make_hooks = monkeypatch, make_reel, make_hooks
        self.now = NOW
        self.renders, self.uploads, self.attempts, self.created, self.foreign = [], [], [], [], []
        self.ig_checks = []                               # terminy, o które program pytał Zernio (sprawdzenie zajętej minuty)
        self.remote, self.analytics_posts, self.analytics_calls, self.opened = {}, [], [], []
        self.before_render = self.before_upload = self.before_create = None
        monkeypatch.setattr(versions, "now", lambda: self.now)
        monkeypatch.setattr(render, "render", self._render)
        monkeypatch.setattr(zernio, "upload", self._upload)
        monkeypatch.setattr(zernio, "create_post", self._create_post)
        monkeypatch.setattr(zernio, "ig_post_at", self._ig_post_at)
        monkeypatch.setattr(zernio, "get_post", self._get_post)
        monkeypatch.setattr(zernio, "analytics", self._analytics)
        monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: self.opened.append(url) or True)

        def refuse(*args, **kwargs):
            raise AssertionError("sieć w testach tylko przez atrapę")

        monkeypatch.setattr(zernio, "_urlopen", refuse)
        monkeypatch.setattr(zernio.urllib.request, "urlopen", refuse)

    # --- dane --------------------------------------------------------------------

    def pool(self, n=12, hooks=10, **settings):
        """Zapisuje pulę n rolek z bankami hooków i ustawienia z kontem Instagrama."""
        reels, bank = [], {}
        for i in range(n):
            code = "Reel%03d" % (i + 1)
            reel = self.make_reel(code)
            reel["name"] = "Rolka %d" % (i + 1)
            reels.append(reel)
            bank[code] = self.make_hooks(hooks)
        candidates.save_pool(reels)
        config.write_json(config.HOOKS, bank)
        config.save_settings({"ig_account_id": ACCOUNT, "ig_handle": "przyklad.konto", **settings})

    @property
    def posts(self):
        return [payload for _, _, payload in self.created]

    # --- atrapy ------------------------------------------------------------------

    def _render(self, v, reel):
        self.renders.append(v["id"])
        if self.before_render:
            self.before_render(len(self.renders), v)
        config.OUT.mkdir(parents=True, exist_ok=True)
        out = config.OUT / ("%s.mp4" % v["id"])
        out.write_bytes(b"film")
        (config.OUT / ("%s_hook.png" % v["id"])).write_bytes(b"png")
        v.update(file=str(out), duration=12.3, changes="zmiany testowe", pauses_cut=0, segments=[[0.1, 12.4]])
        return out

    def _upload(self, path):
        self.uploads.append(Path(path).name)
        if self.before_upload:
            self.before_upload(len(self.uploads), path)
        return "https://cdn.example.com/temp/%s" % Path(path).name

    def _create_post(self, payload):
        self.attempts.append(payload)
        if self.before_create:
            self.before_create(len(self.attempts), payload)
        when = datetime.fromisoformat(payload["scheduledFor"]).replace(tzinfo=ZoneInfo(payload["timezone"]))
        post_id = "post-%d" % (len(self.created) + 1)
        self.created.append((post_id, when.astimezone(timezone.utc), payload))
        return {"_id": post_id, "mediaItems": [{"url": "https://cdn.example.com/media/%s.mp4" % post_id}]}

    def _ig_post_at(self, account_id, when_utc):
        assert account_id == ACCOUNT                      # konto idzie z ustawień klienta
        target = when_utc.astimezone(timezone.utc)
        self.ig_checks.append(target)
        for post_id, when in [(p, w) for p, w, _ in self.created] + self.foreign:
            if abs((when - target).total_seconds()) < 60:
                return {"_id": post_id}
        return None

    def _get_post(self, post_id):
        answer = self.remote[post_id]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def _analytics(self, account_id, from_date, to_date):
        self.analytics_calls.append((account_id, from_date, to_date))
        return list(self.analytics_posts)

    # --- wstrzykiwanie błędów ----------------------------------------------------

    def fail(self, where, at, error):
        """Rzuca `error` przy `at`-tym kolejnym wywołaniu (licząc od teraz): where = render, upload albo create."""
        done = {"render": self.renders, "upload": self.uploads, "create": self.attempts}[where]
        target = len(done) + at

        def hook(n, *args):
            if n == target:
                raise error

        setattr(self, "before_" + where, hook)

    def heal(self):
        self.before_render = self.before_upload = self.before_create = None


@pytest.fixture
def world(monkeypatch, make_reel, make_hooks):
    return World(monkeypatch, make_reel, make_hooks)


@pytest.fixture
def run(capsys):
    def go(*argv):
        rc = cli.main(list(argv))
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    return go


def load():
    return state.load()["versions"]


def first_batch(world, run, n=9):
    """Pierwsze wersje tak, jak robi je klient: pierwsze, akceptacja wszystkich i zaplanowanie w Zernio."""
    world.pool(12)
    assert run("pierwsze", "--ile", str(n))[0] == 0
    assert run("akceptuj", "--wszystkie")[0] == 0
    rc, out, err = run("zaplanuj")
    assert rc == 0, err
    assert {v["status"] for v in load().values()} == {"zaplanowana"}
    return len(load())


def put_state(*vs, **extra):
    """Wpisuje wersje wprost do stanu (bez renderu) i zwraca je jako słownik."""
    st = {"seq": len(vs), "versions": {v["id"]: v for v in vs}, "brake": {"on": False}}
    st.update(extra)
    state.save(st)
    return st["versions"]


def make_version(vid="TR-001", code="Reel001", days_ago=None, slot=None, **extra):
    if slot is None and days_ago is not None:
        slot = (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:00")
    v = {"id": vid, "code": code, "level": "subtelna", "hook_id": "h01", "hook": "Krótki hook", "emoji": "🔥",
         "slot": slot, "status": "zaplanowana", "caption": "Podpis wersji", "created": NOW.isoformat(timespec="seconds"),
         "params": {"thumb_ms": 900}}
    v.update(extra)
    return v


# --- godziny i zasady puli -----------------------------------------------------------

def test_hours_follow_the_pool_size_and_the_settings(world):
    world.pool(12)
    assert versions.hours() == ("09:00", "10:20", "11:40", "13:00", "14:20", "15:40", "17:00", "18:20", "19:40", "21:00")
    world.pool(3)
    assert versions.hours() == ("09:00", "15:00", "21:00")
    world.pool(12, daily_max=5, hours=["10:00", "20:00"])
    assert versions.hours() == ("10:00", "12:30", "15:00", "17:30", "20:00")
    world.pool(1)
    assert versions.hours() == ("13:00",)


def test_inactive_reels_do_not_count_for_the_daily_number(world):
    world.pool(12)
    pool = candidates.load_pool()
    for reel in pool[:9]:
        reel["active"] = False
    candidates.save_pool(pool)
    assert len(versions.hours()) == 3


@pytest.mark.parametrize("bad,key", [
    ({"hours": ["06:00", "21:00"]}, "hours"), ({"hours": ["09:00", "23:00"]}, "hours"),
    ({"brake_slot": "23:00"}, "brake_slot"), ({"brake_slot": "07:00"}, "brake_slot"),
    ({"daily_max": "dziesięć"}, "daily_max"), ({"daily_max": 0}, "daily_max"), ({"daily_max": True}, "daily_max"),
    ({"hours": ["9 rano", "21:00"]}, "hours"), ({"hours": ["21:00", "09:00"]}, "hours"), ({"hours": "cały dzień"}, "hours"),
    ({"day_window": ["07:15"]}, "day_window"), ({"day_window": "cały dzień"}, "day_window"),
    ({"brake_slot": "po obiedzie"}, "brake_slot"),
])
def test_broken_settings_are_a_plain_message(world, run, bad, key):
    world.pool(12, **bad)
    rc, out, err = run("pierwsze", "--ile", "1")
    assert rc == 1 and key in err and "dane/config.json" in err and "Traceback" not in err
    assert world.renders == []


# --- pierwsze wersje -----------------------------------------------------------------

def test_pierwsze_renders_nine_for_acceptance_without_upload(world, run):
    world.pool(12)
    rc, out, err = run("pierwsze")
    assert rc == 0, err
    vs = list(load().values())
    assert len(vs) == 9 and {v["status"] for v in vs} == {"do_akceptacji"}
    assert world.uploads == [] and world.attempts == [] and not any(v.get("media_url") for v in vs)
    assert max(Counter((v["slot"][:10], v["code"]) for v in vs).values()) == 1      # żadnej rolki dwa razy dziennie
    assert all(isinstance(v["render_s"], (int, float)) and v["render_s"] >= 0 for v in vs)
    assert all(Path(v["file"]).is_file() and v["caption"] and v["params"] for v in vs)
    assert len(world.opened) == 1 and world.opened[0].endswith("podglad.html")      # na końcu podgląd
    assert (config.DATA / "podglad.html").is_file()
    assert "Wersji do akceptacji: 9" in out


def test_pierwsze_names_the_levels_the_same_way_as_status_and_the_plan(world, run):
    """Poziomy w tekstach dla klienta idą przez config.LEVEL_LABEL („Średnia”), a nie jako klucz „srednia”."""
    world.pool(12)
    rc, out, err = run("pierwsze", "--ile", "6")
    assert rc == 0, err
    produced = [line for line in out.splitlines() if line.startswith("  TR-") and " | " in line]
    assert len(produced) == 6
    levels = [line.split(" | ")[2] for line in produced]
    assert set(levels) <= set(config.LEVEL_LABEL.values()) and "Średnia" in levels
    assert not {"subtelna", "srednia", "mocna"} & set(out.split())          # żadnego klucza technicznego
    status_out = run("status")[1]
    assert all(label in status_out for label in set(levels))                # te same słowa co w `status`


def test_paczka_names_the_levels_with_polish_letters_too(world, run):
    first_batch(world, run)
    rc, out, err = run("paczka", "--dni", "1")
    assert rc == 0, err
    produced = [line for line in out.splitlines() if line.startswith("  TR-") and " | " in line]
    assert produced and all(line.split(" | ")[2] in config.LEVEL_LABEL.values() for line in produced)


def test_pierwsze_takes_the_nearest_slots_within_seven_days_and_only_in_the_daytime(world, run):
    world.pool(12)
    run("pierwsze")
    slots = sorted(v["slot"] for v in load().values())
    assert slots[0] == "2026-11-21T13:00:00"          # najbliższy termin z zapasem 20 minut
    assert slots == sorted(set(slots))                  # każdy termin raz
    assert all(planner.parse_slot(s) < NOW + timedelta(days=7) for s in slots)
    assert all(planner.is_daytime(planner.parse_slot(s)) for s in slots)


def test_small_pool_three_a_day(world, run):
    world.pool(3)
    assert len(versions.hours()) == 3
    rc, out, err = run("pierwsze", "--ile", "9")
    assert rc == 0, err
    vs = list(load().values())
    per_day = Counter(v["slot"][:10] for v in vs)
    assert len(vs) == 9 and max(per_day.values()) <= 3
    assert max(Counter((v["slot"][:10], v["code"]) for v in vs).values()) == 1
    assert world.uploads == [] and world.attempts == []


def test_pierwsze_tops_up_to_the_requested_number_and_survives_a_rerun(world, run):
    world.pool(12)
    assert run("pierwsze", "--ile", "4")[0] == 0 and len(load()) == 4
    rc, out, err = run("pierwsze", "--ile", "9")
    assert rc == 0 and len(load()) == 9                  # dorobił 5, a nie 9
    renders = len(world.renders)
    rc, out, err = run("pierwsze", "--ile", "9")
    assert rc == 0 and len(load()) == 9 and len(world.renders) == renders
    assert "Masz już komplet" in out


def test_pierwsze_makes_replacements_for_rejected_versions(world, run):
    world.pool(12)
    run("pierwsze")
    assert run("odrzuc", "TR-001", "TR-002", "--powod", "za długi hook")[0] == 0
    rc, out, err = run("pierwsze")
    assert rc == 0 and len(load()) == 11
    live = [v for v in load().values() if v["status"] == "do_akceptacji"]
    assert len(live) == 9 and len({v["slot"] for v in live}) == 9                     # dwie nowe w wolnych terminach


def test_pierwsze_without_a_pool_says_what_to_do(world, run):
    rc, out, err = run("pierwsze")
    assert rc == 1 and "Pula jest pusta" in err and world.renders == []


def test_pierwsze_does_not_need_the_instagram_account(world, run):
    world.pool(12)
    config.save_settings({"ig_account_id": None})
    assert run("pierwsze", "--ile", "3")[0] == 0


def test_pierwsze_names_the_reel_that_has_no_hooks(world, run):
    world.pool(1)
    config.write_json(config.HOOKS, {})
    rc, out, err = run("pierwsze", "--ile", "1")
    assert rc == 1 and "Rolka 1" in err and "hooki.json" in err and "Traceback" not in err


def add_reel(world, code, name, bank=None, **changes):
    """Dopisuje rolkę do puli tak, jak robi to `pula KOD`: bez hooków, dopóki ktoś ich nie napisze."""
    reel = world.make_reel(code)
    reel["name"] = name
    reel.update(changes)
    candidates.save_pool(candidates.load_pool() + [reel])
    if bank is not None:
        config.write_json(config.HOOKS, {**candidates.load_hooks(), code: bank})
    return reel


def new_versions(after=9):
    return [v for v in load().values() if int(v["id"][3:]) > after]


def test_paczka_skips_a_reel_without_hooks_with_a_warning_and_plans_the_rest(world, run):
    """Rozmowa urwana po dodaniu rolki do puli nie może zatrzymać niedzielnej paczki dla pozostałych rolek."""
    first_batch(world, run)
    add_reel(world, "Reel013", "Rolka nowa")
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    warning = next(line for line in out.splitlines() if line.startswith("Uwaga: pomijam rolkę"))
    assert warning.startswith("Uwaga: pomijam rolkę Rolka nowa (Reel013): nie ma hooków w dane/hooki.json")
    assert "co najmniej 3" in warning and "sprawdz-pule" in warning and "Reszta puli idzie dalej" in warning
    new = new_versions()
    assert len(new) == 11 and {v["status"] for v in new} == {"zaplanowana"} and "Reel013" not in {v["code"] for v in new}
    assert "Gotowe. Zaplanowane w Zernio: 11." in out


def test_paczka_dry_run_warns_about_the_reel_it_would_skip(world, run):
    first_batch(world, run)
    add_reel(world, "Reel013", "Rolka nowa")
    before = snapshot(world)
    rc, out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0 and snapshot(world) == before
    assert "Uwaga: pomijam rolkę Rolka nowa (Reel013): nie ma hooków" in out and "Wersji w planie: 11." in out


def test_pierwsze_skips_a_reel_without_hooks_too(world, run):
    world.pool(12)
    add_reel(world, "Reel013", "Rolka nowa")
    rc, out, err = run("pierwsze", "--ile", "4")
    assert rc == 0, err
    assert "Uwaga: pomijam rolkę Rolka nowa (Reel013)" in out
    assert len(load()) == 4 and "Reel013" not in {v["code"] for v in load().values()}


def test_a_reel_without_hooks_that_is_switched_off_is_not_mentioned(world, run):
    first_batch(world, run)
    add_reel(world, "Reel013", "Rolka nowa", active=False)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0 and "pomijam rolkę" not in out


def test_paczka_refuses_only_when_no_reel_can_be_planned(world, run):
    first_batch(world, run)
    config.write_json(config.HOOKS, {})
    before, renders = state.load(), len(world.renders)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 1 and "Traceback" not in err and state.load() == before and len(world.renders) == renders
    assert "Nie ma rolki, z której da się zrobić wersje." in err
    assert "Rolka 1, Rolka 2, " in err and "Rolka 12: nie ma hooków w dane/hooki.json" in err      # jedna linia, powody razem
    assert err.rstrip().endswith("uruchom komendę sprawdz-pule.") and "pomijam rolkę" not in out


@pytest.mark.parametrize("change,expected", [
    (lambda reel, bank: bank[1].update(text="x" * 51), "hook h02: tekst ma 51 znaków, a limit to 50"),
    (lambda reel, bank: bank[0].update(emoji="🦄"), "emotki „🦄” nie ma w zestawie"),
    (lambda reel, bank: bank.append({"text": "Bez numeru", "emoji": "🔥"}), "nie ma id"),
    (lambda reel, bank: reel.update(extras=["Z" * 2300] * 4), "podpis wersji 1 ma"),
    (lambda reel, bank: reel.update(blur=[{"t": [0, "1)':movie=x"], "box": [0, 0, 1, 0.3]}]), "wpis nr 1 w polu blur"),
])
def test_paczka_skips_a_reel_whose_hooks_or_captions_break_a_limit_and_names_the_problem(world, run, change, expected):
    """`sprawdz-pule` pilnuje limitów, ale hooki dopisuje się później, więc plan sam sprawdza to, co psuje wersje."""
    first_batch(world, run)
    pool, bank = candidates.load_pool(), candidates.load_hooks()
    change(pool[2], bank["Reel003"])
    candidates.save_pool(pool)
    config.write_json(config.HOOKS, bank)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    warning = next(line for line in out.splitlines() if line.startswith("Uwaga: pomijam rolkę Rolka 3 (Reel003): "))
    assert expected in warning and "sprawdz-pule" in warning
    new = new_versions()
    assert len(new) == 11 and "Reel003" not in {v["code"] for v in new}


def test_a_bank_of_one_valid_hook_is_enough_to_plan(world, run):
    """Do planu wystarczy jeden hook (pełne sprawdzenie, co najmniej 3, robi `sprawdz-pule`)."""
    first_batch(world, run)
    bank = candidates.load_hooks()
    bank["Reel003"] = bank["Reel003"][:1]
    config.write_json(config.HOOKS, bank)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0 and "pomijam rolkę" not in out and "Reel003" in {v["code"] for v in new_versions()}


def test_the_hook_bank_message_does_not_name_a_reel_that_has_no_hooks_at_all(world):
    """Rolka bez żadnego hooka jest pomijana (to inna sprawa niż „bank prawie pusty”, po którym idą powtórki)."""
    world.pool(3)
    add_reel(world, "Reel013", "Rolka nowa")
    assert versions.hook_bank_low(state.load()) == []
    assert versions.reels_without_hooks() == ["Rolka nowa (Reel013)"]
    bank = candidates.load_hooks()
    bank["Reel002"] = bank["Reel002"][:2]
    config.write_json(config.HOOKS, bank)
    assert versions.hook_bank_low(state.load()) == ["Rolka 2"]


def test_reels_without_hooks_are_the_active_ones_with_an_empty_or_missing_bank(world):
    world.pool(2)
    add_reel(world, "Reel013", "Brak banku")
    add_reel(world, "Reel014", "Pusty bank", bank=[])
    add_reel(world, "Reel015", "Wyłączona", active=False)
    add_reel(world, "Reel016", "Zepsuty bank", bank="nie lista")
    assert versions.reels_without_hooks() == ["Brak banku (Reel013)", "Pusty bank (Reel014)", "Zepsuty bank (Reel016)"]


def test_pierwsze_replaces_a_failed_version_in_the_same_term(world, run):
    world.pool(12)
    world.fail("render", 2, RuntimeError("ffmpeg padł"))
    run("pierwsze", "--ile", "4")
    bad = next(v for v in load().values() if v["status"] == "blad")
    world.heal()
    rc, out, err = run("pierwsze", "--ile", "4")
    assert rc == 0 and len(world.opened) == 2
    new = next(v for v in load().values() if v["id"] != bad["id"] and v["slot"] == bad["slot"])
    assert new["status"] == "do_akceptacji" and load()[bad["id"]]["replaced_by"] == new["id"]
    assert versions.open_errors(state.load()) == []


def test_pierwsze_names_a_missing_source_file_relative_to_the_client_folder(world, run):
    world.pool(12)

    def missing(n, v):
        raise FileNotFoundError(2, "No such file or directory", str(config.SRC / "Reel001.mp4"))

    world.before_render = missing
    rc, out, err = run("pierwsze", "--ile", "1")
    assert rc == 1 and "dane/src/Reel001.mp4" in out and str(config.ROOT) not in out + err


def test_pierwsze_marks_a_failed_render_and_goes_on(world, run):
    world.pool(12)
    world.fail("render", 2, RuntimeError("ffmpeg padł"))
    rc, out, err = run("pierwsze", "--ile", "4")
    assert rc == 1 and "ffmpeg padł" in out + err
    statuses = Counter(v["status"] for v in load().values())
    assert statuses == {"do_akceptacji": 3, "blad": 1}
    bad = next(v for v in load().values() if v["status"] == "blad")
    assert "ffmpeg padł" in bad["note"]
    assert len(world.opened) == 1                                       # podgląd mimo jednej porażki


def test_pierwsze_shows_the_render_time_advice_when_rendering_is_slow(world, run):
    world.pool(12)
    ticks = iter(range(0, 100_000, 200))                                 # każdy odczyt zegara: +200 s, render trwa 200 s
    world.monkeypatch.setattr(versions, "clock", lambda: next(ticks))
    rc, out, err = run("pierwsze", "--ile", "2")
    assert rc == 0 and "daily_max" in out and "200 s" in out
    assert [v["render_s"] for v in load().values()] == [200.0, 200.0]


def test_pierwsze_stays_quiet_about_render_time_when_rendering_is_fast(world, run):
    world.pool(12)
    rc, out, err = run("pierwsze", "--ile", "2")
    assert rc == 0 and "daily_max" not in out


# --- podgląd, akceptacja i odrzucenie ------------------------------------------------

def test_podglad_shows_only_versions_waiting_for_acceptance(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "TR-001")
    world.opened.clear()
    rc, out, err = run("podglad")
    assert rc == 0 and len(world.opened) == 1
    text = (config.DATA / "podglad.html").read_text(encoding="utf-8")
    assert 'src="wersje/TR-002.mp4"' in text and 'src="wersje/TR-003.mp4"' in text
    assert 'src="wersje/TR-001.mp4"' not in text
    assert "Wersji na stronie: 2" in out


def test_podglad_wszystkie_shows_the_last_fourteen_days(world, run):
    world.pool(12)
    put_state(make_version("TR-001", days_ago=20, status="opublikowana", created=(NOW - timedelta(days=21)).isoformat()),
              make_version("TR-002", days_ago=5, status="opublikowana"),
              make_version("TR-003", slot="2026-11-22T09:00:00", status="zaplanowana"),
              make_version("TR-004", days_ago=2, status="odrzucona"))
    rc, out, err = run("podglad", "--wszystkie")
    assert rc == 0
    text = (config.DATA / "podglad.html").read_text(encoding="utf-8")
    assert 'src="wersje/TR-001.mp4"' not in text
    for vid in ("TR-002", "TR-003", "TR-004"):
        assert 'src="wersje/%s.mp4"' % vid in text


def test_podglad_with_nothing_to_show_says_what_to_do(world, run):
    world.pool(12)
    rc, out, err = run("podglad")
    assert rc == 0 and "Nie ma wersji do akceptacji" in out and "--wszystkie" in out and world.opened == []


def test_podglad_tells_where_the_page_is_when_no_browser_opens(world, run, monkeypatch):
    world.pool(12)
    run("pierwsze", "--ile", "2")
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: False)
    rc, out, err = run("podglad")
    assert rc == 0 and "podglad.html" in out and "ręcznie" in out


def test_akceptuj_and_odrzuc_change_only_what_they_are_told(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "5")
    rc, out, err = run("akceptuj", "TR-001", "tr-2")                    # numery bywają pisane różnie
    assert rc == 0 and "TR-001" in out and "TR-002" in out
    rc, out, err = run("odrzuc", "TR-003", "--powod", "hook zasłania twarz")
    assert rc == 0
    vs = load()
    assert [vs["TR-00%d" % n]["status"] for n in range(1, 6)] == \
        ["zaakceptowana", "zaakceptowana", "odrzucona", "do_akceptacji", "do_akceptacji"]
    assert vs["TR-003"]["note"] == "hook zasłania twarz"
    rc, out, err = run("akceptuj", "--wszystkie")
    assert rc == 0 and {v["status"] for k, v in load().items() if k != "TR-003"} == {"zaakceptowana"}
    assert load()["TR-003"]["status"] == "odrzucona"


def test_akceptuj_names_zaplanuj_as_the_next_step_but_not_as_an_order(world, run):
    """Zdanie z komendy czyta Claude klienta. Nie może brzmieć jak polecenie do natychmiastowego planowania,
    bo `zaplanuj` wolno uruchomić dopiero po osobnej zgodzie klienta na pokazane terminy."""
    world.pool(12)
    run("pierwsze", "--ile", "2")
    rc, out, err = run("akceptuj", "--wszystkie")
    line = next(l for l in out.splitlines() if l.startswith("Zaakceptowane:"))
    assert rc == 0 and err == "" and line.startswith("Zaakceptowane: TR-001, TR-002. ")
    assert "Następny krok to zaplanuj" in line and "zgodzie klienta" in line and "zaplanuj --na-sucho" in line
    assert "Teraz uruchom" not in out and "uruchom zaplanuj" not in out
    assert world.attempts == [] and world.uploads == []                       # sama akceptacja niczego nie wysyła
    assert {v["status"] for v in load().values()} == {"zaakceptowana"}


def test_akceptuj_without_ids_asks_for_them(world, run):
    world.pool(12)
    rc, out, err = run("akceptuj")
    assert rc == 1 and "--wszystkie" in err


def test_unknown_id_changes_nothing_and_says_so(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "2")
    before = state.load()
    rc, out, err = run("akceptuj", "TR-001", "TR-099")
    assert rc == 1 and "TR-099" in err and "Nie ma wersji" in err
    assert state.load() == before                                        # nic nie zostało zmienione
    rc, out, err = run("odrzuc", "TR-099")
    assert rc == 1 and "TR-099" in err


def test_a_rejected_or_scheduled_version_cannot_be_accepted_again(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "2")
    run("odrzuc", "TR-001")
    rc, out, err = run("akceptuj", "TR-001")
    assert rc == 1 and "Odrzucona" in out + err and load()["TR-001"]["status"] == "odrzucona"
    run("akceptuj", "TR-002")
    run("zaplanuj")
    rc, out, err = run("odrzuc", "TR-002")
    assert rc == 1 and load()["TR-002"]["status"] == "zaplanowana" and "Zernio" in out + err


# --- planowanie w Zernio ------------------------------------------------------------

def test_zaplanuj_posts_trial_manual_with_account_and_zone_from_settings(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "2")
    run("akceptuj", "--wszystkie")
    rc, out, err = run("zaplanuj")
    assert rc == 0, err
    assert len(world.posts) == 2 and len(world.uploads) == 2
    first = world.posts[0]
    assert first["platforms"][0]["accountId"] == ACCOUNT and first["timezone"] == "Europe/Warsaw"
    assert first["platforms"][0]["platformSpecificData"]["trialParams"] == {"graduationStrategy": "MANUAL"}
    assert first["scheduledFor"] == "2026-11-21T13:00:00" and first["content"] == load()["TR-001"]["caption"]
    assert first["mediaItems"] == [{"type": "video", "url": "https://cdn.example.com/temp/TR-001.mp4"}]
    v = load()["TR-001"]
    assert v["status"] == "zaplanowana" and v["zernio_post_id"] == "post-1" and v["slot"] == "2026-11-21T13:00:00"
    assert v["media_url"] == "https://cdn.example.com/media/post-1.mp4"           # stały adres po utworzeniu posta
    assert first["platforms"][0]["platformSpecificData"]["thumbOffset"] == v["params"]["thumb_ms"]


def test_zaplanuj_uses_the_time_zone_from_the_settings(world, run):
    tokyo = ZoneInfo("Asia/Tokyo")
    world.pool(12, timezone="Asia/Tokyo")
    world.now = datetime(2026, 11, 21, 6, 0, tzinfo=tokyo)
    run("pierwsze", "--ile", "1")
    run("akceptuj", "--wszystkie")
    assert run("zaplanuj")[0] == 0
    assert world.posts[0]["timezone"] == "Asia/Tokyo" and world.posts[0]["scheduledFor"] == "2026-11-21T09:00:00"


def test_zaplanuj_dry_run_does_not_post(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "--wszystkie")
    before = state.load()
    rc, out, err = run("zaplanuj", "--na-sucho")
    assert rc == 0, err
    assert world.uploads == [] and world.attempts == [] and world.created == []
    assert state.load() == before                                                    # stan bez zmian
    assert "zaplanowałbym" in out and "2026-11-21 13:00" in out and "Podpis" in out
    assert out.count("TR-00") >= 3


def test_zaplanuj_dry_run_shows_the_same_slots_as_the_real_run_for_overdue_versions(world, run):
    """Wersje zaakceptowane dawno temu mają minione terminy i dostają kolejne wolne. Plan na sucho ma pokazać klientowi
    te same cztery różne terminy, które zajmie prawdziwe planowanie, a nie czterokrotnie ten sam."""
    world.pool(12)
    run("pierwsze", "--ile", "4")
    run("akceptuj", "--wszystkie")
    world.now = NOW + timedelta(days=3)                                  # terminy wersji minęły
    before = state.load()
    rc, dry_out, err = run("zaplanuj", "--na-sucho")
    assert rc == 0 and state.load() == before                            # plan niczego nie zmienia ani nie zapisuje
    dry = re.findall(r"(TR-\d+): zaplanowałbym na (\d{4}-\d\d-\d\d \d\d:\d\d)", dry_out)
    assert [vid for vid, _ in dry] == ["TR-001", "TR-002", "TR-003", "TR-004"]
    assert len({slot for _, slot in dry}) == 4 and "Na sucho: zaplanowałbym 4 z 4." in dry_out
    rc, out, err = run("zaplanuj")
    assert rc == 0, err
    real = [(v["id"], versions.slot_label(v["slot"])) for v in sorted(load().values(), key=versions.id_number)]
    assert dry == real                                                   # to samo, co zrobi prawdziwe planowanie
    assert max(Counter(p["scheduledFor"] for p in world.posts).values()) == 1


def test_zaplanuj_dry_run_does_not_put_two_versions_of_one_reel_on_one_day(world, run):
    """Plan na sucho pilnuje „rolka najwyżej raz dziennie” tak samo jak prawdziwy przebieg, także dla przeniesionych wersji."""
    world.pool(12)
    put_state(*(make_version("TR-%03d" % i, "Reel001", slot="2026-11-19T10:00:00", status="zaakceptowana")
                for i in (1, 2, 3)))
    rc, out, err = run("zaplanuj", "--na-sucho")
    slots = re.findall(r"zaplanowałbym na (\d{4}-\d\d-\d\d) \d\d:\d\d", out)
    assert rc == 0 and len(slots) == 3 and len(set(slots)) == 3          # trzy dni, bo to wciąż ta sama rolka


def test_paczka_dry_run_keeps_the_slots_of_versions_it_would_finish_out_of_the_new_plan(world, run):
    """„Dokończyłbym” zajmuje terminy w pamięci, więc plan nowych wersji ich nie powtarza: dokładnie jak prawdziwa paczka."""
    first_batch(world, run)
    with state.locked() as st:
        for i in range(3):
            v = versions.new_version(st, "Reel%03d" % (i + 1), "subtelna", {"id": "h9%d" % i, "text": "H", "emoji": "🔥"},
                                     "2026-11-20T09:00:00", "zaakceptowana")                 # termin sprzed „teraz”
            versions.produce(st, v, False)
    before = snapshot(world)
    rc, dry_out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0 and snapshot(world) == before
    finish = dict(re.findall(r"(TR-\d+): zaplanowałbym na (\d{4}-\d\d-\d\d \d\d:\d\d)", dry_out))
    plan = re.findall(r"^(\d{4}-\d\d-\d\d \d\d:\d\d)  ", dry_out, flags=re.M)
    assert len(finish) == 3 and len(set(finish.values())) == 3
    assert plan and not set(plan) & set(finish.values()) and len(set(plan)) == len(plan)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    done = load()
    assert {vid: versions.slot_label(done[vid]["slot"]) for vid in finish} == finish
    new = sorted(versions.slot_label(v["slot"]) for v in done.values() if v["id"] not in finish and int(v["id"][3:]) > 12)
    assert new == sorted(plan)


def test_zaplanuj_schedules_only_accepted_versions_and_says_what_waits(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    rc, out, err = run("zaplanuj")
    assert rc == 0 and world.posts == [] and "akceptuj" in out                       # nic nie zaakceptowano
    run("akceptuj", "TR-002")
    rc, out, err = run("zaplanuj")
    assert rc == 0 and len(world.posts) == 1
    assert {k: v["status"] for k, v in load().items()} == {"TR-001": "do_akceptacji", "TR-002": "zaplanowana",
                                                           "TR-003": "do_akceptacji"}


def test_zaplanuj_sends_back_to_the_clients_acceptance_not_to_a_command_to_run_blindly(world, run):
    """Teksty kończące się „uruchom akceptuj” mogłyby skłonić Claude'a do zaakceptowania za klienta, więc mówią, że
    akceptuje klient (po wyraźnym „akceptuję”)."""
    world.pool(12)
    run("pierwsze", "--ile", "2")
    rc, out, err = run("zaplanuj")                                       # bez numerów: nic nie jest zaakceptowane
    assert rc == 0 and "Nie ma zaakceptowanych wersji do zaplanowania." in out
    assert "akceptuję" in out and "klienta" in out and "akceptuj --wszystkie" in out and "Obejrzyj podgląd i zaakceptuj" not in out
    rc, out, err = run("zaplanuj", "TR-001")                            # z numerem
    line = next(l for l in (out + err).splitlines() if "czeka na akceptację" in l)
    assert rc == 1 and "akceptuję" in line and "klienta" in line and "akceptuj TR-001" in line
    assert "Najpierw uruchom akceptuj" not in line and world.attempts == []


def test_zaplanuj_with_an_id_refuses_a_version_that_nobody_accepted(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "2")
    rc, out, err = run("zaplanuj", "TR-001")
    assert rc == 1 and "czeka na akceptację" in out + err and world.attempts == []
    assert load()["TR-001"]["status"] == "do_akceptacji"
    rc, out, err = run("zaplanuj", "TR-001", "--na-sucho")                              # na sucho też mówi, co jest nie tak
    assert rc == 1 and "czeka na akceptację" in out + err and world.attempts == []


def test_zaplanuj_renders_again_when_the_file_is_gone(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "2")
    run("akceptuj", "--wszystkie")
    for path in config.OUT.glob("TR-00*"):
        path.unlink()                                                                  # klient posprzątał folder wersji
    renders = len(world.renders)
    rc, out, err = run("zaplanuj")
    assert rc == 0, err
    assert len(world.renders) - renders == 2 and len(world.posts) == 2
    assert {v["status"] for v in load().values()} == {"zaplanowana"}


def test_zaplanuj_marks_a_version_that_zernio_refuses_and_schedules_the_rest(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "--wszystkie")
    world.fail("create", 2, zernio.ZernioError("POST /posts -> 400: zły plik", 400))
    rc, out, err = run("zaplanuj")
    assert rc == 1 and len(world.posts) == 2
    assert [v["status"] for v in load().values()] == ["zaplanowana", "blad", "zaplanowana"]
    assert "400" in load()["TR-002"]["note"] and "Zaplanowane w Zernio: 2 z 3" in out


def test_zaplanuj_twice_never_posts_the_same_version_twice(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "--wszystkie")
    run("zaplanuj")
    run("zaplanuj")
    run("zaplanuj", "TR-001")
    assert len(world.posts) == 3 and len(world.uploads) == 3


def test_zaplanuj_without_the_account_says_which_step_comes_first(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "1")
    run("akceptuj", "--wszystkie")
    config.save_settings({"ig_account_id": None})
    rc, out, err = run("zaplanuj")
    assert rc == 1 and "Najpierw krok 3: konto Instagram" in err and "Traceback" not in err
    assert world.posts == []


def test_schedule_refuses_night(world):
    world.pool(12)
    with state.locked() as st:
        hook = {"id": "h01", "text": "Hook", "emoji": "🔥"}
        v = versions.new_version(st, "Reel001", "subtelna", hook, "2026-11-22T03:19:00", "zaakceptowana")
        versions.produce(st, v, False)
        assert versions.schedule_one(st, v, False) is False
        assert world.attempts == [] and world.uploads == []
        assert v["status"] == "zaakceptowana" and not v.get("zernio_post_id")


def test_schedule_one_works_without_the_account_when_the_hour_is_wrong(world):
    world.pool(12)
    config.save_settings({"ig_account_id": None})
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T23:30:00", "zaakceptowana")
        versions.produce(st, v, False)
        assert versions.schedule_one(st, v, False) is False


def test_the_day_window_comes_from_the_settings(world):
    world.pool(12, day_window=["09:00", "20:00"], hours=["09:00", "19:00"])
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T21:00:00", "zaakceptowana")
        versions.produce(st, v, False)
        assert versions.schedule_one(st, v, False) is False                   # 21:00 poza oknem klienta
        v["slot"] = "2026-11-22T19:00:00"
        assert versions.schedule_one(st, v, False) is True


def test_schedule_one_moves_a_slot_that_is_too_close_to_the_next_free_one(world):
    world.pool(12)
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-21T12:05:00", "zaakceptowana")            # za 5 minut: za blisko
        versions.produce(st, v, False)
        assert versions.schedule_one(st, v, False) is True
        assert v["slot"] == "2026-11-21T13:00:00" and v["status"] == "zaplanowana"


def test_schedule_one_skips_a_slot_where_zernio_already_has_a_post(world):
    world.pool(12)
    world.foreign.append(("cudzy-post", datetime(2026, 11, 22, 8, 0, tzinfo=timezone.utc)))     # 09:00 czasu polskiego
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T09:00:00", "zaakceptowana")
        versions.produce(st, v, False)
        assert versions.schedule_one(st, v, False) is False
        assert world.attempts == [] and not v.get("zernio_post_id")


HINT_PARTS = ("przesuń godziny triali w ustawieniach", "dane/config.json", "hours", "09:05–21:05", "odrzuć pominięte wersje",
              "pierwsze albo paczka")


def block_with_foreign_posts(world, *ids):
    """Wpisuje cudze posty IG dokładnie na terminy wersji `ids` (jak własne triale klienta o tych samych godzinach)."""
    for vid in ids:
        slot = planner.parse_slot(load()[vid]["slot"])
        world.foreign.append(("cudzy-post-" + vid, slot.astimezone(timezone.utc)))


def test_a_skipped_version_says_plainly_what_to_do_about_the_other_post(world, capsys):
    world.pool(12)
    world.foreign.append(("cudzy-post", datetime(2026, 11, 22, 8, 0, tzinfo=timezone.utc)))     # 09:00 czasu polskiego
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T09:00:00", "zaakceptowana")
        versions.produce(st, v, False)
        capsys.readouterr()
        assert versions.schedule_one(st, v, False) is False
    out = capsys.readouterr().out
    assert out.count("\n") == 1                                         # jedna linia
    assert out.startswith("  ! TR-001: na 2026-11-22 09:00 masz już inny post na Instagramie. Pomijam tę wersję. ")
    for part in HINT_PARTS + ("odrzuc TR-001",):
        assert part in out, part
    assert "cudzy-post" not in out                                         # numer posta niczego klientowi nie mówi


def test_a_skipped_version_in_a_series_has_no_hint_of_its_own(world, capsys):
    """Wywołujący, który zbiera pominięte wersje, sam powtarza wskazówkę raz na końcu serii."""
    world.pool(12)
    world.foreign.append(("cudzy-post", datetime(2026, 11, 22, 8, 0, tzinfo=timezone.utc)))     # 09:00 czasu polskiego
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T09:00:00", "zaakceptowana")
        versions.produce(st, v, False)
        capsys.readouterr()
        clashes = []
        assert versions.schedule_one(st, v, False, clashes) is False
    out = capsys.readouterr().out
    assert clashes == ["TR-001"] and out.count("\n") == 1
    assert out.strip() == "! TR-001: na 2026-11-22 09:00 masz już inny post na Instagramie. Pomijam tę wersję."


def test_zaplanuj_dry_run_with_every_slot_taken_ends_with_the_same_hint(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "--wszystkie")
    block_with_foreign_posts(world, "TR-001", "TR-002", "TR-003")
    rc, out, err = run("zaplanuj", "--na-sucho")
    lines = out.splitlines()
    assert rc == 0 and err == "" and world.attempts == [] and world.uploads == []
    assert "Na sucho: zaplanowałbym 0 z 3. Nic nie wysłałem i nic nie zmieniłem." in lines
    skipped = [line for line in lines if "masz już inny post na Instagramie" in line]
    assert [line.split(":")[0].strip(" !") for line in skipped] == ["TR-001", "TR-002", "TR-003"]
    assert all("Pomijam tę wersję." in line for line in skipped)
    assert all("przesuń godziny" not in line for line in skipped)         # linie pominięć są krótkie
    assert out.count("przesuń godziny triali") == 1                        # wskazówka jest raz, na końcu
    last = lines[-1]
    assert last.startswith("Jeśli o tych godzinach publikujesz coś innego") and "odrzuc TR-001 TR-002 TR-003" in last
    assert all(part in last for part in HINT_PARTS)
    assert load()["TR-001"]["status"] == "zaakceptowana"                   # nic się nie zmieniło


def test_zaplanuj_with_a_taken_slot_schedules_the_rest_and_hints_only_about_the_taken_one(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "--wszystkie")
    block_with_foreign_posts(world, "TR-002")
    rc, out, err = run("zaplanuj")
    lines = out.splitlines()
    assert rc == 1 and len(world.posts) == 2                                # dwie wersje poszły, jedna czeka
    assert "Zaplanowane w Zernio: 2 z 3." in lines
    assert [v["status"] for v in load().values()] == ["zaplanowana", "zaakceptowana", "zaplanowana"]
    assert lines[-1].startswith("Jeśli o tych godzinach") and "odrzuc TR-002)" in lines[-1] and "TR-001" not in lines[-1]
    assert out.count("przesuń godziny triali") == 1                        # raz, na końcu, a nie też przy pominiętej wersji


def test_zaplanuj_without_any_clash_has_no_hint(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "2")
    run("akceptuj", "--wszystkie")
    for argv in (("zaplanuj", "--na-sucho"), ("zaplanuj",)):
        rc, out, err = run(*argv)
        assert rc == 0 and "przesuń godziny" not in out and "masz już inny post" not in out


def test_other_reasons_for_skipping_do_not_get_the_hours_hint(world, run, capsys):
    world.pool(12, day_window=["09:00", "20:00"], hours=["09:00", "19:00"])
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T21:00:00", "zaakceptowana")                    # poza oknem publikacji
        versions.produce(st, v, False)
        capsys.readouterr()
        clashes = []
        assert versions.schedule_one(st, v, False, clashes) is False and clashes == []
    out = capsys.readouterr().out
    assert "poza oknem publikacji" in out and "przesuń godziny" not in out
    rc, out, err = run("zaplanuj", "--na-sucho")
    assert rc == 0 and "przesuń godziny" not in out


def test_paczka_skipped_because_of_other_posts_gives_the_hint_instead_of_promising_a_retry(world, run):
    first_batch(world, run)
    taken = versions.free_slots(state.load(), 1)
    assert len(taken) == 1
    world.foreign.extend(("cudzy-post-%d" % i, t.astimezone(timezone.utc)) for i, t in enumerate(taken))
    posts = len(world.posts)
    rc, out, err = run("paczka", "--dni", "1")
    assert rc == 0, err
    assert len(world.posts) == posts and "Pominięte: 1." in out
    assert "masz już inny post na Instagramie" in out
    assert "następne uruchomienie spróbuje je dokończyć" not in out         # po ponowieniu byłoby to samo
    skipped = next(v["id"] for v in load().values() if v["status"] == "zaakceptowana")
    last_hint = [line for line in out.splitlines() if line.startswith("Jeśli o tych godzinach")][-1]
    assert "odrzuc %s)" % skipped in last_hint and all(part in last_hint for part in HINT_PARTS)
    assert out.count("przesuń godziny triali") == 1


def test_paczka_still_promises_a_retry_for_a_version_skipped_for_another_reason(world, run):
    """Wersja pominięta z innego powodu (tu: termin za blisko) zostaje i następne uruchomienie ją dokończy."""
    first_batch(world, run)
    with state.locked() as st:
        late = versions.new_version(st, "Reel002", "subtelna", {"id": "h99", "text": "H", "emoji": "🔥"},
                                    "2026-11-23T03:00:00", "zaakceptowana")                  # w nocy
        versions.produce(st, late, False)
    rc, out, err = run("paczka", "--dni", "1")
    assert rc == 0, err
    assert "Dokańczam zaakceptowane wersje" in out and "poza oknem publikacji" in out
    assert "przesuń godziny" not in out


def test_schedule_one_reuploads_a_file_older_than_six_days_only(world):
    world.pool(12)
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T09:00:00", "zaakceptowana")
        versions.produce(st, v, True)
        assert world.uploads == ["TR-001.mp4"]
        assert versions.schedule_one(st, v, False) is True and world.uploads == ["TR-001.mp4"]    # świeży plik
        w = versions.new_version(st, "Reel002", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T10:20:00", "zaakceptowana")
        versions.produce(st, w, True)
        w["uploaded_at"] = (NOW - timedelta(days=7)).isoformat(timespec="seconds")
        assert versions.schedule_one(st, w, False) is True
        assert world.uploads == ["TR-001.mp4", "TR-002.mp4", "TR-002.mp4"]


def test_schedule_one_ignores_a_version_that_already_has_a_post(world):
    world.pool(12)
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T09:00:00", "zaakceptowana")
        v["zernio_post_id"] = "post-x"
        assert versions.schedule_one(st, v, False) is False and world.attempts == []


def test_schedule_one_has_only_the_publication_paths_the_program_uses():
    """Nie ma ścieżki „za 3 minuty” (dawny `at_now`): wersja zawsze dostaje termin z planu albo najbliższy wolny."""
    import inspect

    assert list(inspect.signature(versions.schedule_one).parameters) == ["st", "v", "dry_run", "clashes"]


def test_schedule_one_in_dry_run_changes_nothing(world, capsys):
    world.pool(12)
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-22T09:00:00", "zaakceptowana")
        versions.produce(st, v, False)
        snapshot = json.dumps(st, sort_keys=True)
        assert versions.schedule_one(st, v, True) is True
        assert json.dumps(st, sort_keys=True) == snapshot
    out = capsys.readouterr().out
    assert "2026-11-22 09:00" in out and v["caption"][:20] in out
    assert world.uploads == [] and world.attempts == []


# --- paczka tygodniowa ----------------------------------------------------------------

def test_paczka_refuses_before_first_acceptance(world, run):
    world.pool(12)
    rc, out, err = run("paczka")
    assert rc == 1 and "Najpierw krok 8: pierwsze wersje do akceptacji" in err
    assert world.renders == [] and world.analytics_calls == [] and load() == {}
    run("pierwsze", "--ile", "3")                                          # są wersje, ale nikt ich nie zaakceptował
    run("akceptuj", "--wszystkie")                                         # zaakceptowane, ale jeszcze nie zaplanowane
    before, renders = state.load(), len(world.renders)
    rc, out, err = run("paczka")
    assert rc == 1 and "Najpierw krok 8: pierwsze wersje do akceptacji" in err and "zaplanuj" in err
    assert "zgodzie klienta" in err and "uruchom zaplanuj" not in err        # to nie polecenie planowania od ręki
    assert state.load() == before and len(world.renders) == renders and world.attempts == []


def test_paczka_waits_until_the_client_has_decided_about_every_first_version(world, run):
    """Klient, który zaakceptował i zaplanował jedną wersję z dziewięciu, nie odblokowuje ok. 70 wersji tygodniowo, których
    reszty pierwszej partii nigdy nie obejrzał."""
    world.pool(12)
    run("pierwsze", "--ile", "9")
    run("akceptuj", "TR-001", "TR-002")
    assert run("zaplanuj")[0] == 0 and versions.started(state.load())
    before, renders = state.load(), len(world.renders)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 1 and "Traceback" not in err and out == ""
    assert "7 wersji czeka na akceptację klienta (TR-003, TR-004, TR-005, TR-006, TR-007, TR-008, TR-009)" in err
    assert "„akceptuję”" in err and "akceptuj" in err and "odrzuc" in err and "paczka ruszy" in err
    assert state.load() == before and len(world.renders) == renders and world.analytics_calls == []
    assert run("akceptuj", "TR-003")[0] == 0 and run("odrzuc", "TR-004", "TR-005", "TR-006", "TR-007", "TR-008", "TR-009")[0] == 0
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err                                                    # po decyzji o każdej wersji paczka rusza


def test_paczka_names_a_single_waiting_version_in_the_singular(world, run):
    first_batch(world, run, n=3)
    with state.locked() as st:
        v = versions.new_version(st, "Reel010", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"},
                                 "2026-11-30T09:00:00", "do_akceptacji")
        versions.produce(st, v, False)
    rc, out, err = run("paczka")
    assert rc == 1 and "1 wersja czeka na akceptację klienta (%s)" % v["id"] in err


def test_paczka_dry_run_shows_the_plan_but_says_the_real_one_waits_for_the_decision(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "9")
    run("akceptuj", "TR-001")
    run("zaplanuj")
    before = snapshot(world)
    rc, out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0 and snapshot(world) == before and "Wersji w planie:" in out
    note = next(line for line in out.splitlines() if line.startswith("Uwaga: to tylko podgląd planu."))
    assert "8 wersji czeka na akceptację klienta" in note and "„akceptuję”" in note


def test_paczka_without_any_waiting_version_is_not_slowed_down(world, run):
    first_batch(world, run)
    run("odrzuc", "TR-001")                                                # zaplanowanej nie da się odrzucić: nic nie czeka
    rc, out, err = run("paczka", "--dni", "1")
    assert rc == 0, err
    assert "czeka na akceptację" not in out + err


def test_paczka_without_a_pool_says_what_to_do(world, run):
    config.save_settings({"ig_account_id": ACCOUNT})
    rc, out, err = run("paczka")
    assert rc == 1 and "Pula jest pusta" in err and world.analytics_calls == []


def test_paczka_dry_run_before_first_acceptance_shows_the_plan_with_a_note(world, run):
    world.pool(12)
    rc, out, err = run("paczka", "--dni", "1", "--na-sucho")
    assert rc == 0 and "krok 8" in out and "Wersji w planie: 10" in out
    assert world.renders == [] and load() == {}


def test_paczka_plans_renders_uploads_and_schedules_a_week(world, run):
    first_batch(world, run)
    renders, posts = len(world.renders), len(world.posts)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    new = len(world.renders) - renders
    assert new == 11 and len(world.posts) - posts == 11 and len(world.uploads) == 20
    vs = load().values()
    assert {v["status"] for v in vs} == {"zaplanowana"} and len(vs) == 20
    assert len({v["slot"] for v in vs}) == 20                                         # każdy termin raz
    assert max(Counter((v["slot"][:10], v["code"]) for v in vs).values()) == 1
    assert world.analytics_calls and world.analytics_calls[0][0] == ACCOUNT           # hamulec liczony z konta klienta
    assert max(Counter(p["scheduledFor"] for p in world.posts).values()) == 1


def test_paczka_start_begins_on_the_given_day(world, run):
    first_batch(world, run)
    rc, out, err = run("paczka", "--dni", "6", "--start", "2026-11-25")
    assert rc == 0, err
    new = [v for v in load().values() if v["id"] > "TR-009"]
    assert new and min(v["slot"] for v in new) >= "2026-11-25T00:00:00"


def test_paczka_with_a_bad_start_date_is_a_plain_message(world, run):
    first_batch(world, run)
    rc, out, err = run("paczka", "--start", "jutro")
    assert rc == 1 and "RRRR-MM-DD" in err and "Traceback" not in err


def test_paczka_dry_run_prints_the_plan_and_changes_nothing(world, run):
    first_batch(world, run)
    before, renders, uploads = state.load(), len(world.renders), len(world.uploads)
    rc, out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0, err
    assert state.load() == before and len(world.renders) == renders and len(world.uploads) == uploads
    assert len(world.posts) == 9 and "Wersji w planie: 11. Wolnych terminów: 11" in out and "Rolka" in out
    assert "Hamulec: wyłączony" in out


# --- plan na sucho: pyta Zernio o zajęte minuty, ale niczego nie wysyła ---------------------

def block_planned(world, rows, *numbers):
    """Cudze posty IG na terminach wybranych wierszy planu (numery od 0). Zwraca etykiety tych terminów."""
    labels = []
    for n in numbers:
        t = rows[n][0]
        world.foreign.append(("cudzy-post-%d" % n, t.astimezone(timezone.utc)))
        labels.append(versions.slot_label(t))
    return labels


def snapshot(world):
    return {"state": state.load(), "renders": len(world.renders), "uploads": len(world.uploads),
            "attempts": len(world.attempts), "created": len(world.created)}


def test_paczka_dry_run_asks_zernio_about_every_planned_slot_and_sends_nothing(world, run):
    first_batch(world, run)
    rows = versions.plan_rows(state.load(), 2)
    labels = block_planned(world, rows, 1, 4)
    before = snapshot(world)
    world.ig_checks.clear()
    rc, out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0 and err == ""
    assert sorted(world.ig_checks) == sorted(t.astimezone(timezone.utc) for t, *_ in rows)     # po jednym pytaniu na termin
    assert snapshot(world) == before                                       # 0 renderów, 0 wysyłek plików, 0 postów, stan bez zmian
    lines = out.splitlines()
    skipped = [line for line in lines if "masz już inny post na Instagramie" in line]
    assert len(skipped) == 2 and all(line.startswith("  ! ") for line in skipped)
    assert [label in line for label, line in zip(labels, skipped)] == [True, True]
    assert all("Pomijam ten termin." in line for line in skipped) and "cudzy-post" not in out
    assert "Wersji w planie: 11. Wolnych terminów: 11." in out
    assert "Na sucho: zaplanowałbym 9 z 11. Nic nie wysłałem i nic nie zmieniłem." in lines
    assert out.count("przesuń godziny triali") == 1 and "odrzuc " not in lines[-1] and "uruchom plan na sucho" in out
    assert lines.index(skipped[0]) > next(i for i, line in enumerate(lines) if line.startswith("Wersji w planie") or "Termin" in line)


def test_paczka_dry_run_reports_the_same_skips_as_the_real_run(world, run):
    first_batch(world, run)
    rows = versions.plan_rows(state.load(), 2)
    labels = block_planned(world, rows, 0, 5, 10)
    rc, dry_out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0 and sum("masz już inny post" in line for line in dry_out.splitlines()) == 3
    assert all(label in dry_out for label in labels)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    left = sorted(versions.slot_label(v["slot"]) for v in load().values() if v["status"] == "zaakceptowana")
    assert left == sorted(labels)                                          # prawdziwy przebieg pomija dokładnie te same terminy
    assert "Pominięte: 3." in out


def test_paczka_dry_run_without_a_clash_says_what_it_would_do_and_has_no_hint(world, run):
    first_batch(world, run)
    before = snapshot(world)
    rc, out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0 and snapshot(world) == before
    assert "Na sucho: zaplanowałbym 11 z 11. Nic nie wysłałem i nic nie zmieniłem." in out.splitlines()
    assert "masz już inny post" not in out and "przesuń godziny" not in out


def test_paczka_dry_run_mentions_accepted_versions_the_real_run_would_finish(world, run):
    """Wersja zaakceptowana bez posta (np. pominięta wcześniej przez cudzy post) to pierwsze, co robi prawdziwa paczka."""
    first_batch(world, run)
    with state.locked() as st:
        slot = versions.free_slots(st, 1)[0]
        stuck = versions.new_version(st, "Reel001", "subtelna", {"id": "h99", "text": "H", "emoji": "🔥"}, slot,
                                     "zaakceptowana")
        versions.produce(st, stuck, False)
    world.foreign.append(("cudzy-post", slot.astimezone(timezone.utc)))
    before = snapshot(world)
    rc, out, err = run("paczka", "--dni", "2", "--na-sucho")
    assert rc == 0 and snapshot(world) == before
    assert "Dokończyłbym zaakceptowane wersje, które nie trafiły jeszcze do Zernio: 1." in out
    assert "! %s: na %s masz już inny post na Instagramie. Pomijam tę wersję." % (stuck["id"], versions.slot_label(slot)) in out
    assert out.count("przesuń godziny triali") == 1 and ("odrzuc %s)" % stuck["id"]) in out.splitlines()[-1]
    assert load()[stuck["id"]]["status"] == "zaakceptowana"


def test_paczka_dry_run_before_the_first_planning_does_not_touch_accepted_versions(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "--wszystkie")
    before = snapshot(world)
    world.ig_checks.clear()
    rc, out, err = run("paczka", "--dni", "1", "--na-sucho")
    assert rc == 0 and snapshot(world) == before and "Dokończyłbym" not in out
    note = next(line for line in out.splitlines() if line.startswith("Uwaga: to tylko podgląd planu"))
    assert "zaplanuj" in note and "zgodzie klienta" in note              # brakuje planowania, a nie akceptacji
    assert "krok 8" not in note and "do akceptacji" not in note


def test_paczka_dry_run_before_the_first_acceptance_still_points_at_step_8(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    rc, out, err = run("paczka", "--dni", "1", "--na-sucho")
    note = next(line for line in out.splitlines() if line.startswith("Uwaga: to tylko podgląd planu"))
    assert rc == 0 and "krok 8" in note and "pierwsze wersje do akceptacji" in note


def test_paczka_dry_run_warns_when_the_plan_would_use_up_the_hook_bank(world, run):
    """Komunikat o banku hooków liczy się z planu, więc plan na sucho mówi to samo, co prawdziwa paczka."""
    world.pool(12, hooks=5)
    run("pierwsze", "--ile", "9")
    run("akceptuj", "--wszystkie")
    assert run("zaplanuj")[0] == 0
    assert versions.hook_bank_low(state.load()) == []                      # przed planem w bankach jest jeszcze po 4 hooki
    rc, dry_out, err = run("paczka", "--dni", "7", "--na-sucho")
    assert rc == 0 and "Bank hooków prawie pusty" in dry_out
    dry_line = next(line for line in dry_out.splitlines() if line.startswith("Bank hooków prawie pusty"))
    rc, out, err = run("paczka", "--dni", "7")
    assert rc == 0, err
    assert dry_line in out.splitlines()                                    # ta sama lista rolek


def test_zaplanuj_dry_run_asks_zernio_about_every_slot_and_never_uploads_or_posts(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "4")
    run("akceptuj", "--wszystkie")
    block_with_foreign_posts(world, "TR-002")
    before = snapshot(world)
    world.ig_checks.clear()
    rc, out, err = run("zaplanuj", "--na-sucho")
    assert rc == 0 and snapshot(world) == before
    assert len(world.ig_checks) == 4                                       # jedno pytanie na wersję, jak w prawdziwym przebiegu
    assert "Na sucho: zaplanowałbym 3 z 4. Nic nie wysłałem i nic nie zmieniłem." in out.splitlines()
    assert out.count("masz już inny post na Instagramie") == 1


def test_paczka_rerun_skips_taken_slots(world, run):
    first_batch(world, run)
    renders = len(world.renders)
    world.fail("render", 3, KeyboardInterrupt())                                      # przerwanie przy trzeciej wersji
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 130 and len(world.renders) - renders == 3 and len(world.posts) == 11
    world.heal()
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    live = [v for v in load().values() if v["status"] in LIVE]
    assert len(live) == 20 and max(Counter(v["slot"] for v in live).values()) == 1   # każdy termin ma jedną wersję
    assert len(world.posts) == 20 and max(Counter(p["scheduledFor"] for p in world.posts).values()) == 1
    assert len(world.renders) - renders == 3 + 9                                      # drugi przebieg zrobił tylko resztę
    assert len(world.uploads) == 20 and {v["status"] for v in live} == {"zaplanowana"}


def test_paczka_finishes_a_version_that_was_cut_off_before_posting(world, run):
    first_batch(world, run)
    world.fail("create", 3, KeyboardInterrupt())                                      # przerwanie przy wysyłce trzeciej
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 130 and len(world.posts) == 11
    cut = [v for v in load().values() if v["status"] == "zaakceptowana"]
    assert len(cut) == 1 and not cut[0].get("zernio_post_id") and cut[0]["media_url"]
    world.heal()
    uploads = len(world.uploads)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    assert len(world.posts) == 20 and max(Counter(p["scheduledFor"] for p in world.posts).values()) == 1
    assert {v["status"] for v in load().values()} == {"zaplanowana"}
    assert len(world.uploads) - uploads == 8                                          # urwana wersja nie wysyła pliku drugi raz


def test_paczka_cut_off_right_after_zernio_took_the_post_never_posts_it_twice(world, run, monkeypatch):
    """Przerwanie po utworzeniu posta, a przed zapisem stanu: Zernio ma post, a wersja o tym nie wie. Ponowna paczka nie
    tworzy drugiego posta na tę minutę (chroni ją sprawdzenie zajętego terminu), a o resztach mówi krok 8 i krok 10."""
    first_batch(world, run)
    real_save, posts_before = state.save, len(world.created)

    def cut_after_the_post(st):
        if len(world.created) > posts_before:
            raise KeyboardInterrupt()
        return real_save(st)

    monkeypatch.setattr(state, "save", cut_after_the_post)
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 130 and len(world.created) == posts_before + 1
    monkeypatch.setattr(state, "save", real_save)
    (stuck,) = [v for v in load().values() if v["status"] == "zaakceptowana"]
    assert not stuck.get("zernio_post_id")                                  # stan nie wie o poście, który istnieje w Zernio
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0, err
    assert len(world.created) == 20 and max(Counter(p["scheduledFor"] for p in world.posts).values()) == 1
    assert "! %s: na %s masz już inny post na Instagramie. Pomijam tę wersję." % (stuck["id"], versions.slot_label(stuck["slot"])) in out
    assert load()[stuck["id"]]["status"] == "zaakceptowana" and "odrzuc %s" % stuck["id"] in out    # klient odrzuca ją i usuwa post


def test_paczka_marks_a_failed_version_and_goes_on(world, run):
    first_batch(world, run)
    world.fail("upload", 3, zernio.ZernioError("POST /media/presign -> 400: zły plik", 400))
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 1                                                                     # coś się nie udało
    statuses = Counter(v["status"] for v in load().values())
    assert statuses == {"zaplanowana": 19, "blad": 1}
    bad = next(v for v in load().values() if v["status"] == "blad")
    assert "400" in bad["note"] and bad["id"] in out + err
    world.heal()
    assert [v["id"] for v in versions.open_errors(state.load())] == [bad["id"]]
    rc, out, err = run("paczka", "--dni", "2")                                         # jego termin jest znów wolny
    assert rc == 0
    live = [v for v in load().values() if v["status"] in LIVE]
    assert len(live) == 20 and max(Counter(v["slot"] for v in live).values()) == 1
    replacement = next(v for v in live if v["slot"] == bad["slot"])
    assert load()[bad["id"]]["status"] == "blad" and load()[bad["id"]]["replaced_by"] == replacement["id"]
    assert versions.open_errors(state.load()) == []                                    # błąd rozwiązany, alarm nie wisi
    assert bad["id"] not in versions.report_text(state.load())
    rc, out, err = run("status")
    assert "zastąpiona %s" % replacement["id"] in out


def test_paczka_stops_at_once_when_zernio_rejects_the_key(world, run):
    first_batch(world, run)
    renders = len(world.renders)
    world.fail("upload", 1, zernio.ZernioError("POST /media/presign -> 401: nie", 401))
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 1 and "klucz" in err and "Traceback" not in err
    assert len(world.renders) - renders == 1                                           # nie renderuje reszty na darmo
    assert "blad" not in {v["status"] for v in load().values()}
    left = [v for v in load().values() if v["status"] == "zaakceptowana"]
    assert len(left) == 1
    world.heal()
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0 and len(world.renders) - renders == 11                              # urwana wersja bez drugiego renderu
    assert {v["status"] for v in load().values()} == {"zaplanowana"} and len(world.posts) == 20


def test_paczka_stops_when_there_is_no_internet(world, run):
    import urllib.error

    first_batch(world, run)
    renders = len(world.renders)
    world.fail("upload", 1, urllib.error.URLError("brak sieci"))
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 1 and "internet" in err and len(world.renders) - renders == 1


def test_paczka_gives_up_after_three_failures_in_a_row(world, run):
    first_batch(world, run)
    renders = len(world.renders)

    def always(n, v):
        raise RuntimeError("dysk pełny")

    world.before_render = always
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 1 and len(world.renders) - renders == 3 and "dysk pełny" in out + err
    assert Counter(v["status"] for v in load().values())["blad"] == 3
    assert "3" in err and "Przerywam" in err


def test_paczka_lets_the_brake_leave_one_trial_a_day(world, run):
    world.pool(12)
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana",
                           ig_url="https://www.instagram.com/reel/Cfirst0001/"))

    def post(day, views):
        return {"publishedAt": "2026-%sT12:00:00Z" % day, "mediaType": "video", "isAd": False,
                "platformPostUrl": "https://www.instagram.com/reel/R%s%d/" % (day.replace("-", ""), views),
                "analytics": {"views": views}}

    world.analytics_posts = ([post("10-%02d" % d, 10000) for d in range(15, 25)]
                             + [post("11-%02d" % d, 6000) for d in (10, 12, 14, 16)])
    rc, out, err = run("paczka", "--dni", "3", "--na-sucho")
    assert rc == 0, err
    assert "włączony" in out.lower() and "1 trial dziennie" in out
    plan = [line for line in out.splitlines() if re.match(r"\s*2026-11-\d\d \d\d:\d\d", line)]
    assert len(plan) == 3 and all(" 13:00" in line for line in plan)
    rc, out, err = run("hamulec")
    assert rc == 0 and "włączony" in out.lower() and "0,60" in out
    assert state.load()["brake"]["on"] is True
    rc, out, err = run("paczka", "--dni", "3")
    new = [v for v in load().values() if v["id"] > "TR-001"]
    assert rc == 0 and len(new) == 3 and {v["slot"][11:16] for v in new} == {"13:00"}


def test_paczka_keeps_the_previous_brake_when_zernio_has_no_statistics(world, run):
    world.pool(12)
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana"), brake={"on": True})

    def refused(account_id, from_date, to_date):
        raise zernio.ZernioError("GET /analytics -> 402: plan", 402)

    world.monkeypatch.setattr(zernio, "analytics", refused)
    rc, out, err = run("hamulec")
    assert rc == 0 and "zostaje poprzedni stan" in out and "402" in out
    assert state.load()["brake"]["on"] is True


def test_paczka_without_the_account_stops_before_any_work(world, run):
    first_batch(world, run)
    config.save_settings({"ig_account_id": None})
    renders = len(world.renders)
    rc, out, err = run("paczka")
    assert rc == 1 and "Najpierw krok 3: konto Instagram" in err and len(world.renders) == renders


def test_paczka_suggests_fewer_trials_a_day_when_rendering_is_slow(world, run):
    first_batch(world, run)
    st = state.load()
    for v in st["versions"].values():
        v["render_s"] = 200.0
    state.save(st)
    rc, out, err = run("paczka", "--dni", "1", "--na-sucho")
    assert rc == 0 and "daily_max" in out and "3" in out and "90" in out
    for v in st["versions"].values():
        v["render_s"] = 2.0
    state.save(st)
    rc, out, err = run("paczka", "--dni", "1", "--na-sucho")
    assert rc == 0 and "daily_max" not in out


def test_paczka_exit_code_is_zero_when_there_is_nothing_to_plan(world, run):
    first_batch(world, run)
    assert run("paczka", "--dni", "1")[0] == 0                                         # został jeden wolny termin
    renders = len(world.renders)
    rc, out, err = run("paczka", "--dni", "1")
    assert rc == 0 and "Nie ma wolnych terminów" in out and len(world.renders) == renders


def test_paczka_mentions_a_nearly_empty_hook_bank(world, run):
    world.pool(12, hooks=3)
    run("pierwsze", "--ile", "9")
    run("akceptuj", "--wszystkie")
    run("zaplanuj")
    rc, out, err = run("paczka", "--dni", "2")
    assert rc == 0 and "Bank hooków" in out and "powtórki" in out


# --- sprawdzanie publikacji i sprzątanie -------------------------------------------------

def test_cleanup_deletes_only_old_published(world):
    world.pool(12)
    files = {}
    vs = []
    for vid, days, status in (("TR-001", 20, "opublikowana"), ("TR-002", 5, "opublikowana"),
                              ("TR-003", 20, "zaplanowana"), ("TR-004", 20, "blad"), ("TR-005", 20, "do_akceptacji"),
                              ("TR-006", 20, "odrzucona"), ("TR-007", 14, "opublikowana"), ("TR-008", 13, "opublikowana")):
        config.OUT.mkdir(parents=True, exist_ok=True)
        mp4, png = config.OUT / ("%s.mp4" % vid), config.OUT / ("%s_hook.png" % vid)
        mp4.write_bytes(b"film")
        png.write_bytes(b"png")
        files[vid] = (mp4, png)
        vs.append(make_version(vid, days_ago=days, status=status, file=str(mp4)))
    st = {"seq": 8, "versions": {v["id"]: v for v in vs}}
    assert versions.cleanup(st) == 2                                                    # TR-001 i TR-007 (równo 14 dni)
    for vid, (mp4, png) in files.items():
        gone = vid in ("TR-001", "TR-007")
        assert mp4.exists() is not gone and png.exists() is not gone, vid
    assert versions.cleanup(st) == 0                                                    # drugi raz nie ma co kasować
    assert versions.cleanup(st, days=3) == 2                                            # TR-002 i TR-008 po zmianie progu


def test_cleanup_does_not_touch_files_outside_the_versions_folder(world, tmp_path):
    world.pool(12)
    outside = tmp_path / "moje-wideo.mp4"
    outside.write_bytes(b"cenne")
    st = {"seq": 1, "versions": {"TR-001": make_version("TR-001", days_ago=30, status="opublikowana",
                                                          file=str(outside))}}
    assert versions.cleanup(st) == 0 and outside.exists()


def test_cleanup_never_deletes_a_file_named_like_the_version_outside_the_versions_folder(world, tmp_path):
    outside = tmp_path / "TR-001.mp4"
    outside.write_bytes(b"cenne")
    st = {"seq": 1, "versions": {"TR-001": make_version("TR-001", days_ago=30, status="opublikowana",
                                                          file=str(outside))}}
    versions.cleanup(st)
    assert outside.read_bytes() == b"cenne"


def test_cleanup_skips_a_version_id_that_points_outside_the_versions_folder(world):
    """D6: numer wersji ze stan.json trafia do nazwy kasowanego pliku, więc zły numer nie może wyjść z dane/wersje."""
    config.OUT.mkdir(parents=True, exist_ok=True)
    victim = config.DATA / "cenne.mp4"
    victim.write_bytes(b"cenne")
    st = {"seq": 1, "versions": {"../cenne": make_version("../cenne", days_ago=30, status="opublikowana")}}
    assert versions.cleanup(st) == 0 and victim.read_bytes() == b"cenne"


def test_the_video_sent_to_zernio_always_comes_from_the_versions_folder(world, tmp_path):
    """D6: pole `file` w stan.json mogłoby wskazać dowolny plik z dysku, który poszedłby do Zernio jako rolka."""
    secret = tmp_path / "skan.jpg"
    secret.write_bytes(b"prywatne")
    v = make_version("TR-001", file=str(secret))
    assert versions.video_file(v) == config.OUT / "TR-001.mp4"
    with pytest.raises(config.UserError):
        versions.video_file(make_version("../../skan"))
    if os.name != "nt":
        config.OUT.mkdir(parents=True, exist_ok=True)
        (config.OUT / "TR-001.mp4").symlink_to(secret)
        with pytest.raises(config.UserError, match="dane/wersje"):
            versions.video_file(v)


def test_scheduling_never_uploads_a_file_named_in_the_state_from_outside_the_versions_folder(world, run, tmp_path):
    world.pool(12)
    secret = tmp_path / "skan.mp4"
    secret.write_bytes(b"prywatne")
    put_state(make_version("TR-001", slot=(NOW + timedelta(days=1)).strftime("%Y-%m-%dT09:00:00"),
                           status="zaakceptowana", file=str(secret)))
    rc, out, err = run("zaplanuj")
    assert rc == 0, out + err
    assert world.uploads == ["TR-001.mp4"] and world.renders == ["TR-001"]      # render od nowa, wysyłka z dane/wersje


def test_cleanup_survives_a_version_without_a_file_or_a_slot(world):
    st = {"seq": 2, "versions": {"TR-001": make_version("TR-001", days_ago=30, status="opublikowana"),
                                 "TR-002": make_version("TR-002", slot=None, status="opublikowana")}}
    assert versions.cleanup(st) == 0


def test_sprawdz_marks_published_failed_and_missing_posts_and_cleans(world, run):
    world.pool(12)
    config.OUT.mkdir(parents=True, exist_ok=True)
    old = config.OUT / "TR-009.mp4"
    old.write_bytes(b"film")
    put_state(
        make_version("TR-001", days_ago=1, zernio_post_id="p1"),
        make_version("TR-002", days_ago=1, zernio_post_id="p2"),
        make_version("TR-003", days_ago=1, zernio_post_id="p3"),
        make_version("TR-004", days_ago=1, zernio_post_id="p4"),
        make_version("TR-005", slot="2026-11-22T09:00:00", zernio_post_id="p5"),          # jeszcze nie wyszła
        make_version("TR-009", days_ago=30, status="opublikowana", file=str(old)))
    world.remote = {
        "p1": {"status": "published", "platforms": [{"status": "published",
                                                      "platformPostUrl": "https://www.instagram.com/reel/Cabc123XYZ_/"}]},
        "p2": {"status": "failed", "platforms": [{"status": "failed", "errorMessage": "Instagram odrzucił film"}]},
        "p3": zernio.ZernioError("GET /posts/p3 -> 404: nie ma", 404),
        "p4": {"status": "scheduled", "platforms": [{"status": "scheduled"}]},
    }
    rc, out, err = run("sprawdz")
    assert rc == 0, err
    vs = load()
    assert vs["TR-001"]["status"] == "opublikowana"
    assert vs["TR-001"]["ig_url"] == "https://www.instagram.com/reel/Cabc123XYZ_/"
    assert vs["TR-001"]["ig_media_id"] == candidates.media_id("Cabc123XYZ_")
    assert vs["TR-002"]["status"] == "blad" and "Instagram odrzucił film" in vs["TR-002"]["note"]
    assert vs["TR-003"]["status"] == "blad" and "Zernio" in vs["TR-003"]["note"]
    assert vs["TR-004"]["status"] == "zaplanowana" and vs["TR-005"]["status"] == "zaplanowana"
    assert not old.exists()
    assert "Opublikowane: 1" in out and "Błędy: 2" in out and "Usunięte pliki starych wersji: 1" in out


def test_sprawdz_waits_when_zernio_has_no_link_yet(world, run):
    world.pool(12)
    put_state(make_version("TR-001", days_ago=1, zernio_post_id="p1"))
    world.remote = {"p1": {"status": "published", "platforms": [{"status": "published"}]}}
    rc, out, err = run("sprawdz")
    assert rc == 0 and load()["TR-001"]["status"] == "zaplanowana"


def test_sprawdz_does_not_ask_zernio_about_the_future(world, run):
    world.pool(12)
    put_state(make_version("TR-001", slot="2026-11-22T09:00:00", zernio_post_id="p1"))
    rc, out, err = run("sprawdz")                                                      # get_post rzuciłby KeyError
    assert rc == 0 and load()["TR-001"]["status"] == "zaplanowana"


def test_sprawdz_stops_with_a_plain_message_when_the_key_is_rejected(world, run):
    world.pool(12)
    put_state(make_version("TR-001", days_ago=1, zernio_post_id="p1"))
    world.remote = {"p1": zernio.ZernioError("GET /posts/p1 -> 401: nie", 401)}
    rc, out, err = run("sprawdz")
    assert rc == 1 and "klucz" in err and "Traceback" not in err and load()["TR-001"]["status"] == "zaplanowana"


# --- wyniki: odczyt i zapis -------------------------------------------------------------

def published(vid, code, days_ago, pk, **extra):
    return make_version(vid, code, days_ago=days_ago, status="opublikowana", ig_media_id=pk,
                        ig_url="https://www.instagram.com/reel/Cabc123XYZ_/", **extra)


def test_do_odczytu_prints_ids_with_english_panel_urls(world, run):
    world.pool(12)
    put_state(published("TR-001", "Reel001", 5, "111"), published("TR-002", "Reel002", 2, "222"),
              published("TR-003", "Reel003", 40, "333"), make_version("TR-004", days_ago=5, status="zaplanowana"))
    rc, out, err = run("do-odczytu")
    assert rc == 0
    assert out.splitlines() == ["TR-001  https://www.instagram.com/insights/media/111/?hl=en"]


def test_do_odczytu_sample_is_the_newest_trial_of_each_reel(world, run):
    world.pool(12)
    put_state(published("TR-001", "Reel001", 20, "111"), published("TR-002", "Reel001", 10, "222"),
              published("TR-003", "Reel002", 8, "333"))
    rc, out, err = run("do-odczytu", "--probka")
    assert rc == 0 and out.splitlines() == ["TR-002  https://www.instagram.com/insights/media/222/?hl=en",
                                           "TR-003  https://www.instagram.com/insights/media/333/?hl=en"]
    rc, out, err = run("do-odczytu")
    assert len(out.splitlines()) == 3


def many_published(count, reels=12):
    """`count` opublikowanych triali w wieku 4-28 dni (wszystkie do odczytu), rozłożonych po `reels` rolkach."""
    return [published("TR-%03d" % i, "Reel%03d" % (i % reels + 1), 4 + i % 25, str(1000 + i)) for i in range(1, count + 1)]


def address_lines(out):
    return [line for line in out.splitlines() if line.startswith("TR-")]


def test_do_odczytu_lists_at_most_thirty_addresses_and_says_how_many_it_left_out(world, run):
    """Po kilku tygodniach do odczytu jest ponad 300 triali, więc samo `do-odczytu` nie może wypisać wszystkich."""
    world.pool(12)
    items = many_published(100)
    put_state(*items)
    rc, out, err = run("do-odczytu")
    assert rc == 0 and err == ""
    lines = address_lines(out)
    assert len(lines) == cli.DUE_LIMIT == 30
    oldest = [v["id"] for v in sorted(items, key=lambda v: (v["slot"], v["id"]))][:30]
    assert [line.split()[0] for line in lines] == oldest                       # najstarsze najpierw, jak dotąd
    assert all(re.fullmatch(r"TR-\d{3}  https://www\.instagram\.com/insights/media/\d+/\?hl=en", line) for line in lines)
    note = out.splitlines()[-1]
    assert note.startswith("Pominięte: 70.") and "najwyżej 30 adresów" in note
    assert "do-odczytu jeszcze raz" in note and "do-odczytu --probka" in note


def test_do_odczytu_says_nothing_about_skipping_when_everything_fits(world, run):
    world.pool(12)
    put_state(*many_published(30))
    rc, out, err = run("do-odczytu")
    assert len(address_lines(out)) == 30 and "Pominięte" not in out and len(out.splitlines()) == 30
    put_state(*many_published(31))
    rc, out, err = run("do-odczytu")
    assert len(address_lines(out)) == 30 and out.splitlines()[-1].startswith("Pominięte: 1.")


def test_do_odczytu_shows_the_next_thirty_once_the_first_thirty_are_saved(world, run):
    world.pool(12)
    put_state(*many_published(45))
    first = [line.split()[0] for line in address_lines(run("do-odczytu")[1])]
    for vid in first:
        assert run("zapisz-wynik", vid, "--wyswietlenia", "100", "--obserwujacy", "1")[0] == 0
    rc, out, err = run("do-odczytu")
    second = [line.split()[0] for line in address_lines(out)]
    assert len(second) == 15 and not set(first) & set(second) and "Pominięte" not in out


def test_do_odczytu_sample_is_one_address_per_reel_and_is_never_cut(world, run):
    """Tygodniowy odczyt idzie z `--probka`: najwyżej jedna, najnowsza wersja rolki, więc kilkanaście adresów."""
    world.pool(12)
    put_state(*many_published(100))
    rc, out, err = run("do-odczytu", "--probka")
    lines = address_lines(out)
    assert rc == 0 and len(lines) == 12 and len(out.splitlines()) == 12 and "Pominięte" not in out
    by_id = load()
    assert len({by_id[line.split()[0]]["code"] for line in lines}) == 12
    for line in lines:                                       # każda to najnowsza wersja swojej rolki
        shown = by_id[line.split()[0]]
        assert shown["slot"] == max(v["slot"] for v in by_id.values() if v["code"] == shown["code"])


def test_do_odczytu_with_nothing_due_says_why_in_plain_words(world, run):
    world.pool(12)
    rc, out, err = run("do-odczytu")
    assert rc == 0 and "TR-" not in out and "3 dni" in out


def test_zapisz_wynik_saves_counts_in_any_panel_format(world, run):
    world.pool(12)
    put_state(published("TR-001", "Reel001", 5, "111"))
    rc, out, err = run("zapisz-wynik", "TR-001", "--wyswietlenia", "12,3 tys.", "--obserwujacy", "9")
    assert rc == 0, err
    v = load()["TR-001"]
    assert v["views"] == 12300 and v["follows"] == 9 and v["read_at"] == "2026-11-21T12:00"
    assert "12 300" in out and "9" in out
    rc, out, err = run("zapisz-wynik", "tr-1", "--wyswietlenia", "345,678", "--obserwujacy", "1,234")
    assert rc == 0 and load()["TR-001"]["views"] == 345678 and load()["TR-001"]["follows"] == 1234


def test_zapisz_wynik_rejects_text_that_is_not_a_number_and_unknown_versions(world, run):
    world.pool(12)
    put_state(published("TR-001", "Reel001", 5, "111"))
    rc, out, err = run("zapisz-wynik", "TR-001", "--wyswietlenia", "dużo", "--obserwujacy", "9")
    assert rc == 1 and "Nie rozumiem liczby" in err and "views" not in load()["TR-001"]
    rc, out, err = run("zapisz-wynik", "TR-077", "--wyswietlenia", "100", "--obserwujacy", "1")
    assert rc == 1 and "Nie ma wersji TR-077" in err


def test_zapisz_wynik_warns_about_a_trial_that_is_not_published_yet(world, run):
    world.pool(12)
    put_state(make_version("TR-001", days_ago=1, status="zaplanowana"))
    rc, out, err = run("zapisz-wynik", "TR-001", "--wyswietlenia", "100", "--obserwujacy", "1")
    assert rc == 0 and "Uwaga" in err and load()["TR-001"]["views"] == 100


def test_a_saved_result_is_not_asked_for_again_this_week(world, run):
    world.pool(12)
    put_state(published("TR-001", "Reel001", 5, "111"))
    assert "TR-001" in run("do-odczytu")[1]
    run("zapisz-wynik", "TR-001", "--wyswietlenia", "100", "--obserwujacy", "1")
    assert "TR-001" not in run("do-odczytu")[1]


# --- hamulec, raport i status ----------------------------------------------------------

def test_hamulec_without_trials_says_there_is_not_enough_data(world, run):
    world.pool(12)
    rc, out, err = run("hamulec")
    assert rc == 0 and "wyłączony" in out and "za mało danych" in out
    assert state.load()["brake"]["on"] is False


def test_the_brake_stays_on_when_there_is_too_little_data_to_say_whether_reach_came_back(world, run):
    """Klient, który publikuje rzadko, nie dostaje wskaźnika. Włączony hamulec nie może wtedy cicho zniknąć."""
    world.pool(12)
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana"), brake={"on": True})
    assert world.analytics_posts == []                                    # żadnych zwykłych rolek w oknie
    rc, out, err = run("hamulec")
    brake = state.load()["brake"]
    assert rc == 0 and brake["on"] is True and brake["ratio"] is None and brake["checked"].startswith("2026-11-21")
    assert "WŁĄCZONY, 1 trial dziennie" in out and "zostaje" in out and "za mało danych" in out and "1000" in out
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana"), brake={"on": False})
    rc, out, err = run("hamulec")
    assert state.load()["brake"]["on"] is False and "wyłączony (nieaktywny: za mało danych" in out


def test_the_brake_switches_off_after_two_weeks_without_data(world, run):
    """Włączony hamulec bez danych nie może trzymać klienta na 1 trialu dziennie bez końca."""
    world.pool(12)
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana"),
              brake={"on": True, "nodata_since": "2026-11-12T09:00+01:00"})
    rc, out, err = run("hamulec")
    brake = state.load()["brake"]
    assert rc == 0 and brake["on"] is True and brake["nodata_since"].startswith("2026-11-12")
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana"),
              brake={"on": True, "nodata_since": "2026-11-05T09:00+01:00"})
    rc, out, err = run("hamulec")
    brake = state.load()["brake"]
    assert rc == 0 and brake["on"] is False and "od 14 dni nie ma danych" in out


def test_the_brake_still_switches_off_when_reach_is_back(world, run):
    world.pool(12)
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana"), brake={"on": True})

    def post(day, views):
        return {"publishedAt": "2026-%sT12:00:00Z" % day, "mediaProductType": "REELS", "isAd": False,
                "platformPostUrl": "https://www.instagram.com/reel/R%s%d/" % (day.replace("-", ""), views),
                "analytics": {"views": views}}

    world.analytics_posts = ([post("10-%02d" % d, 10000) for d in range(15, 25)]
                             + [post("11-%02d" % d, 9500) for d in (10, 12, 14, 16)])
    rc, out, err = run("hamulec")
    assert rc == 0 and "wyłączony" in out.lower() and "0,95" in out
    assert state.load()["brake"]["on"] is False and state.load()["brake"]["ratio"] == 0.95


def test_check_brake_asks_zernio_for_the_clients_account_and_window(world):
    world.pool(12)
    put_state(make_version("TR-001", slot="2026-11-09T09:00:00", status="opublikowana"))
    with state.locked() as full:
        versions.check_brake(full)
    account, since, until = world.analytics_calls[0]
    assert account == ACCOUNT and until == NOW.date()
    assert since == (datetime(2026, 11, 9, 9, tzinfo=WARSAW) - timedelta(days=29)).date()


def test_report_lists_reels_best_versions_errors_and_upcoming(world, run):
    world.pool(12)
    put_state(
        make_version("TR-001", "Reel001", days_ago=10, status="opublikowana", views=1000, follows=5,
                     ig_url="https://www.instagram.com/reel/Cabc123XYZ_/"),
        make_version("TR-002", "Reel001", days_ago=9, status="opublikowana", views=1000, follows=1, hook="Inny hook"),
        make_version("TR-003", "Reel002", days_ago=8, status="opublikowana", views=2000, follows=0),
        make_version("TR-004", "Reel003", days_ago=1, status="blad", note="Brak transkrypcji"),
        make_version("TR-005", "Reel004", slot="2026-11-22T09:00:00", status="zaplanowana"))
    text = versions.report_text(state.load())
    assert text.startswith("# Trial reels: raport 21.11.2026")
    assert "| Rolka 1 | 2 | 2 | 2000 | 6 | 3,0 | 1 |" in text           # liczby po polsku: przecinek dziesiętny
    assert "| Rolka 2 | 1 | 1 | 2000 | 0 | 0,0 | 1 |" in text
    assert "TR-001" in text and "5 obserwujących z 1000 wyświetleń" in text
    assert "Błędy:" in text and "TR-004: Brak transkrypcji" in text
    assert "Zaplanowane na najbliższe dni: 1." in text
    assert "Hamulec: wyłączony (nieaktywny: za mało zwykłych rolek, żeby go policzyć)." in text


def test_report_best_versions_have_a_link_only_when_the_version_has_one(world):
    """Wersja zmierzona ręcznie, zanim ma opublikowany adres, nie dostaje pustego nawiasu „()”."""
    world.pool(12)
    put_state(make_version("TR-001", "Reel001", days_ago=10, status="opublikowana", views=1000, follows=5,
                           ig_url="https://www.instagram.com/reel/Cabc123XYZ_/"),
              make_version("TR-002", "Reel002", days_ago=9, status="zaplanowana", views=1200, follows=3),
              make_version("TR-003", "Reel003", days_ago=8, status="opublikowana", views=800, follows=2, ig_url=""),
              make_version("TR-004", "Reel004", days_ago=7, status="opublikowana", views=900, follows=1, ig_url=None))
    text = versions.report_text(state.load())
    assert "()" not in text and "( )" not in text
    best = {line.split()[1]: line for line in text.splitlines() if line.startswith("- TR-")}
    assert best["TR-001"].endswith("5 obserwujących z 1000 wyświetleń (https://www.instagram.com/reel/Cabc123XYZ_/)")
    for vid, line in (("TR-002", "3 obserwujących z 1200 wyświetleń"), ("TR-003", "2 obserwujących z 800 wyświetleń"),
                      ("TR-004", "1 obserwujących z 900 wyświetleń")):
        assert best[vid].endswith(line), best[vid]


def test_report_shows_the_brake_ratio_and_half_weights_in_polish(world):
    world.pool(12)
    put_state(make_version("TR-001", "Reel001", days_ago=3, status="opublikowana", views=1000, follows=5),
              brake={"on": True, "ratio": 0.62})
    assert "Hamulec: włączony, 1 trial dziennie (wskaźnik 0,62)." in versions.report_text(state.load())
    put_state(make_version("TR-001", "Reel001", days_ago=3, status="opublikowana", views=1000, follows=5),
              brake={"on": True, "ratio": None})
    assert ("Hamulec: włączony, 1 trial dziennie (zostaje, bo za mało zwykłych rolek, żeby sprawdzić, czy zasięg wrócił)."
            in versions.report_text(state.load()))
    put_state(*[make_version("TR-%03d" % i, "Reel%03d" % i, days_ago=3, status="opublikowana", views=1000,
                             follows=12 - i) for i in range(1, 9)])                  # 8 zmierzonych rolek
    table = versions.report_text(state.load()).split("| Waga |")[1].split("Najlepsze")[0]
    assert " 2 |" in table and " 0,5 |" in table and "." not in table              # wagi 2 i 0,5, przecinek zamiast kropki


def test_report_survives_a_reel_that_left_the_pool_and_a_name_with_a_bar(world):
    world.pool(2)
    pool = candidates.load_pool()
    pool[0]["name"] = "Rolka | z kreską"
    candidates.save_pool(pool)
    put_state(make_version("TR-001", "Reel001", days_ago=3, status="opublikowana", views=100, follows=1),
              make_version("TR-002", "Usunieta1", days_ago=3, status="opublikowana", views=100, follows=1))
    text = versions.report_text(state.load())
    assert "| Rolka / z kreską |" in text and "Usunieta1" in text


def test_report_command_writes_the_file_and_prints_it(world, run):
    world.pool(12)
    put_state(make_version("TR-001", "Reel001", days_ago=3, status="opublikowana", views=500, follows=2))
    rc, out, err = run("raport")
    assert rc == 0
    path = config.REPORTS / "2026-11-21.md"
    assert path.is_file() and path.read_text(encoding="utf-8").startswith("# Trial reels: raport 21.11.2026")
    assert "Trial reels: raport" in out and "2026-11-21.md" in out
    assert b"\r" not in path.read_bytes()                                               # takie samo na Macu i Windowsie


def test_status_lists_versions_with_a_summary(world, run):
    world.pool(12)
    run("pierwsze", "--ile", "3")
    run("akceptuj", "TR-001")
    rc, out, err = run("status")
    assert rc == 0, err
    for expected in ("TR-001", "TR-002", "TR-003", "Zaakceptowana", "Do akceptacji", "Rolka"):
        assert expected in out, expected
    assert "Wersji: 3" in out and "Hamulec: wyłączony" in out


def status_ids(out):
    return [line.split()[0] for line in out.splitlines() if line.startswith("TR-")]


def test_status_shows_the_last_fourteen_days_and_open_errors_and_everything_on_request(world, run):
    """Po kilku tygodniach `status` miałby setki wierszy przy każdym wywołaniu, a Claude klienta woła go często."""
    world.pool(12)
    old = "2026-09-01T10:00:00+02:00"
    put_state(
        make_version("TR-001", "Reel001", days_ago=40, status="opublikowana", created=old),
        make_version("TR-002", "Reel002", days_ago=20, status="opublikowana", created=old),
        make_version("TR-003", "Reel003", days_ago=5, status="opublikowana"),
        make_version("TR-004", "Reel004", slot="2026-11-25T09:00:00", status="zaplanowana"),         # przyszły termin
        make_version("TR-005", "Reel005", days_ago=30, status="blad", created=old),                  # błąd bez zastępstwa
        make_version("TR-006", "Reel006", days_ago=30, status="blad", created=old, replaced_by="TR-007"),
        make_version("TR-007", "Reel006", days_ago=30, status="opublikowana", created=old))
    rc, out, err = run("status")
    assert rc == 0 and err == ""
    assert status_ids(out) == ["TR-003", "TR-004", "TR-005"]
    assert out.startswith("Wersji: 7 (")                                           # podsumowanie liczy wszystkie
    note = next(line for line in out.splitlines() if line.startswith("Pokazuję"))
    assert note == ("Pokazuję 3 z 7 wersji: z ostatnich 14 dni i te z błędem. Wszystkie pokaże komenda "
                    "status --wszystkie.")
    rc, out, err = run("status", "--wszystkie")
    assert status_ids(out) == ["TR-%03d" % n for n in range(1, 8)] and "Pokazuję" not in out


def test_status_says_so_when_nothing_is_recent(world, run):
    world.pool(12)
    old = "2026-09-01T10:00:00+02:00"
    put_state(make_version("TR-001", "Reel001", days_ago=40, status="opublikowana", created=old))
    rc, out, err = run("status")
    assert rc == 0 and status_ids(out) == [] and "Wersji: 1 (" in out
    assert "W ostatnich 14 dniach nie ma wersji" in out and "status --wszystkie" in out
    assert status_ids(run("status", "--wszystkie")[1]) == ["TR-001"]


def test_status_keeps_the_output_short_however_many_versions_there_are(world, run):
    world.pool(12)
    old = "2026-09-01T10:00:00+02:00"
    put_state(*[make_version("TR-%03d" % n, "Reel001", days_ago=30 + n % 30, status="opublikowana", created=old)
                for n in range(1, 301)], make_version("TR-301", "Reel002", days_ago=1, status="opublikowana"))
    rc, out, err = run("status")
    assert len(out.splitlines()) < 12 and status_ids(out) == ["TR-301"]


def test_status_with_no_versions_points_to_the_first_step(world, run):
    world.pool(12)
    rc, out, err = run("status")
    assert rc == 0 and "pierwsze" in out


def test_status_shows_results_and_survives_a_reel_that_left_the_pool(world, run):
    world.pool(2)
    put_state(make_version("TR-001", "Reel001", days_ago=3, status="opublikowana", views=1234, follows=5),
              make_version("TR-002", "Usunieta1", days_ago=3, status="opublikowana"))
    rc, out, err = run("status")
    assert rc == 0 and "1 234" in out and "Usunieta1" in out


# --- funkcje pomocnicze -----------------------------------------------------------------

def test_new_version_rotates_captions_and_changes_the_emoji_when_a_hook_repeats(world):
    world.pool(12)
    hook = {"id": "h01", "text": "Ten sam hook", "emoji": "🔥"}
    with state.locked() as st:
        first = versions.new_version(st, "Reel001", "subtelna", hook, None, "do_akceptacji")
        second = versions.new_version(st, "Reel001", "srednia", hook, None, "do_akceptacji")
    assert first["id"] == "TR-001" and second["id"] == "TR-002"
    assert first["emoji"] == "🔥" and second["emoji"] != "🔥" and second["emoji"] in render.ALT_EMOJI
    assert first["caption"] != second["caption"]
    assert first["params"] == render.params_for("TR-001", "subtelna", pool_reel("Reel001"))
    assert first["created"].startswith("2026-11-21T12:00:00")


def pool_reel(code):
    return next(r for r in candidates.load_pool() if r["code"] == code)


def test_produce_measures_the_render_and_saves_the_state_before_uploading(world):
    world.pool(12)
    seen = {}

    def spy(path):
        seen["saved"] = "TR-001" in state.load()["versions"]
        return "https://cdn.example.com/temp/x.mp4"

    world.monkeypatch.setattr(zernio, "upload", spy)
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"}, None,
                                 "zaakceptowana")
        versions.produce(st, v, True)
    assert seen["saved"] is True                                  # wersja po renderze jest już na dysku
    assert isinstance(v["render_s"], float) and v["render_s"] >= 0
    assert v["media_url"] == "https://cdn.example.com/temp/x.mp4" and v["uploaded_at"].startswith("2026-11-21T12:00:00")


def test_produce_without_upload_leaves_zernio_alone(world):
    world.pool(12)
    with state.locked() as st:
        v = versions.new_version(st, "Reel001", "subtelna", {"id": "h01", "text": "H", "emoji": "🔥"}, None,
                                 "do_akceptacji")
        versions.produce(st, v, False)
    assert world.uploads == [] and "media_url" not in v and "render_s" in v


def test_a_video_file_is_found_again_after_the_folder_was_moved(world):
    world.pool(12)
    v = make_version("TR-001", days_ago=1, file="/stary/folder/TR-001.mp4")
    config.OUT.mkdir(parents=True, exist_ok=True)
    (config.OUT / "TR-001.mp4").write_bytes(b"film")
    assert versions.video_file(v) == config.OUT / "TR-001.mp4"


def test_plan_rows_respect_taken_slots_limit_and_start(world):
    world.pool(12)
    st = {"seq": 0, "versions": {}, "brake": {"on": False}}
    rows = versions.plan_rows(st, 2)
    assert rows and all(len(r) == 4 for r in rows)
    t, code, level, hook = rows[0]
    assert t == datetime(2026, 11, 21, 13, 0, tzinfo=WARSAW) and level in config.LEVELS and hook["id"] == "h01"
    assert len(versions.plan_rows(st, 2, limit=4)) == 4
    start = datetime(2026, 11, 22, 0, 0, tzinfo=WARSAW)
    assert min(r[0] for r in versions.plan_rows(st, 3, start=start)) >= start
    st["versions"]["TR-001"] = make_version("TR-001", slot="2026-11-21T13:00:00", status="zaplanowana")
    assert versions.plan_rows(st, 2)[0][0] == datetime(2026, 11, 21, 14, 20, tzinfo=WARSAW)
    st["brake"]["on"] = True
    assert {r[0].strftime("%H:%M") for r in versions.plan_rows(st, 3)} == {"13:00"}


def test_the_pool_is_read_without_broken_entries(world):
    world.pool(3)
    pool = candidates.load_pool()
    pool += [{"code": "../zly-kod", "name": "ścieżka zamiast kodu"}, {"code": "zły kod", "name": "spacja"},
             {"code": 123, "name": "liczba"}, {"name": "bez kodu"}, "nie obiekt", {"code": "R00", "name": "za krótki"},
             {"code": "Krotki_6", "name": "sześć znaków to już kod"}]
    candidates.save_pool(pool)
    assert [r["code"] for r in versions.pool_list()] == ["Reel001", "Reel002", "Reel003", "Krotki_6"]
    assert set(versions.pool()) == {"Reel001", "Reel002", "Reel003", "Krotki_6"}


def test_every_part_of_the_program_counts_the_same_reels_as_valid(world, run):
    """Kod rolki ma jedną definicję (`candidates.valid_code`): wpis z za krótkim kodem nie liczy się do dziennej liczby
    triali ani do aktywnych rolek, a `sprawdz-pule` go zgłasza."""
    world.pool(3)
    candidates.save_pool(candidates.load_pool() + [{"code": "R00", "name": "za krótki", "active": True}])
    assert [r["code"] for r in versions.pool_list()] == ["Reel001", "Reel002", "Reel003"]
    assert len(versions.hours()) == 3 and len(cli.active_reels(candidates.load_pool())) == 3
    assert len(wizard._active()) == 3
    rc, out, err = run("sprawdz-pule")
    assert rc == 1 and "„R00”" in out and "za krótki" in out


def test_planned_on_lists_versions_scheduled_for_a_day(world):
    world.pool(12)
    st = {"seq": 4, "versions": {
        "TR-001": make_version("TR-001", slot="2026-11-22T09:00:00", status="zaplanowana"),
        "TR-002": make_version("TR-002", slot="2026-11-22T21:00:00", status="zaplanowana"),
        "TR-003": make_version("TR-003", slot="2026-11-22T10:20:00", status="do_akceptacji"),
        "TR-004": make_version("TR-004", slot="2026-11-23T09:00:00", status="zaplanowana")}}
    assert [v["id"] for v in versions.planned_on(st, datetime(2026, 11, 22, tzinfo=WARSAW).date())] == ["TR-001", "TR-002"]
    assert versions.planned_on(st, datetime(2026, 11, 24, tzinfo=WARSAW).date()) == []
    assert [v["id"] for v in versions.planned_on(st, datetime(2026, 11, 22).date(), statuses=("do_akceptacji",))] == ["TR-003"]


def test_hooks_ignore_the_rules_entry(world):
    world.pool(2)
    bank = candidates.load_hooks()
    bank["_zasady"] = "tekst"
    config.write_json(config.HOOKS, bank)
    assert set(versions.hooks()) == {"Reel001", "Reel002"}


def test_no_command_posts_outside_the_day_window_even_with_odd_slots(world, run):
    first_batch(world, run)
    run("paczka", "--dni", "3")
    assert all(planner.is_daytime(planner.parse_slot(v["slot"])) for v in load().values())
    assert world.posts and all("07:15" <= p["scheduledFor"][11:16] <= "22:00" for p in world.posts)


# --- wejście do komend ---------------------------------------------------------------

CYCLE_COMMANDS = ("pierwsze", "podglad", "akceptuj", "odrzuc", "zaplanuj", "paczka", "sprawdz", "do-odczytu",
                  "zapisz-wynik", "hamulec", "raport", "status")


def test_every_cycle_command_is_listed_in_the_help(capsys):
    cli.main([])
    out = capsys.readouterr().out
    for name in CYCLE_COMMANDS:
        assert name in out, name


@pytest.mark.parametrize("name", CYCLE_COMMANDS)
def test_every_cycle_command_has_its_own_help(name, capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main([name, "--help"])
    assert caught.value.code == 0 and name in capsys.readouterr().out


def test_commands_that_do_not_render_start_without_the_heavy_packages(tmp_path):
    shadow = tmp_path / "zepsute"
    shadow.mkdir()
    for name in ("av", "PIL", "numpy"):
        (shadow / (name + ".py")).write_text("raise ImportError('zepsuty pakiet')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONUTF8": "1", "TRIAL_REELS_ROOT": str(tmp_path / "klient"), "PYTHONPATH": str(shadow)}
    for argv in (("status",), ("do-odczytu",), ("raport",), ("podglad",), ("akceptuj", "--wszystkie"),
                 ("zaplanuj", "--na-sucho")):
        done = subprocess.run([sys.executable, "-m", "trial_reels", *argv], cwd=Path(__file__).resolve().parents[1],
                              env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        assert done.returncode == 0 and "Traceback" not in done.stderr, (argv, done.stderr)
