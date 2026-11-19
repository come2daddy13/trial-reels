"""Wersje triali: tworzenie, planowanie w Zernio, sprawdzanie publikacji, hamulec, sprzątanie i raport.

Wersja to jedna rolka z drobnymi zmianami (hook tekstowy, emotka, montaż, inny podpis) w jednym terminie. Wersje leżą
w `dane/stan.json` (patrz `state`) i przechodzą przez statusy:

    do_akceptacji -> zaakceptowana -> zaplanowana -> opublikowana        (poza obiegiem: odrzucona, blad)

Zasady, których pilnuje ten moduł:
- terminy rozkłada `planner` z ustawień klienta, żadna rolka nie idzie dwa razy jednego dnia, a poza oknem
  publikacji (domyślnie 07:15–22:00) nic nie jest planowane;
- trial idzie do Zernio z `graduationStrategy = MANUAL`: do obserwujących puszcza go klient, ręcznie;
- stan zapisuje się po każdej wersji, więc przerwane polecenie można uruchomić jeszcze raz: zajęte terminy są
  pomijane, a wersja bez posta w Zernio zostaje dokończona, a nie zrobiona od nowa.

Ciężki `render` (PIL, PyAV) ładuje się dopiero w funkcjach, które renderują, więc moduł startuje od razu.
"""
from __future__ import annotations

import re
import socket
import ssl
import subprocess
import time
import urllib.error
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import candidates, captions, config, planner, state, zernio

KEEP_DAYS = 14                # po tylu dniach od publikacji kasujemy plik wersji (film zostaje w Zernio i na Instagramie)
UPLOAD_MAX_AGE_DAYS = 6       # plik wysłany do Zernio leży tam w `temp/` 7 dni, więc starszy wysyłamy od nowa
MAX_FAILS_IN_A_ROW = 3        # tyle wersji z rzędu może się nie udać, zanim przerwiemy polecenie
SLOT_SEARCH_DAYS = 21         # tak daleko szukamy wolnego terminu, gdy termin wersji minął
PLAN_DAYS_FIRST = 7           # pierwsze wersje biorą najbliższe terminy z tylu dni
BUDGET_MIN = 90               # tyle minut tygodniowo może zająć render (patrz `planner.suggest_daily`)
HOOK_BANK_LOW = 3             # poniżej tylu nieużytych hooków mówimy, że bank prawie się skończył

clock = time.monotonic        # zegar do mierzenia renderu (testy go podmieniają)


def say(*parts) -> None:
    print(*parts, flush=True)


def _dec(x: float, spec: str = "%.1f") -> str:
    """Liczba z przecinkiem dziesiętnym, po polsku."""
    return (spec % x).replace(".", ",")


def now() -> datetime:
    """Teraz w strefie klienta (testy podmieniają tę funkcję)."""
    return datetime.now(planner.TZ)


# --- ustawienia ------------------------------------------------------------------

_HHMM = re.compile(r"(\d{1,2}):(\d{2})")


def _minutes(name: str, value) -> int:
    match = _HHMM.fullmatch(value.strip()) if isinstance(value, str) else None
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise config.UserError("Ustawienie %s w dane/config.json ma zły format: %s. Wpisz godzinę w formie 09:00."
                               % (name, config.line(repr(value))))
    return int(match.group(1)) * 60 + int(match.group(2))


def _range(name: str, value) -> tuple:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise config.UserError("Ustawienie %s w dane/config.json ma mieć dwie godziny, na przykład [\"09:00\", "
                               "\"21:00\"]. Jest: %s." % (name, config.line(repr(value))))
    first, last = (_minutes(name, x) for x in value)
    if first >= last:
        raise config.UserError("Ustawienie %s w dane/config.json: pierwsza godzina (%s) ma być wcześniejsza niż druga "
                               "(%s)." % (name, value[0], value[1]))
    return tuple(x.strip() for x in value)


def schedule_settings() -> dict:
    """Ustawienia terminów z dane/config.json, sprawdzone. Zły zapis to `UserError` z nazwą ustawienia."""
    s = config.settings()
    daily_max = s["daily_max"]
    if isinstance(daily_max, bool) or not isinstance(daily_max, int) or daily_max < 1:
        raise config.UserError("Ustawienie daily_max w dane/config.json ma być liczbą całkowitą od 1 (na przykład 10). "
                               "Jest: %s." % config.line(repr(daily_max)))
    brake_slot = _minutes("brake_slot", s["brake_slot"])
    day_window, hours_range = _range("day_window", s["day_window"]), _range("hours", s["hours"])
    first, last = (_minutes("day_window", x) for x in day_window)
    for name, value in (("hours", hours_range[0]), ("hours", hours_range[1]), ("brake_slot", s["brake_slot"])):
        if not first <= _minutes(name, value) <= last:  # poza oknem nic by nie wyszło, a wersje czekałyby bez końca
            raise config.UserError("Ustawienie %s w dane/config.json (%s) wychodzi poza okno publikacji %s–%s "
                                   "(ustawienie day_window). Zmień godzinę albo okno."
                                   % (name, value.strip(), day_window[0], day_window[1]))
    return {"timezone": s["timezone"], "day_window": day_window, "hours": hours_range, "daily_max": daily_max,
            "brake_slot": s["brake_slot"].strip(), "ig_account_id": s.get("ig_account_id")}


def account_id() -> str:
    """ID konta Instagrama zapisane komendą `konto`. Bez niego nie wiadomo, na które konto planować."""
    found = config.settings().get("ig_account_id")
    if not found:
        raise config.UserError("Najpierw krok 3: konto Instagram. Uruchom komendę konto.")
    return str(found)


# --- pula i godziny --------------------------------------------------------------

def pool_list() -> list:
    """Pula rolek (także wyłączone). Wpis bez poprawnego kodu (`candidates.valid_code`: co najmniej 6 liter, cyfr, „-”
    albo „_”, bo kod trafia do nazw plików) pomijamy tak samo jak kreator i `active_reels`: zgłasza go `sprawdz-pule`."""
    return [r for r in candidates.load_pool() if isinstance(r, dict) and candidates.valid_code(r.get("code"))]


def pool() -> dict:
    return {r["code"]: r for r in pool_list()}


def hooks() -> dict:
    """Banki hooków {kod rolki: [hooki]}."""
    return {code: bank for code, bank in candidates.load_hooks().items() if code != "_zasady"}


def reel_name(reels: dict, code) -> str:
    """Nazwa rolki z puli, a gdy rolki już w niej nie ma, jej kod."""
    return str((reels.get(code) or {}).get("name") or code)


def reel_of(code: str) -> dict:
    reel = pool().get(code)
    if reel is None:
        raise config.UserError("Rolki %s nie ma w puli. Dodaj ją komendą pula albo zrezygnuj z jej wersji." % code)
    return reel


NO_HOOKS = "nie ma hooków w dane/hooki.json (dopisz co najmniej %d)" % candidates.MIN_HOOKS


def _has_hooks(bank: dict, code: str) -> bool:
    mine = bank.get(code)
    return isinstance(mine, list) and bool(mine)


def _hooks_of(bank: dict, code: str) -> list:
    """Hooki rolki, które mają `id` (pozostałe i tak nie przejdą sprawdzenia planu). Pusta lista, gdy rolka ich nie ma."""
    mine = bank.get(code)
    return [h for h in mine if isinstance(h, dict) and h.get("id")] if isinstance(mine, list) else []


def _title(reel: dict) -> str:
    """„NAZWA (KOD)” albo samo KOD, gdy rolka nie ma osobnej nazwy."""
    name, code = reel.get("name"), reel["code"]
    return "%s (%s)" % (name, code) if name and name != code else code


def reels_without_hooks() -> list:
    """Aktywne rolki puli, które nie mają w dane/hooki.json ani jednego hooka (nazwy w formie „NAZWA (KOD)”).

    Plan wersji ich nie bierze (patrz `reel_problems`). To lekka kontrola dla kreatora: nie ładuje PIL ani PyAV.
    """
    bank = hooks()
    return [_title(r) for r in pool_list() if r.get("active", True) and not _has_hooks(bank, r["code"])]


def reel_problems() -> dict:
    """{kod: powód} dla aktywnych rolek, z których plan nie zrobi teraz wersji.

    Powodem jest brak hooków albo hooki, podpisy i wpisy `blur`, które psułyby wersje: limity z `sprawdz-pule` (hook do
    50 znaków, emotka z paczki, podpis do 2200 znaków, blur z samych liczb w kadrze). Plików i transkrypcji nie
    sprawdza: render zgłasza je wersja po wersji.
    """
    bank, found, emoji_ok = hooks(), {}, None
    for reel in pool_list():
        code = reel["code"]
        if not reel.get("active", True):
            continue
        if not _has_hooks(bank, code):
            found[code] = NO_HOOKS
            continue
        if emoji_ok is None:
            from . import render  # PIL i PyAV ładują się dopiero tu

            emoji_ok = set(render.emoji_set())
        problems = candidates.plan_problems(reel, bank, emoji_ok)
        if problems:
            prefix = candidates.reel_label(reel) + ": "
            first = (problems[0][len(prefix):] if problems[0].startswith(prefix) else problems[0]).rstrip(".")
            found[code] = first + (" (to nie wszystko: sprawdz-pule pokaże resztę)" if len(problems) > 1 else "")
    return found


def hours() -> tuple:
    """Godziny triali w ciągu dnia: tyle, ile wynosi dzienna liczba triali (nie więcej niż aktywnych rolek)."""
    s = schedule_settings()
    count = planner.daily_count(pool_list(), s["daily_max"])
    return planner.slot_hours(count, s["hours"][0], s["hours"][1], s["brake_slot"])


def slot_label(slot) -> str:
    """Termin jako „2026-11-22 09:00” (czas z ustawień klienta); brak terminu daje „-”."""
    text = planner.slot_str(slot) if isinstance(slot, datetime) else str(slot or "")
    return text[:16].replace("T", " ") if text else "-"


def id_number(v: dict) -> int:
    """Numer z ID wersji (TR-012 daje 12), do sortowania. Po 999 wersjach „TR-1000” nadal idzie za „TR-999”."""
    digits = re.sub(r"\D", "", str(v.get("id", "")))
    return int(digits) if digits else 0


def by_slot(v: dict) -> tuple:
    return v.get("slot") or "", id_number(v)


# --- tworzenie i render ----------------------------------------------------------

def new_version(st: dict, code: str, level: str, hook: dict, slot, status: str) -> dict:
    """Nowa wersja rolki `code` z danym hookiem, terminem i statusem. Wpisuje ją do `st` (zapis robi wywołujący)."""
    from . import render  # PIL i PyAV ładują się dopiero tu

    reel = reel_of(code)
    if isinstance(slot, datetime):
        slot = planner.slot_str(slot)
    vid = state.next_id(st)
    nth = sum(1 for v in st["versions"].values() if v["code"] == code)
    reused = any(v["code"] == code and v.get("hook_id") == hook["id"] for v in st["versions"].values())
    emoji = hook.get("emoji")
    if reused:  # ten sam hook drugi raz dostaje inną emotkę
        emoji = render.ALT_EMOJI[int(vid[3:]) % len(render.ALT_EMOJI)]
    v = {"id": vid, "code": code, "level": level, "hook_id": hook["id"], "hook": hook["text"], "emoji": emoji,
         "slot": slot, "status": status, "caption": captions.compose(reel, nth),
         "created": now().isoformat(timespec="seconds"), "params": render.params_for(vid, level, reel)}
    st["versions"][vid] = v
    return v


def video_file(v: dict) -> Path:
    """Plik filmu wersji: zawsze dane/wersje/<ID>.mp4.

    Pole `file` w stanie tylko opisuje render. Ścieżka w nim bywa stara (folder przeniesiono) albo zmieniona w pliku,
    więc do wysyłki jej nie bierzemy: do Zernio nie może trafić żaden plik spoza folderu wersji. Zły numer wersji albo
    plik, który po rozwinięciu dowiązań leży poza dane/wersje, to `UserError`.
    """
    path = config.OUT / ("%s.mp4" % config.checked_version_id(v.get("id")))
    if (path.exists() or path.is_symlink()) and not config.within(path, config.OUT):
        raise config.UserError("Plik %s wskazuje poza folder dane/wersje, więc go nie wysyłam. Usuń go i uruchom komendę "
                               "jeszcze raz: wersja wyrenderuje się od nowa." % path.name)
    return path


def produce(st: dict, v: dict, upload: bool) -> None:
    """Renderuje wersję, zapisuje czas renderu (`render_s`) i stan, a przy `upload` wysyła film do Zernio."""
    from . import render

    reel = reel_of(v["code"])
    started = clock()
    render.render(v, reel)
    v["render_s"] = round(clock() - started, 1)
    state.save(st)
    if upload:
        v["media_url"] = zernio.upload(str(video_file(v)))
        v["uploaded_at"] = now().isoformat(timespec="seconds")
        state.save(st)
    say("  %s %s | %s | %s | %s | %.1f s" % (v["id"], slot_label(v.get("slot")), reel.get("name") or v["code"],
                                             config.LEVEL_LABEL.get(v["level"], v["level"]),
                                             " ".join(x for x in (v["hook"], v.get("emoji")) if x),
                                             v.get("duration") or 0))


# --- planowanie w Zernio ---------------------------------------------------------

def free_slot(st: dict, v: dict, t_now: datetime):
    """Najbliższy wolny termin dla wersji `v`: nie zajęty i bez tej samej rolki tego dnia. None, gdy nie ma."""
    s = schedule_settings()
    taken = planner.taken_slots(st["versions"])
    days = {}
    for x in st["versions"].values():
        if x.get("slot") and x.get("status") in planner.LIVE and x["id"] != v["id"]:
            days.setdefault(planner.parse_slot(x["slot"]).date(), set()).add(x["code"])
    brake = bool(st.get("brake", {}).get("on", False))
    for t in planner.slot_times(t_now, SLOT_SEARCH_DAYS, hours(), brake, s["brake_slot"]):
        if planner.slot_str(t) not in taken and v["code"] not in days.get(t.date(), set()):
            return t
    return None


def _needs_upload(v: dict, t_now: datetime) -> bool:
    """Czy film trzeba (znowu) wysłać do Zernio: nie było wysyłki albo plik w `temp/` ma ponad 6 dni."""
    uploaded = v.get("uploaded_at")
    if not v.get("media_url") or not uploaded:
        return True
    try:
        when = datetime.fromisoformat(uploaded)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=planner.TZ)
    return t_now - when > timedelta(days=UPLOAD_MAX_AGE_DAYS)


def clash_hint(ids) -> str:
    """Wskazówka dla klienta, gdy wersje `ids` pominięto, bo w Zernio jest już post IG na ich termin.

    Wersja zachowuje swój termin także po zmianie godzin w ustawieniach, więc samo przesunięcie godzin jej nie
    uwolni: pominiętą wersję trzeba odrzucić i zrobić nową, już na nowych godzinach. Bez `ids` (plan na sucho: wersji
    jeszcze nie ma) nie ma czego odrzucać, więc wskazówka kończy się na przesunięciu godzin i ponownym planie.
    """
    if not ids:
        return ("Jeśli o tych godzinach publikujesz coś innego, przesuń godziny triali w ustawieniach (pole hours w "
                "dane/config.json, np. na 09:05–21:05) i uruchom plan na sucho jeszcze raz.")
    return ("Jeśli o tych godzinach publikujesz coś innego, przesuń godziny triali w ustawieniach (pole hours w "
            "dane/config.json, np. na 09:05–21:05), odrzuć pominięte wersje (odrzuc %s) i zrób nowe komendą "
            "pierwsze albo paczka." % " ".join(ids))


def schedule_one(st: dict, v: dict, dry_run: bool, clashes: list | None = None) -> bool:
    """Planuje wersję w Zernio jako trial (MANUAL). True, gdy wersja jest (albo przy `dry_run` byłaby) zaplanowana.

    Termin wersji, który minął albo jest za blisko, zamieniamy na najbliższy wolny. Nic nie idzie poza oknem
    publikacji klienta, a w Zernio nie może już być posta IG na tę samą minutę. Przy `dry_run` pokazujemy termin
    i początek podpisu, ale nie wysyłamy niczego i niczego nie zapisujemy. Wybrany termin wpisujemy tylko do
    przekazanej wersji w pamięci, żeby kolejne wersje serii (i plan nowych wersji w `paczka --na-sucho`) widziały go
    jako zajęty, tak jak w prawdziwym przebiegu: wywołujący trzyma stan tylko w pamięci i go nie zapisuje.

    Wersję pominiętą przez cudzy post `schedule_one` opisuje jedną linią. Gdy wywołujący zbiera pominięte wersje
    w liście `clashes` (np. przy planowaniu serii), linie są krótkie, a wskazówkę (`clash_hint`) raz, z numerami
    wszystkich pominiętych wersji, wypisuje podsumowanie serii. Bez listy wskazówka idzie w tej samej linii.
    """
    if v.get("zernio_post_id"):
        say("  %s już ma post w Zernio (%s)" % (v["id"], v["zernio_post_id"]))
        return False
    s = schedule_settings()
    t_now = now()
    before = v.get("slot")
    when = planner.parse_slot(before) if before else None
    if not when or when < t_now + timedelta(minutes=config.MIN_LEAD_MIN):
        when = free_slot(st, v, t_now)
    if not when:
        say("  ! %s: nie ma wolnego terminu w najbliższych tygodniach" % v["id"])
        return False
    if not planner.is_daytime(when, s["day_window"]):
        say("  ! %s: termin %s jest poza oknem publikacji %s–%s (czas %s), więc nie publikuję"
            % (v["id"], slot_label(when), s["day_window"][0], s["day_window"][1], s["timezone"]))
        return False
    account = account_id()
    if zernio.ig_post_at(account, when):
        own_hint = clashes is None                    # nikt nie zbiera pominięć, więc nikt nie powtórzy wskazówki na końcu
        if clashes is not None:
            clashes.append(v["id"])
        say("  ! %s: na %s masz już inny post na Instagramie. Pomijam tę wersję.%s"
            % (v["id"], slot_label(when), " " + clash_hint([v["id"]]) if own_hint else ""))
        return False
    if when < now() + timedelta(minutes=2):
        say("  ! %s: termin %s jest zbyt blisko, pomijam" % (v["id"], slot_label(when)))
        return False
    if dry_run:
        moved = " (zamiast %s, bo ten termin minął albo jest za blisko)" % slot_label(before) \
            if before and planner.slot_str(when) != before else ""
        say("  %s: zaplanowałbym na %s%s. Podpis: %s" % (v["id"], slot_label(when), moved,
                                                         config.line(v.get("caption") or "")[:60]))
        v["slot"] = planner.slot_str(when)       # tylko w pamięci: następna wersja serii ma ten termin już zajęty
        return True
    if _needs_upload(v, t_now):  # plik w `temp/` Zernio żyje 7 dni, stary wysyłam od nowa
        v["media_url"] = zernio.upload(str(video_file(v)))
        v["uploaded_at"] = now().isoformat(timespec="seconds")
    payload = zernio.trial_payload(account, s["timezone"], v["caption"], v["media_url"], planner.slot_str(when),
                                   v["params"]["thumb_ms"])
    post = zernio.create_post(payload)
    post_id = post.get("_id") or post.get("id")
    if not post_id:
        raise zernio.ZernioError("Zernio nie podało numeru posta, więc nie wiem, czy wersja %s jest zaplanowana. "
                                 "Sprawdź panel Zernio i uruchom komendę jeszcze raz." % v["id"])
    v["zernio_post_id"] = post_id
    items = post.get("mediaItems") or []
    if items and items[0].get("url"):
        v["media_url"] = items[0]["url"]  # stały adres po utworzeniu posta
    v["slot"] = planner.slot_str(when)
    v["status"] = "zaplanowana"
    state.save(st)
    say("  %s zaplanowana w Zernio na %s (czas %s)" % (v["id"], slot_label(when), s["timezone"]))
    return True


# --- błędy pojedynczych wersji ---------------------------------------------------

def is_systemic(e: BaseException) -> bool:
    """Błąd, po którym następne wersje padłyby tak samo: zły albo brak klucza, płatność, limit, awaria, brak internetu."""
    if isinstance(e, zernio.ZernioError):
        if e.status is None:
            return getattr(e, "key", False) or "brak klucza" in str(e)
        return e.status in (401, 402, 403, 429) or e.status >= 500
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (401, 403)
    return isinstance(e, (urllib.error.URLError, ConnectionError, TimeoutError, socket.gaierror, ssl.SSLError))


def _shown(path) -> str:
    """Ścieżka do pokazania klientowi: względem jego folderu (dane/src/KOD.mp4), z ukośnikami jak w poleceniach."""
    try:
        return Path(path).resolve().relative_to(config.ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def describe_problem(e: BaseException) -> str:
    """Jedna linia o tym, dlaczego wersja się nie udała (trafia do uwag wersji i do raportu)."""
    text = config.line(e)
    if isinstance(e, config.UserError):
        return text
    if isinstance(e, subprocess.CalledProcessError):
        return "ffmpeg zgłosił błąd przy renderze (jego komunikat jest wyżej). Sprawdź plik źródłowy rolki."
    if isinstance(e, FileNotFoundError):
        return ("Nie ma pliku %s. Uruchom komendę pobierz albo wrzuć oryginał do dane/src." % _shown(e.filename)
                if e.filename else text)
    if isinstance(e, ValueError) and text.startswith("nie ma frazy"):
        return "%s. Sprawdź pola strong i cuts rolki komendą sprawdz-pule." % text
    if isinstance(e, zernio.ZernioError):
        return "Zernio: %s" % text[:300]
    return ("%s: %s" % (type(e).__name__, text) if text else type(e).__name__)[:500]


class _Loop:
    """Pętla po wersjach: błąd jednej oznacza ją jako `blad` i idzie dalej, błąd systemowy przerywa od razu
    (wersja zostaje, jaka była, więc następne uruchomienie ją dokończy), a kilka błędów z rzędu też przerywa."""

    def __init__(self, st: dict):
        self.st, self.failed, self.streak = st, [], 0

    def attempt(self, v: dict, action):
        try:
            result = action()
        except Exception as e:
            if is_systemic(e):
                raise
            v["status"] = "blad"
            v["note"] = describe_problem(e)
            state.save(self.st)
            say("  ! %s: %s" % (v["id"], v["note"]))
            self.failed.append(v["id"])
            self.streak += 1
            if self.streak >= MAX_FAILS_IN_A_ROW:
                raise config.UserError(
                    "Przerywam, bo %d kolejne wersje się nie udały. Ostatni błąd: %s. Napraw przyczynę i uruchom "
                    "komendę jeszcze raz: zajęte terminy zostaną pominięte." % (self.streak, v["note"].rstrip("."))) from None
            return False
        self.streak = 0
        return result


def _mark_replaced(st: dict, slot: str, new_id: str) -> None:
    """Wersje z błędem, które miały ten termin, dostają `replaced_by`: błąd jest już rozwiązany."""
    changed = False
    for old in st["versions"].values():
        if old.get("status") == "blad" and old.get("slot") == slot and old["id"] != new_id and not old.get("replaced_by"):
            old["replaced_by"] = new_id
            changed = True
    if changed:
        state.save(st)


def open_errors(st: dict) -> list:
    """Wersje z błędem, które nie mają jeszcze zastępstwa w tym samym terminie (to o nich mówimy klientowi)."""
    return [v for v in sorted(st["versions"].values(), key=id_number)
            if v.get("status") == "blad" and not v.get("replaced_by")]


def make_versions(st: dict, rows: list, status: str, upload: bool) -> dict:
    """Robi wersje z planu `rows` (krotki z `plan_rows`): render, a przy `upload` wysyłka i planowanie w Zernio.

    Zwraca {"done", "failed", "skipped", "clashes"} (listy ID). Pominięta wersja (np. za blisko albo poza oknem
    publikacji) zostaje zaakceptowana, a następne uruchomienie spróbuje ją dokończyć. `clashes` to pominięte
    wersje, których termin zajmuje już inny post IG w Zernio: te czekają na odrzucenie i nową wersję (`clash_hint`).
    """
    loop = _Loop(st)
    out = {"done": [], "failed": loop.failed, "skipped": [], "clashes": []}
    for t, code, level, hook in rows:
        v = new_version(st, code, level, hook, planner.slot_str(t), status)

        def work(v=v):
            produce(st, v, upload)
            return schedule_one(st, v, False, out["clashes"]) if upload else True

        if loop.attempt(v, work):
            out["done"].append(v["id"])
            _mark_replaced(st, planner.slot_str(t), v["id"])
        elif v["status"] != "blad":
            out["skipped"].append(v["id"])
    return out


def schedule_accepted(st: dict, ids=None, dry_run: bool = False) -> dict:
    """Planuje w Zernio zaakceptowane wersje bez posta: wskazane `ids` albo wszystkie.

    Wersję, której plik zniknął z dysku, renderuje od nowa (render jest powtarzalny). Wersji w innym statusie niż
    „zaakceptowana” nie rusza i mówi, co z nią zrobić. Zwraca {"eligible", "done", "failed", "refused", "clashes"};
    `clashes` to wersje pominięte, bo ich termin zajmuje już inny post IG w Zernio (patrz `clash_hint`).

    Przy `dry_run` kolejne wersje zajmują terminy w pamięci (w `st`), więc plan na sucho pokazuje te same, różne
    terminy co prawdziwy przebieg. Wywołujący musi wtedy trzymać stan tylko w pamięci i go nie zapisywać.
    """
    items = st["versions"]
    refused = []
    if ids is None:
        todo = sorted((v for v in items.values() if v["status"] == "zaakceptowana" and not v.get("zernio_post_id")),
                      key=by_slot)
    else:
        todo = []
        for vid in ids:
            v = items[vid]
            if v["status"] == "zaakceptowana":
                todo.append(v)
            elif v["status"] == "do_akceptacji":
                say("  %s czeka na akceptację klienta. Gdy klient wyraźnie napisze „akceptuję”, uruchom akceptuj %s "
                    "(albo akceptuj --wszystkie)." % (vid, vid))
                refused.append(vid)
            elif v["status"] in ("zaplanowana", "opublikowana"):
                say("  %s już jest w Zernio (status: %s)." % (vid, config.STATUS_LABEL[v["status"]]))
            else:
                say("  %s ma status %s, więc jej nie planuję." % (vid, config.STATUS_LABEL.get(v["status"], v["status"])))
                refused.append(vid)
    if todo and not dry_run:
        schedule_settings()  # zły zapis ustawień i brak konta zgłaszamy od razu, zanim ruszy cokolwiek
        account_id()
    loop = _Loop(st)
    done = 0
    clashes = []
    for v in todo:
        if dry_run:
            done += bool(schedule_one(st, v, True, clashes))
            continue

        def work(v=v):
            if _needs_upload(v, now()) and not video_file(v).is_file():
                produce(st, v, False)  # pliku nie ma, więc renderuję go od nowa
            return schedule_one(st, v, False, clashes)

        done += bool(loop.attempt(v, work))
    return {"eligible": len(todo), "done": done, "failed": loop.failed, "refused": refused, "clashes": clashes}


# --- plan terminów ---------------------------------------------------------------

def _as_start(start):
    """Początek planu jako chwila ze strefą klienta: z napisu „RRRR-MM-DD” (północ), z daty albo z chwili."""
    if start is None:
        return None
    if isinstance(start, str):
        return planner.parse_slot(start if "T" in start else start + "T00:00:00")
    if isinstance(start, datetime):
        return start if start.tzinfo else start.replace(tzinfo=planner.TZ)
    return datetime(start.year, start.month, start.day, tzinfo=planner.TZ)


def free_slots(st: dict, days: int, start=None, limit=None) -> list:
    """Wolne terminy z najbliższych `days` dni, od najwcześniejszego. `start` (data, napis RRRR-MM-DD albo chwila):
    nie wcześniej niż to, `limit`: najwyżej tyle terminów. Przy włączonym hamulcu zostaje jeden termin dziennie."""
    s = schedule_settings()
    start = _as_start(start)
    brake = bool(st.get("brake", {}).get("on", False))
    taken = planner.taken_slots(st["versions"])
    slots = [t for t in planner.slot_times(now(), days, hours(), brake, s["brake_slot"])
             if planner.slot_str(t) not in taken and (start is None or t >= start)]
    return slots[:limit] if limit else slots


def plan_clashes(rows: list) -> list:
    """Wiersze planu (z `plan_rows`), na których termin w Zernio stoi już inny post IG tego konta.

    Tylko odczyt: to samo sprawdzenie (`zernio.ig_post_at`), które robi prawdziwe planowanie, więc plan na sucho
    pomija te same terminy, co prawdziwa paczka. Niczego nie wysyła i nie zmienia stanu.
    """
    account = account_id()
    return [row for row in rows if zernio.ig_post_at(account, row[0])]


def _report_blocked(reels: dict, blocked: dict, usable: list) -> None:
    """Mówi, które rolki plan pomija i dlaczego. Gdy nie zostaje żadna aktywna rolka, kończy się `UserError`."""
    if not blocked:
        return
    if not any(r.get("active", True) for r in usable):
        groups = {}
        for code, reason in blocked.items():
            groups.setdefault(reason, []).append(reel_name(reels, code))
        raise config.UserError("Nie ma rolki, z której da się zrobić wersje. %s Popraw to i uruchom komendę sprawdz-pule."
                               % " ".join("%s: %s." % (", ".join(names), reason) for reason, names in groups.items()))
    for code, reason in blocked.items():
        say("Uwaga: pomijam rolkę %s: %s. Reszta puli idzie dalej. Popraw to i uruchom sprawdz-pule: rolka wróci do "
            "planu od następnej paczki." % (_title(reels[code]), reason))


def plan_rows(st: dict, days: int, start=None, limit=None) -> list:
    """Plan na wolne terminy z najbliższych `days` dni jako krotki (termin, kod rolki, poziom zmian, hook).

    Rolki wybiera `planner.assign` (kolejka ważona, żadnej dwa razy jednego dnia), poziom zmian i hook kolejne
    wersje tej samej rolki dobierają się tak, żeby proporcje 50/30/20 i bank hooków się zgadzały.

    Rolka bez hooków albo z hookami i podpisami, które łamią limity (`reel_problems`), jest pomijana z ostrzeżeniem,
    a reszta puli idzie dalej. Plan odmawia (`UserError`) dopiero wtedy, gdy nie zostaje żadna aktywna rolka.
    """
    t_now = now()
    reels, blocked = pool(), reel_problems()
    usable = [r for r in pool_list() if r["code"] not in blocked]
    _report_blocked(reels, blocked, usable)
    slots = free_slots(st, days, start, limit)
    plan = planner.assign(slots, usable, st["versions"], t_now)
    bank = hooks()
    extra, tmp = Counter(), dict(st["versions"])
    rows = []
    for t, code in plan:
        hooks_of_reel = bank[code]
        level = planner.pick_level(tmp, reels[code], extra)
        hook = planner.pick_hook(code, hooks_of_reel, tmp)
        extra[level] += 1
        fake = "plan-%d" % len(rows)
        tmp[fake] = {"id": fake, "code": code, "level": level, "hook_id": hook["id"], "slot": planner.slot_str(t),
                     "status": "zaplanowana"}
        rows.append((t, code, level, hook))
    return rows


def planned_on(st: dict, day, statuses=("zaplanowana",)) -> list:
    """Wersje o danym statusie (domyślnie zaplanowane w Zernio) z terminem w dniu `day` (data w strefie klienta)."""
    return [v for v in sorted(st["versions"].values(), key=by_slot)
            if v.get("status") in statuses and v.get("slot") and planner.parse_slot(v["slot"]).date() == day]


def waiting_for_review(st: dict) -> list:
    """Wersje, które czekają na decyzję klienta (zaakceptować albo odrzucić), od najstarszej. Robi je `pierwsze`."""
    return sorted((v for v in st["versions"].values() if v["status"] == "do_akceptacji"), key=id_number)


def versions_wait(n: int) -> str:
    """Liczba wersji z poprawną odmianą rzeczownika i czasownika: „1 wersja czeka”, „3 wersje czekają”, „7 wersji czeka”."""
    if n == 1:
        return "1 wersja czeka"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "%d wersje czekają" % n
    return "%d wersji czeka" % n


def started(st: dict) -> bool:
    """Czy klient zaakceptował pierwsze wersje: jakakolwiek jest już w Zernio (zaplanowana albo opublikowana)."""
    return any(v.get("status") in ("zaplanowana", "opublikowana") for v in st["versions"].values())


def hook_bank_low(st: dict, planned: list = ()) -> list:
    """Nazwy aktywnych rolek, którym zostało mniej niż 3 nieużyte hooki (potem idą powtórki najlepszych).

    Rolka bez żadnego hooka to nie „prawie pusty bank”, tylko rolka, którą plan pomija (patrz `reel_problems`), więc
    tej listy nie dotyczy.

    `planned` to wiersze planu (z `plan_rows`), których wersji jeszcze nie ma: plan na sucho liczy bank tak, jakby
    już powstały, żeby powiedzieć to samo, co powie prawdziwa paczka.
    """
    reels, bank = pool(), hooks()
    used = dict(st["versions"])
    for i, (_, code, _, hook) in enumerate(planned):
        used["plan-%d" % i] = {"id": "plan-%d" % i, "code": code, "hook_id": hook["id"]}
    low = []
    for code, reel in reels.items():
        mine = _hooks_of(bank, code)       # rolka bez żadnego hooka jest pomijana w planie, a nie „prawie pusta”
        if reel.get("active", True) and mine and planner.bank_left(code, mine, used) < HOOK_BANK_LOW:
            low.append(reel_name(reels, code))
    return low


def daily_hint(st: dict):
    """Podpowiedź, gdy render jest tak wolny, że tydzień nie zmieści się w ok. 90 minutach. Inaczej None.

    Liczy średni czas ostatnich 20 renderów (`render_s`). Decyzję o mniejszej liczbie triali dziennie podejmuje klient.
    """
    per_day = planner.daily_count(pool_list(), schedule_settings()["daily_max"])
    times = [v["render_s"] for v in sorted(st["versions"].values(), key=id_number)
             if isinstance(v.get("render_s"), (int, float)) and v["render_s"] > 0][-20:]
    if not times or per_day < 1:
        return None
    avg = sum(times) / len(times)
    better = planner.suggest_daily(avg, per_day, BUDGET_MIN)
    if better >= per_day:
        return None
    return ("Render trwa u ciebie średnio %d s na wersję, więc paczka na tydzień (%d wersji dziennie) zajmuje około %d "
            "minut. Żeby zmieścić się w około %d minutach, możesz zmniejszyć dzienną liczbę triali do %d "
            "(ustawienie daily_max w dane/config.json). To twoja decyzja: na razie zostaje %d."
            % (round(avg), per_day, round(per_day * 7 * avg / 60), BUDGET_MIN, better, per_day))


# --- hamulec ---------------------------------------------------------------------

def check_brake(st: dict) -> dict:
    """Liczy hamulec ze statystyk zwykłych rolek konta klienta i zapisuje wynik w `st["brake"]`.

    Gdy Zernio nie podaje statystyk (np. stary plan), zostaje poprzedni stan. Zostaje on też wtedy, gdy zwykłych rolek
    jest za mało, żeby policzyć wskaźnik (`ratio` to wtedy None), ale najwyżej `config.BRAKE_NODATA_DAYS` dni od
    pierwszego sprawdzenia bez danych: potem włączony hamulec sam się wyłącza, żeby klient nie utknął na 1 trialu
    dziennie. Zły albo brakujący klucz zgłasza błąd od razu.
    """
    account = account_id()
    t = now()
    pub = [planner.parse_slot(v["slot"]) for v in st["versions"].values()
           if v.get("status") == "opublikowana" and v.get("slot")]
    first = min(pub) if pub else None
    since = min(first - timedelta(days=29), t - timedelta(days=17)) if first else t - timedelta(days=17)
    try:
        posts = zernio.analytics(account, since.date(), t.date())
    except zernio.ZernioError as e:
        if e.status in (401, 403) or (e.status is None and (getattr(e, "key", False) or "brak klucza" in str(e))):
            raise
        say("  ! hamulec: nie mogę pobrać statystyk z Zernio%s, zostaje poprzedni stan"
            % (" (kod %d)" % e.status if e.status else ""))
        return st.get("brake", {})
    urls = {v.get("ig_url") for v in st["versions"].values() if v.get("ig_url")}
    ratio = planner.brake_ratio(posts, urls, t, first)
    prev = st.get("brake", {})
    was_on = bool(prev.get("on", False))
    brake = {"ratio": ratio, "checked": t.isoformat(timespec="minutes")}
    if ratio is not None:
        brake["on"] = ratio < 1 - config.BRAKE_DROP
    else:
        since = prev.get("nodata_since") or brake["checked"]
        brake["nodata_since"] = since
        brake["on"] = was_on and t - datetime.fromisoformat(since) < timedelta(days=config.BRAKE_NODATA_DAYS)
        if was_on and not brake["on"]:
            say("  Hamulec wyłączony: od %d dni nie ma danych o zwykłych rolkach, więc wracam do pełnej liczby triali."
                % config.BRAKE_NODATA_DAYS)
    st["brake"] = brake
    return st["brake"]


# --- sprawdzanie publikacji i sprzątanie -----------------------------------------

def verify(st: dict) -> Counter:
    """Pyta Zernio o wersje, których termin minął, i ustawia status: opublikowana (z linkiem), blad albo zostaje.

    Zwraca liczniki: sprawdzone, opublikowana, blad, czeka.
    """
    t_now = now()
    counts = Counter()
    for v in sorted(st["versions"].values(), key=id_number):
        if v["status"] != "zaplanowana" or not v.get("zernio_post_id") or not v.get("slot"):
            continue
        if planner.parse_slot(v["slot"]) > t_now:
            continue
        counts["sprawdzone"] += 1
        try:
            post = zernio.get_post(v["zernio_post_id"])
        except zernio.ZernioError as e:
            if e.status != 404:
                raise
            v.update(status="blad", note="Posta nie ma już w Zernio (ktoś go usunął?). Jego termin znów jest wolny.")
            counts["blad"] += 1
            say("  %s: posta nie ma w Zernio" % v["id"])
            continue
        plat = (post.get("platforms") or [{}])[0]
        url = plat.get("platformPostUrl") or plat.get("postUrl")
        status = plat.get("status") or post.get("status")
        if status == "published" and url:
            v.update(status="opublikowana", ig_url=url, ig_media_id=candidates.media_id(url))
            counts["opublikowana"] += 1
            say("  %s: opublikowana %s" % (v["id"], url))
        elif status in ("failed", "error") or post.get("status") == "failed":
            reason = plat.get("errorMessage") or plat.get("error") or post.get("error") or "Zernio nie podało powodu"
            v.update(status="blad", note=config.line(reason)[:500])
            counts["blad"] += 1
            say("  %s: błąd publikacji: %s" % (v["id"], v["note"]))
        else:
            counts["czeka"] += 1
            say("  %s: czeka na publikację (status w Zernio: %s)" % (v["id"], status or "brak"))
    return counts


def cleanup(st: dict, days: int = KEEP_DAYS) -> int:
    """Kasuje z dysku filmy wersji opublikowanych co najmniej `days` dni temu (liczone od terminu). Zwraca, ile wersji.

    Kasuje film wersji (dane/wersje/<ID>.mp4) i nakładkę z hookiem, a cudzych plików nie rusza: ścieżki z pola `file`
    w stanie nie bierze, a wersję ze złym numerem (nie TR-001) pomija. Film zostaje w Zernio i na Instagramie.
    """
    t_now = now()
    removed = 0
    for v in st["versions"].values():
        if v.get("status") != "opublikowana" or not v.get("slot") or not config.version_id_ok(v.get("id")):
            continue
        try:
            age = t_now - planner.parse_slot(v["slot"])
        except ValueError:
            continue
        if age < timedelta(days=days):
            continue
        files = [config.OUT / ("%s.mp4" % v["id"]), config.OUT / ("%s_hook.png" % v["id"])]
        gone = False
        for path in files:
            try:
                existed = path.is_file()
                path.unlink(missing_ok=True)
            except OSError:
                continue
            gone = gone or (existed and path.suffix == ".mp4")
        removed += gone
    return removed


# --- raport ----------------------------------------------------------------------

def recent(st: dict, days: int = 14) -> list:
    """Wersje z ostatnich `days` dni (utworzone albo z terminem od tamtej pory, także przyszłym), od najwcześniejszego terminu."""
    limit = now() - timedelta(days=days)
    out = []
    for v in sorted(st["versions"].values(), key=by_slot):
        for stamp in (v.get("created"), v.get("slot")):
            try:
                when = planner.parse_slot(stamp) if stamp else None
            except ValueError:
                continue
            if when is not None and when >= limit:
                out.append(v)
                break
    return out


def brake_line(brake: dict) -> str:
    """Zdanie o hamulcu do raportu. Bez wskaźnika (za mało zwykłych rolek) mówi, że hamulec jest nieaktywny albo że
    zostaje, bo nie ma jak sprawdzić, czy zasięg wrócił."""
    on = bool(brake.get("on"))
    if brake.get("ratio") is None:
        if on:
            return ("Hamulec: włączony, 1 trial dziennie (zostaje, bo za mało zwykłych rolek, żeby sprawdzić, czy zasięg "
                    "wrócił).")
        return "Hamulec: wyłączony (nieaktywny: za mało zwykłych rolek, żeby go policzyć)."
    return "Hamulec: %s (wskaźnik %s)." % ("włączony, 1 trial dziennie" if on else "wyłączony", _dec(brake["ratio"], "%.2f"))


def report_text(st: dict) -> str:
    """Raport tygodniowy w Markdown: hamulec, wyniki rolek, najlepsze wersje, błędy i plan na najbliższe dni."""
    t = now()
    reels = pool()
    per_reel = planner.reel_stats(st["versions"])
    weights = planner.weights(pool_list(), st["versions"], t)
    brake = st.get("brake", {})
    lines = ["# Trial reels: raport %s" % t.strftime("%d.%m.%Y"), "", brake_line(brake),
             "", "| Rolka | Triale | Zmierzone | Wyświetlenia | Obserwujący | Obs./1000 | Waga |",
             "|---|---|---|---|---|---|---|"]
    for code, r in reels.items():
        if not r.get("active", True):
            continue
        n = sum(1 for v in st["versions"].values() if v["code"] == code and v["status"] in ("zaplanowana", "opublikowana"))
        s = per_reel.get(code, {"views": 0, "follows": 0, "n": 0})
        lines.append("| %s | %d | %d | %d | %d | %s | %s |" % (
            reel_name(reels, code).replace("|", "/"), n, s["n"], s["views"], s["follows"],
            _dec(planner.per_1000(s)), _dec(weights.get(code, 0), "%g")))
    measured = [v for v in st["versions"].values() if v.get("views")]
    best = sorted(measured, key=lambda v: (v.get("follows") or 0), reverse=True)[:5]
    if best:
        lines += ["", "Najlepsze wersje (kandydaci do przepuszczenia do obserwujących):"]
        for v in best:
            link = " (%s)" % v["ig_url"] if v.get("ig_url") else ""   # wersja zmierzona ręcznie może nie mieć adresu
            lines.append("- %s %s, „%s”: %d obserwujących z %d wyświetleń%s" % (
                v["id"], reel_name(reels, v["code"]), v.get("hook", ""), v.get("follows") or 0, v["views"], link))
    errors = open_errors(st)
    if errors:
        lines += ["", "Błędy:"] + ["- %s: %s" % (v["id"], v.get("note", "")) for v in errors]
    upcoming = [v for v in st["versions"].values()
                if v["status"] == "zaplanowana" and v.get("slot") and planner.parse_slot(v["slot"]) > t]
    lines += ["", "Zaplanowane na najbliższe dni: %d." % len(upcoming)]
    low = hook_bank_low(st)
    if low:
        lines.append("Bank hooków prawie pusty, idą powtórki najlepszych (to OK): %s." % ", ".join(low))
    return "\n".join(lines) + "\n"
