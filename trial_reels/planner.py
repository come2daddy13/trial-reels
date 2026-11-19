"""Rotacja trial reels (czyste funkcje, bez sieci): terminy, wagi rolek, poziom zmian, wybór hooka.

Zasady:
- Dziennie tyle triali, ile wynosi `daily_max`, ale nie więcej niż aktywnych rolek. Godziny rozkładamy równo
  w godzinach pracy. Nigdy dwie wersje tej samej rolki jednego dnia.
- 3 najlepsze rolki (obserwujący na 1000 wyświetleń) dostają wagę 2,0, a 3 najsłabsze 0,5 (gdy zmierzonych jest 6 lub więcej).
  3 triale z rzędu bez obserwującego to pauza rolki na 14 dni.
- Proporcje poziomów zmian: 50% subtelnych, 30% średnich, 20% mocnych.
- Hamulec: gdy zasięg zwykłych rolek spadnie o ponad 30%, idzie 1 trial dziennie.

Godziny i strefa przychodzą z ustawień klienta: godziny jako parametry funkcji, strefę ustawia `set_tz`.
Inne moduły czytają strefę zawsze przez `planner.TZ`, bo `set_tz` podmienia ją w locie.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

try:
    TZ = ZoneInfo(config.DEFAULTS["timezone"])
except config.ZONE_ERRORS:
    # Windows nie ma własnej bazy stref: bez działającego pakietu tzdata import nie może się wywrócić, bo wtedy doktor
    # nie powiedziałby, co jest zepsute. Do czasu `set_tz` liczymy w UTC, a doktor pokazuje problem (config.zone_problem).
    TZ = timezone.utc
LIVE = ("do_akceptacji", "zaakceptowana", "zaplanowana", "opublikowana")


def set_tz(name: str) -> None:
    """Ustawia strefę czasową planera (nazwa IANA, np. „Europe/Warsaw”). Nieznana nazwa zgłasza błąd i niczego nie zmienia."""
    global TZ
    TZ = ZoneInfo(name)


def _hm(hhmm: str) -> tuple[int, int]:
    """Godzina „HH:MM” jako (godziny, minuty)."""
    hours, minutes = hhmm.split(":")
    return int(hours), int(minutes)


def _minutes(hhmm: str) -> int:
    """Godzina „HH:MM” jako liczba minut od północy."""
    hours, minutes = _hm(hhmm)
    return hours * 60 + minutes


def parse_slot(s: str) -> datetime:
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=TZ)


def slot_str(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%Y-%m-%dT%H:%M:00")


def slot_hours(n: int, start: str = "09:00", end: str = "21:00", single: str = "13:00") -> tuple[str, ...]:
    """Godziny `n` triali w ciągu dnia: równe odstępy od `start` do `end`, zaokrąglone do minuty.

    Jeden trial idzie o `single`, a dla `n <= 0` nie ma godzin. Wynik jest rosnący i bez powtórzeń.
    """
    if n <= 0:
        return ()
    if n == 1:
        return (single,)
    first, span, steps = _minutes(start), _minutes(end) - _minutes(start), n - 1
    # Zaokrąglenie od połowy w górę liczone na liczbach całkowitych, więc bez błędów zmiennoprzecinkowych.
    found = {first + (2 * k * span + steps) // (2 * steps) for k in range(n)}
    return tuple("%02d:%02d" % divmod(m, 60) for m in sorted(found))


def daily_count(pool: list, daily_max: int) -> int:
    """Ile triali dziennie: `daily_max`, ale nie więcej niż aktywnych rolek w puli."""
    active = sum(1 for r in pool if r.get("active", True))
    return max(0, min(daily_max, active))


def suggest_daily(avg_render_s: float, daily_max: int, budget_min: int = 90) -> int:
    """Ile triali dziennie zmieści się w tygodniowym budżecie czasu na render (`budget_min` minut).

    Tydzień to 7 dni po tyle wersji, ile wyjdzie, a każda renderuje się średnio `avg_render_s` sekund.
    Wynik ma co najmniej 1 i najwyżej `daily_max`. Gdy czasu renderu nie znamy (0 lub mniej), czas
    niczego nie ogranicza i wychodzi `daily_max`.
    """
    if avg_render_s <= 0:
        return daily_max
    fits = int(budget_min * 60 // (7 * avg_render_s))
    return min(daily_max, max(1, fits))


def is_daytime(t: datetime, window: tuple = ("07:15", "22:00")) -> bool:
    """Publikujemy tylko w ciągu dnia: godzina `t` w strefie planera mieści się w `window` (z krańcami), także testy."""
    start, end = (_minutes(x) for x in window)
    local = t.astimezone(TZ)
    return start <= local.hour * 60 + local.minute <= end


def slot_times(now: datetime, days: int, hours, brake: bool = False, brake_slot: str = "13:00") -> list[datetime]:
    """Terminy od `now` (z zapasem) do `now + days`, w strefie planera, od najwcześniejszego.

    `hours` to godziny „HH:MM” w ciągu dnia, zwykle z `slot_hours`. Przy `brake` zostaje tylko `brake_slot`.
    """
    now = now.astimezone(TZ)
    day_times = sorted({_hm(h) for h in ((brake_slot,) if brake else hours)})
    out = []
    for d in range(days + 1):
        day = now.date() + timedelta(days=d)
        for h, m in day_times:
            t = datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)
            if now + timedelta(minutes=config.MIN_LEAD_MIN) <= t < now + timedelta(days=days):
                out.append(t)
    return out


def taken_slots(versions: dict) -> set:
    return {v["slot"] for v in versions.values() if v.get("slot") and v.get("status") in LIVE}


def reel_stats(versions: dict) -> dict:
    st = {}
    for v in versions.values():
        if v.get("views") is None or v.get("follows") is None:
            continue
        s = st.setdefault(v["code"], {"views": 0, "follows": 0, "n": 0})
        s["views"] += v["views"]
        s["follows"] += v["follows"]
        s["n"] += 1
    return st


def per_1000(s: dict) -> float:
    return 1000.0 * s["follows"] / s["views"] if s.get("views") else 0.0


def paused_until(code: str, versions: dict):
    measured = sorted((v for v in versions.values() if v["code"] == code and v.get("follows") is not None
                       and v.get("slot")), key=lambda v: v["slot"])
    last3 = measured[-3:]
    if len(last3) == 3 and all(v["follows"] == 0 for v in last3):
        return parse_slot(last3[-1]["slot"]) + timedelta(days=14)
    return None


def weights(pool: list, versions: dict, now: datetime) -> dict:
    active = [r["code"] for r in pool if r.get("active", True)]
    w = {c: 1.0 for c in active}
    stats = reel_stats(versions)
    measured = [c for c in active if stats.get(c, {}).get("n")]
    if len(measured) >= 6:
        ranked = sorted(measured, key=lambda c: per_1000(stats[c]), reverse=True)
        top, bottom = ranked[:3], ranked[-3:]
        for c in top:
            w[c] = 2.0
        for c in bottom:
            if c not in top:
                w[c] = 0.5
    for c in active:
        until = paused_until(c, versions)
        if until and until > now:
            w[c] = 0.0
    return w


def assign(slots: list, pool: list, versions: dict, now: datetime) -> list:
    """Kolejka ważona (deficyt): każda rolka zbiera kredyt = waga, wybrana oddaje sumę wag."""
    w = weights(pool, versions, now)
    order = [r["code"] for r in pool]
    total = sum(w.values()) or 1.0
    per_day = {}
    recent = Counter()
    for v in versions.values():
        if v.get("slot") and v.get("status") in LIVE:
            t = parse_slot(v["slot"])
            per_day.setdefault(t.date(), set()).add(v["code"])
            if now - timedelta(days=14) <= t:
                recent[v["code"]] += 1
    avg = total / max(1, len([c for c in w if w[c] > 0]))
    credit = {c: -recent[c] * avg for c in w}
    plan = []
    for t in slots:
        day = t.date()
        cand = [c for c in w if w[c] > 0 and c not in per_day.get(day, set())]
        if not cand:
            continue
        for c in w:
            credit[c] += w[c]
        prev = per_day.get(day - timedelta(days=1), set())
        best = max(cand, key=lambda c: (credit[c] - (0.5 * w[c] if c in prev else 0.0), -order.index(c)))
        credit[best] -= total
        per_day.setdefault(day, set()).add(best)
        plan.append((t, best))
    return plan


def pick_level(versions: dict, reel: dict, extra: Counter = None) -> str:
    counts = Counter(v["level"] for v in versions.values() if v.get("status") in LIVE)
    if extra:
        counts.update(extra)
    n = sum(counts.values()) + 1
    options = [lv for lv in config.LEVELS if lv != "mocna" or reel.get("strong")]
    return max(options, key=lambda lv: (config.LEVEL_MIX[lv] * n - counts[lv], config.LEVEL_MIX[lv]))


def pick_hook(code: str, bank: list, versions: dict) -> dict:
    """Najpierw nieużyty hook z banku; potem najlepszy zmierzony; na końcu najrzadziej użyty."""
    mine = [v for v in versions.values() if v["code"] == code and v.get("status") != "odrzucona"]
    used = Counter(v.get("hook_id") for v in mine)
    for h in bank:
        if not used[h["id"]]:
            return h
    scores = {}
    for v in mine:
        if v.get("views"):
            s = scores.setdefault(v["hook_id"], [0, 0])
            s[0] += v.get("follows") or 0
            s[1] += v["views"]
    if scores:
        best = max(scores, key=lambda k: scores[k][0] / max(scores[k][1], 1))
        for h in bank:
            if h["id"] == best:
                return h
    return min(bank, key=lambda h: used[h["id"]])


def bank_left(code: str, bank: list, versions: dict) -> int:
    used = {v.get("hook_id") for v in versions.values() if v["code"] == code}
    return sum(1 for h in bank if h["id"] not in used)


MIN_VIEWS = 1000  # niżej są ukryte rolki (reklamy, testy) z ok. 100–300 wyświetleń, a nie zasięg u obserwujących
BRAKE_MIN_BASE = 5     # tyle zwykłych rolek musi być w 28 dniach przed pierwszym trialem, żeby policzyć wskaźnik
BRAKE_MIN_RECENT = 3   # i tyle w ostatnich dwóch tygodniach (od startu triali)


def is_regular_reel(post: dict) -> bool:
    """Czy post to rolka. Zernio podaje to w `mediaProductType` (REELS), tak jak czyta go reszta programu, a gdy go
    nie ma, w `mediaType` (wideo albo rolka). Wideo z siatki (`mediaProductType` inny niż REELS) to nie rolka."""
    kind = str(post.get("mediaProductType") or "").upper()
    if kind:
        return kind == "REELS"
    return str(post.get("mediaType") or "").lower() in ("video", "reel", "reels")


def brake_ratio(posts: list, trial_urls: set, now: datetime, first_trial):
    """Mediana wyświetleń zwykłych rolek od startu triali (ostatnie 14 dni, min. 2 dni po publikacji)
    / mediana z 28 dni przed pierwszym trialem. None = triale jeszcze nie ruszyły albo za mało danych
    (mniej niż `BRAKE_MIN_BASE` rolek przed trialami albo mniej niż `BRAKE_MIN_RECENT` po ich starcie)."""
    if first_trial is None:
        return None
    recent, base = [], []
    for p in posts:
        if p.get("isAd") or p.get("platformPostUrl") in trial_urls or not p.get("publishedAt"):
            continue
        if not is_regular_reel(p):
            continue
        views = ((p.get("analytics") or {}).get("views")) or 0
        if views < MIN_VIEWS:
            continue
        t = datetime.fromisoformat(p["publishedAt"].replace("Z", "+00:00"))
        age = (now - t).days
        if t >= first_trial and 2 <= age < 16:
            recent.append(views)
        elif first_trial - timedelta(days=28) <= t < first_trial:
            base.append(views)
    if len(recent) < BRAKE_MIN_RECENT or len(base) < BRAKE_MIN_BASE:
        return None
    return statistics.median(recent) / statistics.median(base)
