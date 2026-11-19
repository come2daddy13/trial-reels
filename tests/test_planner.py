"""Testy planera: godziny i terminy triali, wagi rolek, poziomy zmian, wybór hooka, hamulec i strefa czasowa."""
import inspect
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from trial_reels import config, planner

TZ = planner.TZ
POOL = [{"code": "R%02d" % i, "strong": "x" if i % 4 else None, "active": True} for i in range(12)]


@pytest.fixture(autouse=True)
def keep_planner_zone(monkeypatch):
    """Strefa ustawiona w teście przez set_tz nie przechodzi do następnych testów."""
    monkeypatch.setattr(planner, "TZ", planner.TZ)


def hhmm(times):
    return [t.strftime("%H:%M") for t in times]


def minutes(hours):
    return [int(h) * 60 + int(m) for h, m in (x.split(":") for x in hours)]


# --- godziny triali w ciągu dnia ---------------------------------------------

def test_slot_hours():
    assert planner.slot_hours(10) == ("09:00", "10:20", "11:40", "13:00", "14:20",
                                      "15:40", "17:00", "18:20", "19:40", "21:00")
    assert planner.slot_hours(5) == ("09:00", "12:00", "15:00", "18:00", "21:00")
    assert planner.slot_hours(1) == ("13:00",) and planner.slot_hours(0) == ()


def test_slot_hours_rounds_to_the_minute():
    assert planner.slot_hours(2) == ("09:00", "21:00")
    assert planner.slot_hours(6) == ("09:00", "11:24", "13:48", "16:12", "18:36", "21:00")
    assert planner.slot_hours(8) == ("09:00", "10:43", "12:26", "14:09", "15:51", "17:34", "19:17", "21:00")


def test_slot_hours_spacing_is_equal_up_to_one_minute():
    for n in range(2, 40):
        hours = planner.slot_hours(n)
        mins = minutes(hours)
        gaps = [b - a for a, b in zip(mins, mins[1:])]
        assert len(hours) == n and hours[0] == "09:00" and hours[-1] == "21:00", n
        assert min(gaps) > 0 and max(gaps) - min(gaps) <= 1, n


def test_slot_hours_custom_window_and_single_slot():
    assert planner.slot_hours(3, "08:00", "20:00") == ("08:00", "14:00", "20:00")
    assert planner.slot_hours(4, "09:15", "21:45") == ("09:15", "13:25", "17:35", "21:45")
    assert planner.slot_hours(1, single="16:45") == ("16:45",)
    assert planner.slot_hours(1, "08:00", "20:00") == ("13:00",)  # jeden trial idzie o `single`, nie o środku okna
    assert planner.slot_hours(-3) == ()


def test_slot_hours_never_repeats_a_minute_and_ignores_window_order():
    assert planner.slot_hours(30, "09:00", "09:10") == tuple("09:%02d" % m for m in range(11))
    assert planner.slot_hours(3, "21:00", "09:00") == ("09:00", "15:00", "21:00")


def test_planner_defaults_match_settings_defaults():
    d = config.DEFAULTS
    hours, times, daytime = (inspect.signature(f).parameters for f in
                             (planner.slot_hours, planner.slot_times, planner.is_daytime))
    assert (hours["start"].default, hours["end"].default) == tuple(d["hours"])
    assert hours["single"].default == times["brake_slot"].default == d["brake_slot"]
    assert daytime["window"].default == tuple(d["day_window"])


# --- ile triali dziennie -----------------------------------------------------

def test_daily_count_caps_at_active_reels():
    assert planner.daily_count([{"code": "A"}, {"code": "B", "active": False}, {"code": "C"}], 10) == 2


def test_daily_count_never_exceeds_daily_max_or_goes_below_zero():
    pool = [{"code": "R%02d" % i} for i in range(12)]
    assert planner.daily_count(pool, 10) == 10
    assert planner.daily_count(pool, 3) == 3
    assert planner.daily_count(pool, 0) == 0 and planner.daily_count(pool, -2) == 0
    assert planner.daily_count([], 10) == 0
    assert planner.daily_count([{"code": "A", "active": False}], 10) == 0


def test_suggest_daily():
    assert planner.suggest_daily(30, 10) == 10
    assert planner.suggest_daily(120, 10) == 6
    assert planner.suggest_daily(9999, 10) == 1


def test_suggest_daily_follows_budget_and_daily_max():
    assert planner.suggest_daily(120, 10, budget_min=45) == 3
    assert planner.suggest_daily(120, 10, budget_min=180) == 10  # budżet pozwala na 12, ale limit dzienny to 10
    assert planner.suggest_daily(30, 4) == 4
    assert planner.suggest_daily(60, 10, budget_min=42) == 6     # dokładnie 6, bez zaokrąglania w górę
    assert planner.suggest_daily(61, 10, budget_min=42) == 5


def test_suggest_daily_without_render_time_does_not_limit():
    assert planner.suggest_daily(0, 10) == 10
    assert planner.suggest_daily(0.0, 7) == 7


# --- terminy -----------------------------------------------------------------

def test_slots_ten_per_day_every_80_min_in_polish_time_with_lead():
    now = datetime(2026, 11, 9, 8, 50, tzinfo=TZ)
    slots = planner.slot_times(now, 1, planner.slot_hours(10))
    assert hhmm(slots) == ["10:20", "11:40", "13:00", "14:20", "15:40", "17:00", "18:20", "19:40", "21:00"]
    day = planner.slot_times(datetime(2026, 11, 9, 6, 0, tzinfo=TZ), 1, planner.slot_hours(10))
    assert len(day) == 10 and {"09:00", "13:00", "17:00"} <= set(hhmm(day))
    assert all(b - a == timedelta(minutes=80) for a, b in zip(day, day[1:]))


def test_brake_leaves_one_slot_per_day():
    now = datetime(2026, 11, 9, 6, 0, tzinfo=TZ)
    assert hhmm(planner.slot_times(now, 3, planner.slot_hours(10), brake=True)) == ["13:00"] * 3


def test_brake_slot_is_a_parameter():
    now = datetime(2026, 11, 9, 6, 0, tzinfo=TZ)
    assert hhmm(planner.slot_times(now, 2, planner.slot_hours(10), brake=True, brake_slot="15:30")) == ["15:30"] * 2


def test_slot_times_uses_given_hours_in_chronological_order_without_repeats():
    now = datetime(2026, 11, 9, 6, 0, tzinfo=TZ)
    slots = planner.slot_times(now, 1, ("18:45", "10:00", "12:30", "10:00"))
    assert hhmm(slots) == ["10:00", "12:30", "18:45"]
    assert all(t.tzinfo == TZ for t in slots)


def test_slot_times_accepts_any_iterable_of_hours():
    now = datetime(2026, 11, 9, 6, 0, tzinfo=TZ)
    slots = planner.slot_times(now, 2, iter(["10:00", "11:00"]))  # jednorazowy iterator starcza na wszystkie dni
    assert [planner.slot_str(t) for t in slots] == [
        "2026-11-09T10:00:00", "2026-11-09T11:00:00", "2026-11-10T10:00:00", "2026-11-10T11:00:00"]


def test_slot_times_without_hours_is_empty():
    assert planner.slot_times(datetime(2026, 11, 9, 6, 0, tzinfo=TZ), 7, ()) == []
    assert planner.slot_times(datetime(2026, 11, 9, 6, 0, tzinfo=TZ), 7, planner.slot_hours(0)) == []


def test_slots_keep_local_clock_time_across_daylight_saving_change():
    now = datetime(2026, 3, 27, 22, 0, tzinfo=TZ)  # zmiana czasu w nocy z 28 na 29 marca
    slots = planner.slot_times(now, 4, ("09:00", "21:00"))
    assert [planner.slot_str(t) for t in slots] == [
        "2026-03-28T09:00:00", "2026-03-28T21:00:00", "2026-03-29T09:00:00", "2026-03-29T21:00:00",
        "2026-03-30T09:00:00", "2026-03-30T21:00:00", "2026-03-31T09:00:00", "2026-03-31T21:00:00"]
    assert [t.utcoffset() for t in slots] == [timedelta(hours=1)] * 2 + [timedelta(hours=2)] * 6


def test_parse_slot_and_slot_str_roundtrip_in_planner_zone():
    t = planner.parse_slot("2026-11-09T09:00:00")
    assert t.tzinfo == TZ and planner.slot_str(t) == "2026-11-09T09:00:00"
    own_zone = planner.parse_slot("2026-11-09T08:00:00+00:00")  # termin z własną strefą zostaje, a zapis idzie w strefie planera
    assert own_zone.utcoffset() == timedelta(0) and planner.slot_str(own_zone) == "2026-11-09T09:00:00"
    assert planner.slot_str(datetime(2026, 11, 9, 9, 0, 45, tzinfo=TZ)) == "2026-11-09T09:00:00"  # sekundy zerujemy


def test_taken_slots_count_only_live_versions():
    assert planner.LIVE == ("do_akceptacji", "zaakceptowana", "zaplanowana", "opublikowana")
    vs = {
        "a": {"slot": "2026-11-10T09:00:00", "status": "zaplanowana"},
        "b": {"slot": "2026-11-10T10:20:00", "status": "odrzucona"},
        "c": {"slot": "2026-11-10T11:40:00", "status": "blad"},
        "d": {"slot": None, "status": "zaakceptowana"},
        "e": {"slot": "2026-11-10T13:00:00", "status": "do_akceptacji"},
    }
    assert planner.taken_slots(vs) == {"2026-11-10T09:00:00", "2026-11-10T13:00:00"}


# --- strefa czasowa ----------------------------------------------------------

def test_planner_starts_in_the_default_zone():
    assert planner.TZ.key == config.DEFAULTS["timezone"] == "Europe/Warsaw"


def test_set_tz_moves_parsing_formatting_slots_and_daytime_window():
    planner.set_tz("Asia/Tokyo")  # UTC+9, bez zmiany czasu
    assert planner.TZ == ZoneInfo("Asia/Tokyo")
    utc = datetime(2026, 11, 9, 0, 30, tzinfo=timezone.utc)  # 09:30 w Tokio, 01:30 w Warszawie
    assert planner.slot_str(utc) == "2026-11-09T09:30:00"
    assert planner.is_daytime(utc)
    assert planner.parse_slot("2026-11-09T09:00:00").utcoffset() == timedelta(hours=9)
    slots = planner.slot_times(utc, 1, ("12:00",))
    assert [planner.slot_str(t) for t in slots] == ["2026-11-09T12:00:00"]
    assert slots[0].utcoffset() == timedelta(hours=9)
    planner.set_tz("Europe/Warsaw")
    assert planner.TZ is TZ and not planner.is_daytime(utc)  # 01:30 w Warszawie to jeszcze noc


def test_set_tz_rejects_unknown_zone_and_keeps_the_old_one():
    before = planner.TZ
    with pytest.raises(ZoneInfoNotFoundError):
        planner.set_tz("Nie/Ma_Takiej_Strefy")
    assert planner.TZ is before


# --- okno publikacji ---------------------------------------------------------

def test_no_publishing_at_night_in_poland():
    day = lambda h, m: planner.is_daytime(datetime(2026, 11, 9, h, m, tzinfo=TZ))
    assert [day(3, 19), day(7, 14), day(7, 15), day(22, 0), day(22, 1)] == [False, False, True, True, False]
    slots = planner.slot_times(datetime(2026, 11, 9, 6, 0, tzinfo=TZ), 7, planner.slot_hours(10))
    assert slots and all(planner.is_daytime(t) for t in slots)


def test_is_daytime_takes_window_and_reads_the_clock_in_planner_zone():
    t = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)  # 09:00 w Warszawie
    assert planner.is_daytime(t)
    assert not planner.is_daytime(t, ("10:00", "20:00"))
    assert planner.is_daytime(t, ("09:00", "09:00"))  # kraniec okna wchodzi do okna
    assert not planner.is_daytime(datetime(2026, 11, 9, 22, 30, tzinfo=timezone.utc))  # 23:30 w Warszawie


# --- kolejka rolek -----------------------------------------------------------

def test_week_of_ten_a_day_spreads_reels_evenly_never_twice_a_day():
    now = datetime(2026, 11, 15, 18, 0, tzinfo=TZ)
    plan = planner.assign(planner.slot_times(now, 7, planner.slot_hours(10)), POOL, {}, now)
    assert len(plan) == 70
    counts = Counter(code for _, code in plan)
    assert set(counts) == {r["code"] for r in POOL}
    assert max(counts.values()) - min(counts.values()) <= 1
    per_day = Counter((t.date(), code) for t, code in plan)
    assert max(per_day.values()) == 1


def test_small_pool_never_repeats_a_reel_within_a_day():
    pool = POOL[:3]
    now = datetime(2026, 11, 9, 6, 0, tzinfo=TZ)
    plan = planner.assign(planner.slot_times(now, 1, planner.slot_hours(10)), pool, {}, now)
    assert len(plan) == 3  # 10 terminów, ale tylko 3 rolki, a rolka nie idzie dwa razy jednego dnia
    hours = planner.slot_hours(planner.daily_count(pool, 10))
    assert hours == ("09:00", "15:00", "21:00")
    plan = planner.assign(planner.slot_times(now, 3, hours), pool, {}, now)
    assert len(plan) == 9 and max(Counter((t.date(), c) for t, c in plan).values()) == 1


def test_assign_respects_versions_already_planned_that_day():
    now = datetime(2026, 11, 9, 6, 0, tzinfo=TZ)
    versions = {"v1": {"code": "R00", "slot": "2026-11-09T09:00:00", "status": "zaplanowana", "level": "subtelna"}}
    plan = planner.assign(planner.slot_times(now, 1, ("10:00", "11:00")), POOL[:2], versions, now)
    assert [(planner.slot_str(t), c) for t, c in plan] == [("2026-11-09T10:00:00", "R01")]


# --- wagi i pauzy ------------------------------------------------------------

def _measured(code, slot, views, follows, level="subtelna"):
    return {"code": code, "slot": slot, "views": views, "follows": follows, "status": "opublikowana", "level": level}


def test_three_zero_trials_pause_reel_for_two_weeks():
    vs = {"a%d" % i: _measured("R01", "2026-11-1%dT09:00:00" % i, 500, 0) for i in range(3)}
    until = planner.paused_until("R01", vs)
    assert until == planner.parse_slot("2026-11-12T09:00:00") + timedelta(days=14)
    w = planner.weights(POOL, vs, datetime(2026, 11, 15, tzinfo=TZ))
    assert w["R01"] == 0.0


def test_pause_ends_after_two_weeks():
    vs = {"a%d" % i: _measured("R01", "2026-11-1%dT09:00:00" % i, 500, 0) for i in range(3)}
    resume = planner.paused_until("R01", vs)
    assert planner.weights(POOL, vs, resume - timedelta(minutes=1))["R01"] == 0.0
    assert planner.weights(POOL, vs, resume + timedelta(minutes=1))["R01"] == 1.0


def test_no_pause_unless_the_last_three_measured_trials_all_got_zero():
    zeros = [_measured("R01", "2026-11-1%dT09:00:00" % i, 500, 0) for i in range(3)]
    assert planner.paused_until("R01", {"a": zeros[0], "b": zeros[1]}) is None  # tylko dwa triale
    gained = {"a": zeros[0], "b": zeros[1], "c": _measured("R01", "2026-11-12T09:00:00", 500, 1)}
    assert planner.paused_until("R01", gained) is None
    unmeasured = {"a": zeros[0], "b": zeros[1], "c": dict(zeros[2], follows=None)}
    assert planner.paused_until("R01", unmeasured) is None  # niezmierzony trial się nie liczy
    other = {"a": zeros[0], "b": zeros[1], "c": dict(zeros[2], code="R02")}
    assert planner.paused_until("R01", other) is None  # trial innej rolki też nie


def test_top_three_get_double_weight_bottom_three_half():
    vs = {}
    for i, r in enumerate(POOL[:8]):
        vs[r["code"]] = _measured(r["code"], "2026-11-10T09:00:00", 1000, 10 * (8 - i))
    w = planner.weights(POOL, vs, datetime(2026, 11, 15, tzinfo=TZ))
    assert [w["R00"], w["R01"], w["R02"]] == [2.0, 2.0, 2.0]
    assert [w["R05"], w["R06"], w["R07"]] == [0.5, 0.5, 0.5]
    assert w["R10"] == 1.0


def test_weights_stay_equal_with_fewer_than_six_measured_reels_and_skip_inactive():
    vs = {r["code"]: _measured(r["code"], "2026-11-10T09:00:00", 1000, 10 * (5 - i)) for i, r in enumerate(POOL[:5])}
    pool = [dict(POOL[0], active=False)] + POOL[1:]
    w = planner.weights(pool, vs, datetime(2026, 11, 15, tzinfo=TZ))
    assert "R00" not in w and set(w.values()) == {1.0}


def test_reel_stats_sum_measured_versions_and_per_1000():
    vs = {
        "a": _measured("R01", "2026-11-10T09:00:00", 1000, 3),
        "b": _measured("R01", "2026-11-11T09:00:00", 3000, 1),
        "c": dict(_measured("R01", "2026-11-12T09:00:00", 0, 0), views=None, follows=None, status="zaplanowana"),
    }
    stats = planner.reel_stats(vs)
    assert stats == {"R01": {"views": 4000, "follows": 4, "n": 2}}
    assert planner.per_1000(stats["R01"]) == 1.0
    assert planner.per_1000({"views": 0, "follows": 5, "n": 1}) == 0.0


# --- poziom zmian i hook -----------------------------------------------------

def test_level_mix_and_no_strong_without_phrase():
    vs, levels = {}, Counter()
    for i in range(100):
        reel = POOL[i % 12]
        lv = planner.pick_level(vs, reel)
        if not reel["strong"]:
            assert lv != "mocna"
        vs[str(i)] = {"code": reel["code"], "level": lv, "status": "zaplanowana"}
        levels[lv] += 1
    assert 45 <= levels["subtelna"] <= 55 and 25 <= levels["srednia"] <= 35 and 15 <= levels["mocna"] <= 25


def test_pick_level_counts_only_live_versions_and_extra_plans():
    reel = {"code": "R01", "strong": "x"}
    assert planner.pick_level({}, reel) == "subtelna"
    rejected = {"a": {"code": "R01", "level": "subtelna", "status": "odrzucona"}}
    assert planner.pick_level(rejected, reel) == "subtelna"  # odrzucona wersja nie liczy się do proporcji
    planned = {"a": {"code": "R01", "level": "subtelna", "status": "zaplanowana"}}
    assert planner.pick_level(planned, reel) == "srednia"
    assert planner.pick_level({}, reel, Counter(subtelna=5)) == "srednia"  # `extra` to wersje z tej samej paczki


def test_hook_unused_first_then_best_measured():
    bank = [{"id": "h01"}, {"id": "h02"}]
    vs = {"a": {"code": "R01", "hook_id": "h01", "status": "opublikowana", "views": 1000, "follows": 1}}
    assert planner.pick_hook("R01", bank, vs)["id"] == "h02"
    vs["b"] = {"code": "R01", "hook_id": "h02", "status": "opublikowana", "views": 1000, "follows": 9}
    assert planner.pick_hook("R01", bank, vs)["id"] == "h02"


def test_hook_falls_back_to_least_used_and_rejected_versions_do_not_use_up_a_hook():
    bank = [{"id": "h01"}, {"id": "h02"}]
    planned = {c: {"code": "R01", "hook_id": h, "status": "zaplanowana"} for c, h in (("a", "h01"), ("b", "h02"), ("c", "h02"))}
    assert planner.pick_hook("R01", bank, planned)["id"] == "h01"  # nic nie zmierzono, h01 użyty rzadziej
    rejected = {"a": {"code": "R01", "hook_id": "h01", "status": "odrzucona"}}
    assert planner.pick_hook("R01", bank, rejected)["id"] == "h01"


def test_bank_left_counts_hooks_never_used_by_the_reel():
    bank = [{"id": "h01"}, {"id": "h02"}, {"id": "h03"}]
    vs = {
        "a": {"code": "R01", "hook_id": "h01", "status": "zaplanowana"},
        "b": {"code": "R02", "hook_id": "h02", "status": "zaplanowana"},
        "c": {"code": "R01", "hook_id": "h01", "status": "odrzucona"},
    }
    assert planner.bank_left("R01", bank, vs) == 2
    assert planner.bank_left("R03", bank, vs) == 3


# --- hamulec -----------------------------------------------------------------

def _post(day, views):
    return {"publishedAt": "2026-%sT12:00:00Z" % day, "mediaType": "video", "isAd": False,
            "platformPostUrl": "https://www.instagram.com/reel/%s-%d/" % (day, views), "analytics": {"views": views}}


def test_brake_ignores_hidden_reels_and_waits_for_trials():
    first = datetime(2026, 11, 9, 9, 0, tzinfo=TZ)
    now = datetime(2026, 11, 20, 12, 0, tzinfo=TZ)
    base = [_post("10-%02d" % d, 10000) for d in range(15, 25)]
    hidden = [_post("11-%02d" % d, 130) for d in range(10, 16)]
    assert planner.MIN_VIEWS == 1000
    assert planner.brake_ratio(base + hidden, set(), now, None) is None
    assert planner.brake_ratio(base + hidden, set(), now, first) is None
    regular = [_post("11-%02d" % d, 6000) for d in (10, 12, 14, 16)]
    assert planner.brake_ratio(base + hidden + regular, set(), now, first) == 0.6


def test_brake_ignores_ads_trial_posts_and_other_media():
    first = datetime(2026, 11, 9, 9, 0, tzinfo=TZ)
    now = datetime(2026, 11, 20, 12, 0, tzinfo=TZ)
    base = [_post("10-%02d" % d, 10000) for d in range(15, 25)]
    days = ("11-10", "11-12", "11-14")
    regular = [_post(day, 6000) for day in days]
    ads = [dict(_post(day, 50000), isAd=True) for day in days]
    trials = [_post(day, 50001) for day in days]
    images = [dict(_post(day, 50002), mediaType="image") for day in days]
    urls = {p["platformPostUrl"] for p in trials}

    def ratio(extra, trial_urls=()):
        return planner.brake_ratio(base + regular + extra, set(trial_urls), now, first)

    assert ratio(ads + trials + images, urls) == 0.6
    assert ratio(ads) == 0.6 and ratio(trials, urls) == 0.6 and ratio(images) == 0.6
    # Kontrola: bez wykluczenia te same posty zmieniłyby wynik.
    assert ratio([dict(p, isAd=False) for p in ads]) > 1.0
    assert ratio(trials) > 1.0
    assert ratio([dict(p, mediaType="video") for p in images]) > 1.0


def test_brake_needs_enough_posts_before_and_after_the_first_trial():
    first = datetime(2026, 11, 9, 9, 0, tzinfo=TZ)
    now = datetime(2026, 11, 20, 12, 0, tzinfo=TZ)
    base = [_post("10-%02d" % d, 10000) for d in range(15, 25)]
    regular = [_post("11-%02d" % d, 6000) for d in (10, 12, 14, 16)]
    assert planner.brake_ratio(base[:4] + regular, set(), now, first) is None  # za mało rolek sprzed triali
    assert planner.brake_ratio(base + regular[:2], set(), now, first) is None  # za mało rolek po starcie triali


def _reel_post(day, views, kind="REELS"):
    """Post w kształcie, w jakim Zernio podaje typ rolki na żywo: mediaProductType, a mediaType może w ogóle nie przyjść."""
    post = _post(day, views)
    del post["mediaType"]
    post["mediaProductType"] = kind
    return post


def test_brake_recognizes_regular_reels_by_media_product_type_like_the_rest_of_the_program():
    """Reszta programu rozpoznaje rolki po mediaProductType. Gdyby hamulec patrzył tylko na mediaType, a Zernio go nie
    przysyłało, nie zadziałałby nigdy."""
    first = datetime(2026, 11, 9, 9, 0, tzinfo=TZ)
    now = datetime(2026, 11, 20, 12, 0, tzinfo=TZ)
    base = [_reel_post("10-%02d" % d, 10000) for d in range(15, 25)]
    regular = [_reel_post("11-%02d" % d, 6000) for d in (10, 12, 14, 16)]
    assert planner.brake_ratio(base + regular, set(), now, first) == 0.6
    feed_video = [dict(_reel_post(day, 50000), mediaProductType="FEED", mediaType="VIDEO") for day in ("11-10", "11-12", "11-14")]
    assert planner.brake_ratio(base + regular + feed_video, set(), now, first) == 0.6        # wideo z siatki to nie rolka
    both = [dict(_post(day, 6000), mediaProductType="REELS") for day in ("11-10", "11-12", "11-14")]
    assert planner.brake_ratio(base + both, set(), now, first) == 0.6                         # oba pola, jak w odpowiedzi z konta


def test_brake_thresholds_are_named_and_match_the_data_it_needs():
    assert (planner.BRAKE_MIN_BASE, planner.BRAKE_MIN_RECENT) == (5, 3)

