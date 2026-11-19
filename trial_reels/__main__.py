"""Wejście do komend: `bash trial.sh <komenda>` (Mac, Git Bash) albo `.\\trial.cmd <komenda>` (PowerShell).

Komendy konfiguracji (doktor, klucz, konto, kandydaci, pula, pobierz, transkrybuj, kadr…) prowadzą klienta przez start,
a komendy cyklu wersji (pierwsze, podglad, akceptuj, odrzuc, zaplanuj, paczka, sprawdz, do-odczytu, zapisz-wynik,
hamulec, raport, status) prowadzą go przez codzienną pracę. Komenda krok mówi, na którym kroku kreatora jesteśmy,
a aktualizuj sprawdza wydania na GitHubie i po zgodzie podmienia kod (bez ruszania danych).
Znane problemy (brak klucza, brak internetu, odmowa Zernio, uszkodzony plik z danymi) wychodzą jako jedna zrozumiała
linia i kod 1, bez śladu stosu. Błąd w samym kodzie zostaje z pełnym śladem, żeby dało się go zgłosić.

Ciężkie pakiety (PIL, PyAV, faster-whisper) ładują się dopiero w komendach, które ich potrzebują, więc `doktor`
działa także na uszkodzonej instalacji.
"""
from __future__ import annotations

import argparse
import calendar
import contextlib
import http.client
import json
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
from collections import Counter
from datetime import date, datetime, timedelta

from . import VERSION, candidates, config, doctor, planner, preview, state, stats, update, versions, wizard, zernio

READING_KEYS = ("panel_views", "panel_follows", "panel_read_at")  # odczyt z panelu IG zapisany przy kandydacie
SAMPLE_HOOK = "Tu pojawi się twój hook"
SAMPLE_EMOJI = "🔥"
# Komendy, które działają także przy uszkodzonym pliku dane/config.json i przy złej strefie czasowej w nim: pokazują
# wersję, pozwalają zobaczyć w doktorze, co poprawić, prowadzą kreator i aktualizują program (aktualizacja bywa
# lekarstwem). Liczą wtedy w strefie domyślnej. Reszta liczy terminy i czyta ustawienia, więc bez nich się zatrzymuje.
SETTINGS_FREE_COMMANDS = frozenset({"wersja", "doktor", "krok", "aktualizuj"})
MODEL_WARNING = ("Uwaga: przy pierwszej transkrypcji pobiera się model rozpoznawania mowy (ok. 1,6 GB). Pobieranie "
                 "może potrwać kilka minut, a w tym czasie nic się nie wyświetla. To normalne, nie przerywaj.")


# --- drobne narzędzia -----------------------------------------------------------

say = versions.say         # ta sama funkcja, którą drukują moduły programu (jedno miejsce, jedna definicja)


def warn(text: str) -> None:
    """Komunikat o problemie na stderr (jedna linia)."""
    print(text, file=sys.stderr, flush=True)


def now() -> datetime:
    return versions.now()


def thousands(n) -> str:
    """Liczba ze spacją między tysiącami: 12345 -> „12 345”."""
    return "{:,}".format(int(n)).replace(",", " ")


def decimal(x: float) -> str:
    """Liczba z jednym miejscem po przecinku, po polsku."""
    return ("%.1f" % x).replace(".", ",")


def months_ago(day: date, months: int) -> date:
    """Ta sama data `months` miesięcy wcześniej (31 marca minus miesiąc to 28 albo 29 lutego)."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def table(header: list, rows: list, right: tuple = ()) -> str:
    """Tabela tekstowa: kolumny wyrównane do lewej (numery z `right` do prawej), ostatnia kolumna bez dopełnienia."""
    widths = [max(len(str(cell)) for cell in column) for column in zip(header, *rows)]
    lines = []
    for row in [header, *rows]:
        cells = []
        for i, cell in enumerate(row):
            text = str(cell)
            if i == len(row) - 1:
                cells.append(text)
            else:
                cells.append(text.rjust(widths[i]) if i in right else text.ljust(widths[i]))
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def local_date(published) -> str:
    """Data publikacji (RRRR-MM-DD) w czasie planera."""
    when = candidates.parse_time(published)
    return when.astimezone(planner.TZ).strftime("%Y-%m-%d") if when else str(published or "")[:10]


def account_id() -> str:
    """ID konta Instagrama zapisane przez `konto`. Bez niego komenda nie wie, czyje rolki czytać."""
    return versions.account_id()


def has_file(c: dict) -> bool:
    """Czy mamy plik rolki albo Zernio ma go do pobrania."""
    return bool(c.get("media_url")) or (config.SRC / ("%s.mp4" % c["code"])).is_file()


def active_reels(pool: list) -> list:
    """Aktywne rolki puli z poprawnym kodem (wpis z zepsutym kodem zgłasza `sprawdz-pule`, a komendy go pomijają)."""
    return [r for r in pool if isinstance(r, dict) and candidates.valid_code(r.get("code")) and r.get("active", True)]


def _reason(error: BaseException) -> str:
    text = config.line(error)
    return "%s: %s" % (type(error).__name__, text) if text else type(error).__name__


# --- opis błędów dla klienta ----------------------------------------------------

def _zernio_problem(e: zernio.ZernioError) -> str:
    status, text = e.status, config.line(e)[:300]
    if status is None:
        if "brak klucza" in text:
            return ("Brak klucza Zernio w dane/.env. Uruchom komendę klucz (otworzy plik w edytorze), wklej klucz i "
                    "uruchom tę komendę jeszcze raz.")
        return text[:1].upper() + text[1:]
    if status in (401, 403):
        return ("Zernio nie przyjęło klucza z dane/.env (kod %d). Sprawdź, czy klucz jest wklejony w całości (plik "
                "otworzy komenda klucz), i uruchom komendę jeszcze raz." % status)
    if status == 402:
        return "Zernio żąda płatności za tę funkcję (kod 402). Sprawdź plan w panelu Zernio."
    if status == 429:
        return "Zernio prosi o zwolnienie tempa (kod 429). Poczekaj minutę i uruchom komendę jeszcze raz."
    if status >= 500:
        return "Zernio ma chwilową awarię (kod %d). Spróbuj za kilka minut." % status
    return "Zernio odpowiedziało błędem: %s" % text


def explain(e: BaseException) -> str | None:
    """Jedna zrozumiała linia dla klienta albo None, gdy to nie jest znany problem (wtedy to błąd w kodzie)."""
    if isinstance(e, config.UserError):
        return config.line(e)
    if isinstance(e, zernio.ZernioError):
        return _zernio_problem(e)
    if isinstance(e, json.JSONDecodeError):
        if str(config.DATA) in str(e):
            return ("Plik z danymi jest uszkodzony: %s. Napraw go albo usuń, a potem uruchom komendę jeszcze raz."
                    % config.line(e))
        return "Zernio odpowiedziało w nieczytelny sposób (%s). Spróbuj jeszcze raz za chwilę." % config.line(e)
    if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException,
                      ssl.SSLError, socket.gaierror)):
        return "Nie mogę połączyć się z Zernio. Sprawdź internet i uruchom komendę jeszcze raz."
    if isinstance(e, OSError):
        return "Problem z plikiem albo folderem: %s." % config.line(e)
    return None


# --- komendy: komputer i konto --------------------------------------------------

def cmd_wersja(args: argparse.Namespace) -> int:
    print(VERSION)
    return 0


def cmd_doktor(args: argparse.Namespace) -> int:
    rows = doctor.checks()
    for row in rows:
        say("%s %s: %s" % ("✓" if row["ok"] else "✗", row["nazwa"], row["info"]))
    bad = [row for row in rows if not row["ok"]]
    say("")
    if bad:
        say("Do poprawienia: %d. Popraw to i uruchom doktor jeszcze raz." % len(bad))
        return 1
    say("Wszystko gra: komputer jest gotowy.")
    return 0


# Edytor tekstu, w którym klient wkleja klucz, i skrót zapisu: (nazwa dla klienta, skrót).
EDITORS = {"darwin": ("TextEdit", "Cmd+S"), "win32": ("Notatnik", "Ctrl+S")}


def _open_editor(path) -> bool:
    """Otwiera plik w edytorze tekstu (Mac: TextEdit, Windows: Notatnik) i nie czeka na zamknięcie okna.

    Edytor nie dziedziczy wejścia ani wyjścia komendy, więc narzędzie, które ją uruchomiło, nie czeka na niego.
    False, gdy edytora nie udało się uruchomić albo system jest inny niż Mac i Windows.
    """
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    try:
        if sys.platform == "darwin":
            return subprocess.run(["open", "-e", str(path)], timeout=60, **quiet).returncode == 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(["notepad.exe", str(path)], creationflags=flags, **quiet)
            return True
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def cmd_klucz(args: argparse.Namespace) -> int:
    """Plik dane/.env z kluczem Zernio: tworzy go (gdy go nie ma) i otwiera klientowi w edytorze. Treści nie pokazuje."""
    if config.adopt_env_txt():
        say("Notatnik zapisał klucz w pliku dane/.env.txt, więc przeniosłem go do dane/.env (klucza nie pokazuję). "
            "Sprawdź komendą krok, czy krok „Zernio i klucz” jest gotowy.")
        return 0
    created = config.create_env()
    say("Utworzyłem plik dane/.env z jedną linią ZERNIO_API_KEY=." if created else
        "Plik dane/.env już jest: niczego w nim nie zmieniam i nie pokazuję jego treści.")
    if config.key_in_file():
        say("W pliku jest już klucz. Żeby go wymienić, wklej nowy klucz w miejsce starego.")
    name, save = EDITORS.get(sys.platform, ("edytor tekstu", "Ctrl+S"))
    if not _open_editor(config.ENV):
        raise config.UserError("Nie udało się otworzyć edytora. Otwórz ręcznie plik dane/.env (w folderze dane, to plik "
                               "ukryty) w edytorze tekstu, wklej klucz tuż za znakiem = i zapisz plik.")
    say("Otworzyłem dane/.env w edytorze (%s). Wklej klucz z Zernio w tej samej linii, tuż za znakiem =, bez spacji i bez "
        "cudzysłowów, zapisz plik (%s) i zamknij okno. Klucza nie wklejaj do czatu. Potem komenda krok sprawdzi, czy "
        "program widzi klucz." % (name, save))
    return 0


def _nick(account: dict) -> str:
    return str(account.get("username") or account.get("name") or account.get("displayName")
               or account.get("_id") or account.get("id") or "?")


def cmd_konto(args: argparse.Namespace) -> int:
    accounts = zernio.accounts()
    if not accounts:
        raise config.UserError("Zernio nie ma podłączonego konta Instagrama. Podłącz je w panelu Zernio "
                               "(Connect, Instagram) i uruchom komendę konto jeszcze raz.")
    say("Konta Instagrama w Zernio:")
    for account in accounts:
        say("  @%s" % _nick(account))
    if args.nick:
        wanted = args.nick.strip().lstrip("@")
        chosen = next((a for a in accounts if _nick(a).lower() == wanted.lower()), None)
        if chosen is None:
            raise config.UserError("Nie ma konta @%s w Zernio. Podłączone konta: %s."
                                   % (wanted, ", ".join("@" + _nick(a) for a in accounts)))
    elif len(accounts) == 1:
        chosen = accounts[0]
    else:
        say("")
        say("Masz kilka kont. Wybierz jedno: konto --nick NICK (nick z listy wyżej).")
        return 0
    chosen_id = chosen.get("_id") or chosen.get("id")
    if not chosen_id:
        raise config.UserError("Zernio nie podało ID tego konta. Spróbuj jeszcze raz za chwilę.")
    config.save_settings({"ig_account_id": str(chosen_id), "ig_handle": _nick(chosen)})
    say("Zapisałem konto @%s." % _nick(chosen))
    try:  # sprawdzenie, czy statystyki rolek da się odczytać (np. plan Zernio ich nie blokuje)
        today = now().date()
        posts = zernio.analytics(str(chosen_id), today - timedelta(days=30), today)
    except (zernio.ZernioError, OSError, http.client.HTTPException, ValueError) as e:
        say("Uwaga: konto jest zapisane, ale test odczytu rolek się nie udał: %s" % (explain(e) or _reason(e)))
    else:
        reels = sum(1 for p in posts if isinstance(p, dict) and str(p.get("mediaProductType") or "").upper() == "REELS")
        say("Test odczytu się udał. Rolek z ostatnich 30 dni: %d." % reels)
    return 0


# --- komendy: kandydaci i pula --------------------------------------------------

def print_candidates(cands: list) -> None:
    measured = any(c.get("panel_follows") is not None for c in cands)
    header = ["Kod", "Data", "Wyświetlenia"] + (["Obserwujący"] if measured else []) + ["Plik", "Początek podpisu"]
    right = (2, 3) if measured else (2,)
    rows = []
    for c in cands:
        row = [c["code"], local_date(c.get("published")), thousands(c.get("views") or 0)]
        if measured:
            row.append("-" if c.get("panel_follows") is None else thousands(c["panel_follows"]))
        row += ["tak" if has_file(c) else "nie", candidates.preview(c.get("caption"))]
        rows.append(row)
    say(table(header, rows, right))


def cmd_kandydaci(args: argparse.Namespace) -> int:
    account = account_id()
    t = now()
    posts = zernio.analytics(account, months_ago(t.date(), args.miesiace), t.date())
    cands = candidates.select(posts, t, top=args.ile)
    if not cands:
        raise config.UserError("Nie ma rolek, które spełniają warunki (wideo z ostatnich %d miesięcy, starsze niż "
                               "7 dni, bez reklam i bez triali). Sprawdź konto komendą konto." % args.miesiace)
    earlier = {c.get("code"): c for c in candidates.load_candidates() if isinstance(c, dict)}
    for c in cands:  # odczyty z panelu IG zostają przy rolkach, które wróciły na listę
        before = earlier.get(c["code"], {})
        c.update({key: before[key] for key in READING_KEYS if key in before})
    candidates.save_candidates(cands)
    print_candidates(cands)
    say("")
    say("Zapisałem kandydatów w dane/kandydaci.json: %d." % len(cands))
    return 0


def cmd_wynik_kandydata(args: argparse.Namespace) -> int:
    cands = candidates.load_candidates()
    if not cands:
        raise config.UserError("Nie ma jeszcze listy kandydatów. Najpierw uruchom komendę kandydaci.")
    code = candidates.shortcode(args.kod)
    target = next((c for c in cands if c.get("code") == code), None) if code else None
    if target is None:
        raise config.UserError("Rolki %s nie ma na liście kandydatów. Uruchom komendę kandydaci albo sprawdź kod."
                               % args.kod)
    try:
        views = stats.parse_count(args.wyswietlenia)
        follows = stats.parse_count(args.obserwujacy)
    except ValueError as e:
        raise config.UserError(str(e)) from None
    target.update(panel_views=views, panel_follows=follows, panel_read_at=now().strftime("%Y-%m-%dT%H:%M"))
    candidates.save_candidates(cands)
    per_1000 = " (%s na 1000 wyświetleń)" % decimal(1000 * follows / views) if views else ""
    say("%s: %s wyświetleń, %s obserwujących%s." % (code, thousands(views), thousands(follows), per_1000))
    return 0


def cmd_js_odczyt(args: argparse.Namespace) -> int:
    say(stats.JS_ODCZYT.rstrip("\n"))
    return 0


def show_pool(pool: list) -> None:
    if not pool:
        say("Pula jest pusta. Dodaj rolki komendą pula KOD ... albo pula --auto 12.")
        return
    rows = []
    for r in pool:
        entry = r if isinstance(r, dict) else {}
        code = str(entry.get("code", "?"))
        rows.append([code, "tak" if entry.get("active", True) else "nie",
                     "tak" if (config.SRC / ("%s.mp4" % code)).is_file() else "nie",
                     "tak" if (config.TRANSCRIPTS / ("%s.json" % code)).is_file() else "nie",
                     candidates.preview(entry.get("name"))])
    say(table(["Kod", "Aktywna", "Plik", "Transkrypcja", "Nazwa"], rows))
    say("")
    say("Rolek w puli: %d (aktywnych: %d)." % (len(pool), len(active_reels(pool))))


def cmd_pula(args: argparse.Namespace) -> int:
    pool = candidates.load_pool()
    if not args.kody and args.auto is None:
        show_pool(pool)
        return 0
    cands = candidates.load_candidates()
    if not cands:
        raise config.UserError("Nie ma jeszcze listy kandydatów. Najpierw uruchom komendę kandydaci.")
    by_code = {c["code"]: c for c in cands if isinstance(c, dict) and c.get("code")}
    known = {r.get("code") for r in pool if isinstance(r, dict)}
    added, unknown = [], []

    def add(c: dict) -> None:
        entry = candidates.pool_entry(c)
        pool.append(entry)
        known.add(entry["code"])
        added.append(entry["code"])
        say("Dodano do puli: %s (%s)." % (entry["code"], entry["name"]))

    for raw in args.kody:
        code = candidates.shortcode(raw)
        if code in known:
            say("Już jest w puli: %s." % code)
        elif code in by_code:
            add(by_code[code])
        else:
            unknown.append(raw)
    if args.auto is not None:
        need = args.auto - len(active_reels(pool))
        if need <= 0:
            say("W puli jest już %d aktywnych rolek (cel: %d). Nic nie dopisuję." % (len(active_reels(pool)), args.auto))
        else:
            ranked, measured = candidates.rank(list(by_code.values()))
            if not measured:
                say("Uwaga: nie ma odczytów obserwujących, więc wybieram według wyświetleń, a to słabsza miara. "
                    "Odczyt z panelu (komenda wynik-kandydata) da lepszy wybór.")
            for c in ranked:
                if need <= 0:
                    break
                if c["code"] not in known:
                    add(c)
                    need -= 1
    if added:
        candidates.save_pool(pool)
    say("Rolek w puli: %d (aktywnych: %d)." % (len(pool), len(active_reels(pool))))
    if unknown:
        warn("Nie ma na liście kandydatów: %s. Uruchom komendę kandydaci albo sprawdź kody." % ", ".join(unknown))
        return 1
    return 0


# --- komendy: pliki, transkrypcje, walidacja, kadr ------------------------------

def fetch_start(reels: list, today: date) -> date:
    """Początek okna statystyk do pobrania plików: co najmniej rok wstecz, a dla starszych rolek do ich daty z ID."""
    start = months_ago(today, 12)
    for r in reels:
        made = candidates.created_at(r.get("media_id"))
        if made is not None:
            start = min(start, made.date() - timedelta(days=7))
    return max(start, months_ago(today, 72))


def cmd_pobierz(args: argparse.Namespace) -> int:
    pool = candidates.load_pool()
    reels = active_reels(pool)
    if not reels:
        raise config.UserError("Pula jest pusta albo wszystkie rolki są wyłączone. Najpierw dodaj rolki komendą pula.")
    todo, changed = [], False
    for r in reels:
        if (config.SRC / ("%s.mp4" % r["code"])).is_file():
            changed = r.pop("brak_pliku", None) is not None or changed  # plik jest, więc stara flaga nie ma sensu
        else:
            todo.append(r)
    if not todo:
        if changed:
            candidates.save_pool(pool)
        say("Wszystkie aktywne rolki mają już pliki w dane/src.")
        return 0
    account = account_id()
    today = now().date()
    posts = zernio.analytics(account, fetch_start(todo, today), today)
    by_code = {}
    for post in posts:
        by_code.setdefault(candidates.shortcode(post.get("platformPostUrl")) if isinstance(post, dict) else None, post)
    got, no_file, failed = [], [], []
    try:
        for i, r in enumerate(todo, start=1):
            code = r["code"]
            url = candidates.media_url(by_code.get(code))
            if not url:
                r["brak_pliku"] = True
                no_file.append(code)
                say("Rolka %s: Zernio nie ma jej pliku, bo zwykle to rolka z muzyką z biblioteki Instagrama. Co dalej: "
                    "wrzuć oryginał jako dane/src/%s.mp4 albo wyłącz rolkę (active: false)." % (code, code))
                continue
            say("Pobieram %d z %d: %s ..." % (i, len(todo), code))
            dest = config.SRC / ("%s.mp4" % code)
            try:
                zernio.download(url, dest)
            except (zernio.ZernioError, OSError, http.client.HTTPException) as e:
                failed.append(code)
                warn("Rolka %s: %s" % (code, explain(e) or _reason(e)))
                continue
            r.pop("brak_pliku", None)
            got.append(code)
            say("  gotowe (%s MB)." % decimal(dest.stat().st_size / 1_000_000))
    finally:
        candidates.save_pool(pool)
    say("Pobrane: %d. Bez pliku w Zernio: %d. Nieudane: %d." % (len(got), len(no_file), len(failed)))
    return 1 if failed else 0


def cmd_transkrybuj(args: argparse.Namespace) -> int:
    from . import transcribe  # numpy i faster-whisper ładują się dopiero tutaj

    reels = active_reels(candidates.load_pool())
    if not reels:
        raise config.UserError("W puli nie ma aktywnych rolek. Najpierw dodaj je komendą pula.")
    todo, skipped = [], 0
    for r in reels:
        code = r["code"]
        src, out = config.SRC / ("%s.mp4" % code), config.TRANSCRIPTS / ("%s.json" % code)
        if out.is_file():
            continue
        if not src.is_file():
            skipped += 1
            say("Rolka %s: nie ma pliku dane/src/%s.mp4, więc pomijam ją. Uruchom komendę pobierz." % (code, code))
            continue
        todo.append((code, src, out))
    if not todo:
        say("Nie ma nic do zrobienia: rolki z plikiem mają już transkrypcje." if skipped
            else "Wszystkie transkrypcje są gotowe.")
        return 0
    if not transcribe.model_cached():
        say(MODEL_WARNING)
    failed = 0
    for i, (code, src, out) in enumerate(todo, start=1):
        say("Transkrypcja %d z %d: %s ..." % (i, len(todo), code))
        try:
            transcribe.transcribe(src, out)
        except (RuntimeError, FileNotFoundError) as e:
            failed += 1
            warn("Rolka %s: %s" % (code, config.line(e)))
            continue
        except Exception as e:  # najczęściej model (brak internetu przy pobraniu); kolejne rolki padłyby tak samo
            raise config.UserError("Nie udało się wczytać modelu rozpoznawania mowy (%s). Pierwsze uruchomienie pobiera "
                                   "go z internetu (ok. 1,6 GB), więc sprawdź internet i uruchom komendę transkrybuj "
                                   "jeszcze raz." % _reason(e)) from None
        say("  gotowe.")
    say("Transkrypcje gotowe, poza nieudanymi: %d." % failed if failed else "Transkrypcje gotowe.")
    return 1 if failed else 0


def cmd_sprawdz_pule(args: argparse.Namespace) -> int:
    pool = candidates.load_pool()
    active = [r for r in pool if not isinstance(r, dict) or r.get("active", True)]
    if not active:
        say("Pula jest pusta albo wszystkie rolki są wyłączone. Dodaj rolki komendą pula.")
        return 1
    notes: list[str] = []
    problems = candidates.validate(pool, candidates.load_hooks(), notes)
    if problems:
        say("W puli są problemy:")
        for problem in problems:
            say("- %s" % problem)
    else:
        say("Pula gotowa: %d rolek" % len(active))
    for note in notes:                       # np. rolka bez mowy: to informacja, nie problem, więc nie zmienia wyniku
        say("Informacja: %s" % note)
    return 1 if problems else 0


def cmd_kadr(args: argparse.Namespace) -> int:
    from . import render  # PIL i PyAV ładują się dopiero tutaj

    code = candidates.shortcode(args.kod)
    if code is None:          # kod trafia do nazw plików (kadr_KOD.jpg, dane/src/KOD.mp4), więc musi mieć kształt kodu
        raise config.UserError("„%s” nie wygląda na kod rolki (kod to od 6 do 64 liter, cyfr, „-” i „_”). Kody rolek "
                               "z puli pokazuje komenda pula." % config.line(args.kod)[:80])
    reel = next((r for r in candidates.load_pool() if isinstance(r, dict) and r.get("code") == code), None)
    if reel is None:
        raise config.UserError("Rolki %s nie ma w puli. Dodaj ją komendą pula." % args.kod)
    if not (config.SRC / ("%s.mp4" % code)).is_file():
        raise config.UserError("Brak pliku dane/src/%s.mp4. Najpierw uruchom komendę pobierz (albo wrzuć oryginał "
                               "pod tą nazwą)." % code)
    bank = candidates.load_hooks().get(code)
    bank = bank if isinstance(bank, list) else []
    if args.hook_id is not None:            # tekst prosto z pliku: znaki & i % nie przechodzą przez wiersz poleceń
        wanted = args.hook_id.strip()
        first = next((h for h in bank if isinstance(h, dict) and h.get("id") == wanted), None)
        if first is None:
            known = ", ".join(str(h["id"]) for h in bank if isinstance(h, dict) and h.get("id"))
            raise config.UserError("Rolka %s nie ma w dane/hooki.json hooka o id „%s”. %s"
                                   % (code, wanted, "Hooki tej rolki: %s." % known if known else
                                      "Najpierw zapisz jej hooki w dane/hooki.json."))
    else:
        first = bank[0] if bank and isinstance(bank[0], dict) else {}
    text = args.hook or first.get("text") or SAMPLE_HOOK
    available = render.emoji_set()
    if args.emoji is not None:
        emoji = args.emoji
    elif not args.hook and first.get("emoji"):
        emoji = first["emoji"]
    else:
        emoji = SAMPLE_EMOJI if SAMPLE_EMOJI in available else (available[0] if available else None)
    if emoji and emoji.replace("\ufe0f", "") not in available:
        say("Uwaga: emotki %s nie ma w zestawie (assets/emoji), więc na kadrze jej nie będzie." % emoji)
    out = config.OUT / ("kadr_%s.jpg" % code)
    config.OUT.mkdir(parents=True, exist_ok=True)
    try:
        render.hook_frame(reel, text, emoji, args.t, out)
    except subprocess.CalledProcessError:
        raise config.UserError("ffmpeg zgłosił błąd przy przygotowaniu kadru. Sprawdź, czy plik dane/src/%s.mp4 "
                               "da się odtworzyć." % code) from None
    except (RuntimeError, ValueError) as e:
        raise config.UserError(config.line(e)) from None
    say(str(out))
    return 0


# --- komendy: wersje, akceptacja i planowanie -----------------------------------

FIRST_BATCH = 9          # tyle pierwszych wersji ogląda klient, zanim ruszy paczka tygodniowa
PREVIEW_DAYS = 14        # `podglad --wszystkie` pokazuje wersje z tylu ostatnich dni
DUE_LIMIT = 30           # tyle adresów do odczytu pokazuje `do-odczytu` bez `--probka` (resztę liczy i pomija)
ID_PATTERN = re.compile(r"TR-?(\d+)")


def _ids(raw: list) -> list:
    """Numery wersji z argumentów: „tr-1”, „TR-001” i „TR-001,TR-002” dają TR-001, TR-002 (bez powtórek)."""
    out = []
    for chunk in raw:
        for part in re.split(r"[,\s]+", chunk.strip()):
            if not part:
                continue
            match = ID_PATTERN.fullmatch(part.upper())
            vid = "TR-%03d" % int(match.group(1)) if match else part.upper()
            if vid not in out:
                out.append(vid)
    return out


def _version(st: dict, vid: str) -> dict:
    v = st["versions"].get(vid)
    if v is None:
        raise config.UserError("Nie ma wersji %s. Numery wersji pokazuje komenda status." % vid)
    return v


def _label(status: str) -> str:
    return config.STATUS_LABEL.get(status, status)


def _plan_table(rows: list, reels: dict) -> str:
    return table(["Termin", "Rolka", "Poziom", "Hook"],
                 [[versions.slot_label(t), versions.reel_name(reels, code)[:30], config.LEVEL_LABEL[level],
                   " ".join(x for x in (hook["text"], hook.get("emoji")) if x)] for t, code, level, hook in rows])


def _need_pool() -> None:
    if not any(r.get("active", True) for r in versions.pool_list()):
        raise config.UserError("Pula jest pusta albo wszystkie rolki są wyłączone. Najpierw dodaj rolki komendą pula.")


def cmd_pierwsze(args: argparse.Namespace) -> int:
    _need_pool()
    failed, hint = [], None
    with state.locked() as st:
        waiting = sum(1 for v in st["versions"].values() if v["status"] in ("do_akceptacji", "zaakceptowana"))
        need = args.ile - waiting
        if need <= 0:
            say("Masz już komplet wersji do akceptacji (jest ich %d, cel to %d), więc nowych nie robię." % (waiting, args.ile))
        else:
            rows = versions.plan_rows(st, versions.PLAN_DAYS_FIRST, limit=need)
            if not rows:
                raise config.UserError("Nie ma wolnych terminów w najbliższym tygodniu, więc nie mam gdzie ułożyć "
                                       "wersji.")
            say("Robię wersje do akceptacji (bez wysyłki do Zernio). Liczba wersji: %d. Każda renderuje się "
                "chwilę, więc to potrwa." % len(rows))
            failed = versions.make_versions(st, rows, "do_akceptacji", upload=False)["failed"]
        ready = sum(1 for v in st["versions"].values() if v["status"] == "do_akceptacji")
        hint = versions.daily_hint(st)
    say("")
    say("Gotowe. Wersji do akceptacji: %d." % ready)
    if failed:
        warn("Nie udało się zrobić wersji: %s (powody są wyżej). Ich terminy są znów wolne, więc uruchom pierwsze "
             "jeszcze raz, gdy poprawisz przyczynę." % ", ".join(failed))
    if hint:
        say(hint)
    if ready:
        cmd_podglad(argparse.Namespace(wszystkie=False))
    return 1 if failed else 0


def cmd_podglad(args: argparse.Namespace) -> int:
    st = state.load()
    if args.wszystkie:
        shown = versions.recent(st, PREVIEW_DAYS)
    else:
        shown = sorted((v for v in st["versions"].values() if v["status"] == "do_akceptacji"), key=versions.by_slot)
    if not shown:
        say("Nie ma wersji z ostatnich %d dni." % PREVIEW_DAYS if args.wszystkie else
            "Nie ma wersji do akceptacji. Żeby zobaczyć wszystkie wersje z ostatnich %d dni, użyj podglad --wszystkie."
            % PREVIEW_DAYS)
        return 0
    path = preview.build(shown, versions.pool(), config.DATA / "podglad.html")
    say("Podgląd gotowy. Wersji na stronie: %d. Plik: %s" % (len(shown), path))
    if preview.open_in_browser(path):
        say("Otworzyłem go w przeglądarce.")
    else:
        say("Nie udało się otworzyć przeglądarki. Otwórz ten plik ręcznie (dwukrotne kliknięcie w folderze dane).")
    return 0


def cmd_akceptuj(args: argparse.Namespace) -> int:
    if args.wszystkie and args.ids:
        raise config.UserError("Podaj albo numery wersji, albo --wszystkie, nie oba naraz.")
    if not args.wszystkie and not args.ids:
        raise config.UserError("Podaj numery wersji (na przykład akceptuj TR-001 TR-002) albo --wszystkie.")
    accepted, problems = [], []
    with state.locked() as st:
        if args.wszystkie:
            ids = [v["id"] for v in sorted(st["versions"].values(), key=versions.by_slot) if v["status"] == "do_akceptacji"]
        else:
            ids = _ids(args.ids)
        for vid in ids:
            v = _version(st, vid)
            if v["status"] == "do_akceptacji":
                v["status"] = "zaakceptowana"
                accepted.append(vid)
            elif v["status"] == "zaakceptowana":
                say("%s już jest zaakceptowana." % vid)
            else:
                problems.append(vid)
                say("%s ma status %s, więc jej nie akceptuję. Nowe wersje zrobisz komendą pierwsze."
                    % (vid, _label(v["status"])))
    if accepted:
        say("Zaakceptowane: %s. Następny krok to zaplanuj, ale dopiero po wyraźnej zgodzie klienta na pokazane terminy "
            "(zaplanuj --na-sucho pokaże je bez wysyłki do Zernio)." % ", ".join(accepted))
    elif not problems:
        say("Nie ma wersji do akceptacji.")
    return 1 if problems else 0


def cmd_odrzuc(args: argparse.Namespace) -> int:
    rejected, problems = [], []
    with state.locked() as st:
        for vid in _ids(args.ids):
            v = _version(st, vid)
            if v["status"] in ("do_akceptacji", "zaakceptowana", "blad"):
                v["status"] = "odrzucona"
                if args.powod:
                    v["note"] = args.powod.strip()
                rejected.append(vid)
            elif v["status"] == "odrzucona":
                say("%s już jest odrzucona." % vid)
            else:
                problems.append(vid)
                say("%s jest już w Zernio (status: %s), więc nie odrzucę jej tutaj. Post usuniesz w panelu Zernio."
                    % (vid, _label(v["status"])))
    if rejected:
        say("Odrzucone: %s. Terminy odrzuconych wersji są znów wolne, więc nowe wersje zrobisz komendą pierwsze."
            % ", ".join(rejected))
    return 1 if problems else 0


def cmd_zaplanuj(args: argparse.Namespace) -> int:
    ids = _ids(args.ids) if args.ids else None
    dry = args.na_sucho
    with (contextlib.nullcontext(state.load()) if dry else state.locked()) as st:
        for vid in ids or []:
            _version(st, vid)
        result = versions.schedule_accepted(st, ids, dry_run=dry)
        waiting = sum(1 for v in st["versions"].values() if v["status"] == "do_akceptacji")
    if not result["eligible"] and not result["refused"]:
        say("Nie ma zaakceptowanych wersji do zaplanowania."
            + (" Wersje czekają na akceptację klienta: gdy obejrzy podgląd i wyraźnie napisze „akceptuję”, uruchom "
               "akceptuj --wszystkie albo akceptuj TR-001 TR-002." if waiting else ""))
        return 0
    if dry:
        say("Na sucho: zaplanowałbym %d z %d. Nic nie wysłałem i nic nie zmieniłem." % (result["done"], result["eligible"]))
        if result["clashes"]:
            say(versions.clash_hint(result["clashes"]))
        return 1 if result["refused"] else 0
    say("Zaplanowane w Zernio: %d z %d." % (result["done"], result["eligible"]))
    if result["clashes"]:
        say(versions.clash_hint(result["clashes"]))
    return 1 if result["failed"] or result["refused"] or result["done"] < result["eligible"] else 0


def _parse_start(text: str):
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").replace(tzinfo=planner.TZ)
    except ValueError:
        raise config.UserError("Zła data początku: %s. Wpisz ją w formie RRRR-MM-DD, na przykład 2026-11-23." % text) from None


def _before_first_planning(st: dict, dry: bool) -> None:
    """Prawdziwa paczka rusza dopiero po pierwszym zaplanowaniu w Zernio. Plan na sucho mówi, czego brakuje."""
    accepted = any(v["status"] == "zaakceptowana" for v in st["versions"].values())
    if not dry:
        raise config.UserError(
            "Najpierw krok 8: pierwsze wersje do akceptacji. Paczka tygodniowa rusza dopiero wtedy, gdy "
            "zaakceptujesz pierwsze wersje i zaplanujesz je w Zernio (komendy pierwsze, akceptuj, zaplanuj)."
            + (" Masz już zaakceptowane wersje: następny krok to zaplanuj, po zgodzie klienta na pokazane terminy."
               if accepted else ""))
    if accepted:
        say("Uwaga: to tylko podgląd planu. Prawdziwa paczka ruszy dopiero wtedy, gdy pierwsze wersje trafią do Zernio. "
            "Masz już zaakceptowane wersje, więc brakuje tylko zaplanuj, po zgodzie klienta na pokazane terminy.")
    else:
        say("Uwaga: to tylko podgląd planu. Prawdziwa paczka ruszy dopiero wtedy, gdy zrobisz krok 8: pierwsze "
            "wersje do akceptacji.")


def _before_the_decision(waiting: list, dry: bool) -> None:
    """Prawdziwa paczka rusza dopiero, gdy klient zdecydował o każdej z pierwszych wersji. Inaczej zaakceptowanie jednej
    z dziewięciu odblokowywałoby ok. 70 wersji tygodniowo, których reszty klient nigdy nie obejrzał."""
    what = "%s na akceptację klienta (%s)" % (versions.versions_wait(len(waiting)), ", ".join(v["id"] for v in waiting))
    if not dry:
        raise config.UserError("Paczka czeka na decyzję o pierwszych wersjach: %s. Gdy klient obejrzy podgląd i wyraźnie "
                               "napisze „akceptuję”, uruchom akceptuj (albo odrzuć niechciane wersje komendą odrzuc ID), "
                               "a paczka ruszy." % what)
    say("Uwaga: to tylko podgląd planu. Prawdziwa paczka ruszy dopiero, gdy klient zdecyduje o każdej z pierwszych wersji, "
        "a teraz %s: gdy wyraźnie napisze „akceptuję” albo wskaże wersje do odrzucenia, paczka ruszy." % what)


def _dry_run_plan(rows: list, reels: dict, clashes: list) -> None:
    """Plan na sucho dla `rows`: pyta Zernio (tylko odczyt) o zajęte terminy i mówi, co zrobiłaby prawdziwa paczka."""
    taken = versions.plan_clashes(rows)
    for t, code, _, _ in taken:
        say("  ! %s (%s): na ten termin masz już inny post na Instagramie. Pomijam ten termin."
            % (versions.slot_label(t), versions.reel_name(reels, code)))
    say("")
    say("Na sucho: zaplanowałbym %d z %d. Nic nie wysłałem i nic nie zmieniłem." % (len(rows) - len(taken), len(rows)))
    if taken and not clashes:      # wersje już zrobione i pominięte mają własną wskazówkę, z numerami do odrzucenia
        say(versions.clash_hint([]))


def cmd_paczka(args: argparse.Namespace) -> int:
    start = _parse_start(args.start) if args.start else None
    versions.account_id()
    _need_pool()
    dry = args.na_sucho
    failed, clashes, rows = [], [], []
    with (contextlib.nullcontext(state.load()) if dry else state.locked()) as st:
        started = versions.started(st)
        if not started:
            _before_first_planning(st, dry)
        else:
            waiting_for_review = versions.waiting_for_review(st)
            if waiting_for_review:
                _before_the_decision(waiting_for_review, dry)
        brake = versions.check_brake(st)
        waiting = [v for v in st["versions"].values() if v["status"] == "zaakceptowana" and not v.get("zernio_post_id")]
        if waiting and started:        # także na sucho: prawdziwa paczka zaczyna od dokończenia takich wersji
            say("%s zaakceptowane wersje, które nie trafiły jeszcze do Zernio: %d."
                % ("Dokończyłbym" if dry else "Dokańczam", len(waiting)))
            finished = versions.schedule_accepted(st, None, dry_run=dry)
            failed += finished["failed"]
            clashes += finished["clashes"]
        free = versions.free_slots(st, args.dni, start)
        rows = versions.plan_rows(st, args.dni, start)
        reels = versions.pool()
        say("Hamulec: %s. Wersji w planie: %d. Wolnych terminów: %d."
            % ("włączony, 1 trial dziennie" if brake.get("on") else "wyłączony", len(rows), len(free)))
        if rows:
            say(_plan_table(rows, reels))
        elif not dry:
            say("Nie ma wolnych terminów w wybranym okresie (--dni %d). Nic nie robię." % args.dni)
        if dry and rows:
            _dry_run_plan(rows, reels, clashes)
        if not dry and rows:
            made = versions.make_versions(st, rows, "zaakceptowana", upload=True)
            failed += made["failed"]
            clashes += made["clashes"]
            say("")
            say("Gotowe. Zaplanowane w Zernio: %d. Nie udało się: %d. Pominięte: %d." % (
                len(made["done"]), len(made["failed"]), len(made["skipped"])))
            retry = [vid for vid in made["skipped"] if vid not in made["clashes"]]
            if retry:   # po ponowieniu cudzy post nadal by tam stał, więc o nim mówi wskazówka niżej, a nie obietnica
                say("Pominięte wersje (%s) zostają zaakceptowane, a następne uruchomienie spróbuje je dokończyć."
                    % ", ".join(retry))
        if clashes:
            say(versions.clash_hint(clashes))
        low = versions.hook_bank_low(st, rows if dry else ())
        hint = versions.daily_hint(st)
    if low:
        say("Bank hooków prawie pusty: %s. To w porządku, idą powtórki najlepszych hooków." % ", ".join(low))
    if hint:
        say(hint)
    return 1 if failed else 0


def cmd_sprawdz(args: argparse.Namespace) -> int:
    with state.locked() as st:
        counts = versions.verify(st)
        removed = versions.cleanup(st)
    say("Sprawdzone wersje: %d. Opublikowane: %d. Błędy: %d. Czekają na publikację: %d. Usunięte pliki starych wersji: %d."
        % (counts["sprawdzone"], counts["opublikowana"], counts["blad"], counts["czeka"], removed))
    return 0


def cmd_do_odczytu(args: argparse.Namespace) -> int:
    items = stats.todo(state.load()["versions"], versions.now(), sample=args.probka)
    if not items:
        say("Nie ma wersji do odczytu: czytamy opublikowane triale sprzed co najmniej %d dni, nie starsze niż %d dni "
            "i nie czytane w ostatnich %d dniach." % (config.STATS_MIN_AGE_DAYS, stats.MAX_AGE_DAYS, stats.FRESH_DAYS))
        return 0
    # Próbka (po jednym adresie na rolkę) jest krótka sama z siebie. Pełna lista rośnie z każdym tygodniem, więc ją tniemy.
    shown = items if args.probka else items[:DUE_LIMIT]
    for item in shown:
        say("%s  %s" % (item["id"], item["url"]))
    if len(shown) < len(items):
        say("Pominięte: %d. Ta lista ma najwyżej %d adresów. Gdy zapiszesz wyniki z niej, uruchom do-odczytu jeszcze raz, "
            "a pokaże kolejne. Po jednym adresie na rolkę (jej najnowsza wersja) da do-odczytu --probka."
            % (len(items) - len(shown), DUE_LIMIT))
    return 0


def cmd_zapisz_wynik(args: argparse.Namespace) -> int:
    try:
        views = stats.parse_count(args.wyswietlenia)
        follows = stats.parse_count(args.obserwujacy)
    except ValueError as e:
        raise config.UserError(str(e)) from None
    ids = _ids([args.id])
    if len(ids) != 1:
        raise config.UserError("Podaj numer jednej wersji, na przykład TR-001.")
    vid = ids[0]
    with state.locked() as st:
        v = _version(st, vid)
        if v["status"] != "opublikowana":
            warn("Uwaga: %s ma status %s, a nie Opublikowana. Zapisuję wynik, ale sprawdź, czy to na pewno ta wersja."
                 % (vid, _label(v["status"])))
        v.update(views=views, follows=follows, read_at=versions.now().strftime("%Y-%m-%dT%H:%M"))
    say("%s: %s wyświetleń, %s obserwujących." % (vid, thousands(views), thousands(follows)))
    return 0


def cmd_hamulec(args: argparse.Namespace) -> int:
    with state.locked() as st:
        brake = versions.check_brake(st)
    ratio, on = brake.get("ratio"), brake.get("on")
    if ratio is None:        # za mało zwykłych rolek: włączony hamulec zostaje, wyłączony nie ma jak się włączyć
        why = ("za mało danych: potrzeba co najmniej %d zwykłych rolek z 28 dni przed startem triali i %d z ostatnich "
               "dwóch tygodni (liczą się rolki z co najmniej %d wyświetleń)"
               % (planner.BRAKE_MIN_BASE, planner.BRAKE_MIN_RECENT, planner.MIN_VIEWS))
        say("Hamulec: WŁĄCZONY, 1 trial dziennie (zostaje, bo %s, żeby sprawdzić, czy zasięg wrócił)." % why if on else
            "Hamulec: wyłączony (nieaktywny: %s, żeby policzyć spadek zasięgu)." % why)
        return 0
    say("Hamulec: %s (zwykłe rolki: mediana od startu triali do mediany z 28 dni przed startem = %s)."
        % ("WŁĄCZONY, 1 trial dziennie" if on else "wyłączony", ("%.2f" % ratio).replace(".", ",")))
    return 0


def cmd_raport(args: argparse.Namespace) -> int:
    text = versions.report_text(state.load())
    path = config.REPORTS / ("%s.md" % versions.now().strftime("%Y-%m-%d"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    say(text)
    say("Raport zapisany: %s" % path)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    st = state.load()
    everything = sorted(st["versions"].values(), key=versions.id_number)
    if not everything:
        say("Nie ma jeszcze żadnych wersji. Zacznij od komendy pierwsze.")
        return 0
    # Po kilku tygodniach wersji są setki, a ta komenda jest wołana często: domyślnie tylko ostatnie dni i błędy,
    # bo alert „N wersji z błędem” obiecuje, że status pokaże, które to.
    keep = {v["id"] for v in versions.recent(st, PREVIEW_DAYS)} | {v["id"] for v in versions.open_errors(st)}
    items = everything if args.wszystkie else [v for v in everything if v["id"] in keep]
    reels = versions.pool()
    counts = Counter(v["status"] for v in everything)
    parts = ", ".join("%s: %d" % (_label(key).lower(), counts[key]) for key in config.STATUS_LABEL if counts[key])
    brake = st.get("brake", {})
    say("Wersji: %d (%s). Hamulec: %s." % (len(everything), parts, "włączony, 1 trial dziennie" if brake.get("on") else "wyłączony"))
    if not items:
        say("W ostatnich %d dniach nie ma wersji. Wszystkie pokaże komenda status --wszystkie." % PREVIEW_DAYS)
        return 0
    if len(items) < len(everything):
        say("Pokazuję %d z %d wersji: z ostatnich %d dni i te z błędem. Wszystkie pokaże komenda status --wszystkie."
            % (len(items), len(everything), PREVIEW_DAYS))
    say("")
    say(table(["Wersja", "Termin", "Rolka", "Poziom", "Status", "Wyświetlenia", "Obserwujący"],
              [[v["id"], versions.slot_label(v.get("slot")), versions.reel_name(reels, v["code"])[:30],
                config.LEVEL_LABEL.get(v["level"], v["level"]),
                _label(v["status"]) + (" (zastąpiona %s)" % v["replaced_by"] if v.get("replaced_by") else ""),
                thousands(v["views"]) if v.get("views") is not None else "-",
                thousands(v["follows"]) if v.get("follows") is not None else "-"] for v in items], right=(5, 6)))
    return 0


# --- komendy: kreator i aktualizacje --------------------------------------------

def cmd_krok(args: argparse.Namespace) -> int:
    if args.gotowe is not None:
        key = wizard.resolve(args.gotowe)
        if key not in wizard.ENTRY_STEPS:      # takie kroki liczą się z plików, więc zapis nic by nie dał i go nie robimy
            warn("Nic nie zapisałem: krok „%s” sprawdzam sam, z plików w folderze dane (albo doktorem), więc ręczny "
                 "zapis niczego by nie zmienił. Ręcznie oznacza się tylko kroki: %s."
                 % (wizard.TITLES[key], ", ".join(wizard.ENTRY_STEPS)))
            return 0
        key, value = wizard.mark(key, args.wartosc)
        say("Zapisałem krok „%s”: %s." % (wizard.TITLES[key], value))
        return 0
    if args.wartosc is not None:
        raise config.UserError("Opcja --wartosc działa tylko razem z --gotowe ID, na przykład krok --gotowe pomiar "
                               "--wartosc reczny.")
    say(json.dumps(wizard.status(now()), ensure_ascii=False, indent=2))
    return 0


def _forget_new_version() -> None:
    """Kasuje z kreatora zapis o nowej wersji. Uszkodzony plik kreatora nie może zatrzymać aktualizacji: nieaktualny
    zapis i tak niczego nie pokaże (kreator porównuje go z obecną wersją)."""
    try:
        wizard.forget("nowa_wersja")
    except (config.UserError, json.JSONDecodeError, OSError):
        pass


def cmd_aktualizuj(args: argparse.Namespace) -> int:
    if args.sprawdz and args.tak:
        raise config.UserError("Użyj albo --sprawdz (tylko sprawdzam, czy jest nowa wersja), albo --tak (aktualizuję). "
                               "Naraz się nie da.")
    info = update.latest()
    tag = info["tag"]
    if not update.newer(tag, VERSION):
        _forget_new_version()
        say("Masz najnowszą wersję programu (%s)." % VERSION)
        return 0
    say("Jest nowa wersja %s. Masz %s." % (tag, VERSION))
    notes = update.format_notes(info["notes"])
    if notes:
        say("")
        say("Co nowego:")
        say(notes)
        say("")
    if args.sprawdz:
        wizard.remember("nowa_wersja", tag)
        say("Zapisałem w kreatorze, że jest nowa wersja. Zaktualizujesz ją komendą aktualizuj --tak.")
        return 0
    if not args.tak:
        say("Żeby zaktualizować, uruchom komendę aktualizuj --tak. Twoje dane w folderze dane zostaną nietknięte.")
        return 0
    say("Pobieram wersję %s i podmieniam kod programu." % tag)
    result = update.upgrade(info, config.ROOT)
    _forget_new_version()
    say("Zaktualizowane do wersji %s. Zmienione pliki: %d, usunięte: %d. Twoje dane w folderze dane są nietknięte."
        % (update.installed_version(config.ROOT), result["zmienione"], len(result["usuniete"])))
    if result["wymagania"]:
        say("Zmieniły się wymagane pakiety, więc je doinstalowuję. To może potrwać kilka minut.")
        update.install_requirements(config.ROOT)
        say("Pakiety są gotowe.")
    say("Sprawdzam komputer doktorem.")
    if update.run_doctor(config.ROOT) != 0:
        warn("Doktor zgłosił problemy (wyżej). Pliki programu są już zaktualizowane. Popraw to, co pokazał doktor, "
             "i uruchom komendę doktor jeszcze raz.")
        return 1
    return 0


# --- parser i wejście -----------------------------------------------------------

def _positive(text: str) -> int:
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("to ma być liczba całkowita") from None
    if number < 1:
        raise argparse.ArgumentTypeError("liczba musi być większa od zera")
    return number


def _months(text: str) -> int:
    number = _positive(text)
    if number > 72:
        raise argparse.ArgumentTypeError("najwyżej 72 miesiące")
    return number


def _days(text: str) -> int:
    number = _positive(text)
    if number > 31:
        raise argparse.ArgumentTypeError("najwyżej 31 dni")
    return number


def _seconds(text: str) -> float:
    try:
        number = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("to ma być liczba sekund, np. 1.0") from None
    if number < 0:
        raise argparse.ArgumentTypeError("czas nie może być ujemny")
    return number


class _Parser(argparse.ArgumentParser):
    """Bez skrótów opcji: `--ta` nie może zadziałać jak `--tak` i ominąć pytania o zgodę."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    """Parser komend. Każda nowa komenda dodaje tu swoją podkomendę i ustawia `func`."""
    parser = _Parser(
        prog="trial",
        description="Trial reels: planer i montaż próbnych rolek na Instagramie.",
    )
    sub = parser.add_subparsers(dest="komenda", metavar="komenda")

    sub.add_parser("wersja", help="pokaż numer wersji").set_defaults(func=cmd_wersja)
    sub.add_parser("doktor", help="sprawdź, czy komputer jest gotowy").set_defaults(func=cmd_doktor)
    sub.add_parser("klucz", help="utwórz dane/.env i otwórz go w edytorze, żeby wkleić klucz Zernio").set_defaults(
        func=cmd_klucz)

    konto = sub.add_parser("konto", help="wybierz konto Instagrama z Zernio")
    konto.add_argument("--nick", help="nick konta, gdy w Zernio jest ich kilka (z @ albo bez)")
    konto.set_defaults(func=cmd_konto)

    kandydaci = sub.add_parser("kandydaci", help="znajdź rolki, z których zrobimy triale")
    kandydaci.add_argument("--miesiace", type=_months, default=12, help="z ilu ostatnich miesięcy (domyślnie 12)")
    kandydaci.add_argument("--ile", type=_positive, default=25, help="ilu kandydatów (domyślnie 25)")
    kandydaci.set_defaults(func=cmd_kandydaci)

    wynik = sub.add_parser("wynik-kandydata", help="zapisz odczyt z panelu IG: wyświetlenia i obserwujących rolki")
    wynik.add_argument("kod", help="kod rolki albo jej adres")
    wynik.add_argument("--wyswietlenia", required=True, help="liczba z panelu, np. 1234 albo 12,3 tys.")
    wynik.add_argument("--obserwujacy", required=True, help="liczba z panelu, np. 9")
    wynik.set_defaults(func=cmd_wynik_kandydata)

    sub.add_parser("js-odczyt", help="wypisz skrypt do odczytu panelu IG w przeglądarce").set_defaults(
        func=cmd_js_odczyt)

    pula = sub.add_parser("pula", help="dodaj kandydatów do puli albo pokaż pulę")
    pula.add_argument("kody", nargs="*", metavar="KOD", help="kody rolek albo ich adresy")
    pula.add_argument("--auto", nargs="?", const=12, type=_positive, metavar="N",
                      help="dopełnij pulę do N rolek według obserwujących (bez liczby: 12)")
    pula.set_defaults(func=cmd_pula)

    sub.add_parser("pobierz", help="pobierz pliki rolek z Zernio").set_defaults(func=cmd_pobierz)
    sub.add_parser("transkrybuj", help="zrób transkrypcje rolek").set_defaults(func=cmd_transkrybuj)
    sub.add_parser("sprawdz-pule", help="sprawdź, czy pula jest gotowa do renderu").set_defaults(func=cmd_sprawdz_pule)

    kadr = sub.add_parser("kadr", help="zrób klatkę rolki z próbnym hookiem")
    kadr.add_argument("kod", help="kod rolki z puli albo jej adres")
    which = kadr.add_mutually_exclusive_group()
    which.add_argument("--hook", help="tekst hooka (domyślnie pierwszy z banku rolki)")
    which.add_argument("--hook-id", metavar="ID",
                       help="hook z dane/hooki.json, np. h03: tekst i emotka z pliku, bez wpisywania ich w komendzie")
    kadr.add_argument("--emoji", help="emotka z zestawu assets/emoji")
    kadr.add_argument("--t", type=_seconds, default=1.0, help="sekunda filmu, z której bierzemy klatkę (domyślnie 1.0)")
    kadr.set_defaults(func=cmd_kadr)

    pierwsze = sub.add_parser("pierwsze", help="zrób pierwsze wersje do akceptacji (sam render, bez wysyłki do Zernio)")
    pierwsze.add_argument("--ile", type=_positive, default=FIRST_BATCH,
                          help="ile wersji ma czekać na akceptację (domyślnie %d)" % FIRST_BATCH)
    pierwsze.set_defaults(func=cmd_pierwsze)

    podglad = sub.add_parser("podglad", help="otwórz w przeglądarce stronę z wersjami do obejrzenia")
    podglad.add_argument("--wszystkie", action="store_true", help="pokaż wszystkie wersje z ostatnich 14 dni")
    podglad.set_defaults(func=cmd_podglad)

    akceptuj = sub.add_parser("akceptuj", help="zaakceptuj wersje do zaplanowania")
    akceptuj.add_argument("ids", nargs="*", metavar="ID", help="numery wersji, np. TR-001 TR-002")
    akceptuj.add_argument("--wszystkie", action="store_true", help="zaakceptuj wszystkie wersje czekające na akceptację")
    akceptuj.set_defaults(func=cmd_akceptuj)

    odrzuc = sub.add_parser("odrzuc", help="odrzuć wersje (ich terminy znów będą wolne)")
    odrzuc.add_argument("ids", nargs="+", metavar="ID", help="numery wersji, np. TR-003")
    odrzuc.add_argument("--powod", help="krótki powód, zapisany przy wersji")
    odrzuc.set_defaults(func=cmd_odrzuc)

    zaplanuj = sub.add_parser("zaplanuj", help="zaplanuj zaakceptowane wersje w Zernio jako triale")
    zaplanuj.add_argument("ids", nargs="*", metavar="ID", help="numery wersji (bez nich: wszystkie zaakceptowane)")
    zaplanuj.add_argument("--na-sucho", action="store_true", help="pokaż, co by się stało, ale niczego nie wysyłaj")
    zaplanuj.set_defaults(func=cmd_zaplanuj)

    paczka = sub.add_parser("paczka", help="zrób i zaplanuj paczkę wersji na najbliższe dni")
    paczka.add_argument("--dni", type=_days, default=7, help="na ile dni (domyślnie 7)")
    paczka.add_argument("--start", metavar="RRRR-MM-DD", help="pierwszy dzień planu (domyślnie: najbliższe terminy)")
    paczka.add_argument("--na-sucho", action="store_true", help="pokaż plan, ale niczego nie renderuj ani nie wysyłaj")
    paczka.set_defaults(func=cmd_paczka)

    sub.add_parser("sprawdz", help="sprawdź w Zernio, co już wyszło, i posprzątaj stare pliki").set_defaults(
        func=cmd_sprawdz)

    odczyt = sub.add_parser("do-odczytu", help="wypisz adresy paneli IG, z których trzeba odczytać wyniki")
    odczyt.add_argument("--probka", action="store_true", help="tylko najnowszy trial każdej rolki (odczyt ręczny)")
    odczyt.set_defaults(func=cmd_do_odczytu)

    wynik_wersji = sub.add_parser("zapisz-wynik", help="zapisz odczyt z panelu IG: wyświetlenia i obserwujących wersji")
    wynik_wersji.add_argument("id", help="numer wersji, np. TR-001")
    wynik_wersji.add_argument("--wyswietlenia", required=True, help="liczba z panelu, np. 1234 albo 12,3 tys.")
    wynik_wersji.add_argument("--obserwujacy", required=True, help="liczba z panelu, np. 9")
    wynik_wersji.set_defaults(func=cmd_zapisz_wynik)

    sub.add_parser("hamulec", help="policz hamulec (spadek zasięgu zwykłych rolek)").set_defaults(func=cmd_hamulec)
    sub.add_parser("raport", help="zrób raport tygodniowy i zapisz go w dane/raporty").set_defaults(func=cmd_raport)
    status = sub.add_parser("status", help="pokaż listę wersji i ich statusy (domyślnie z ostatnich 14 dni)")
    status.add_argument("--wszystkie", action="store_true", help="pokaż wszystkie wersje, nie tylko z ostatnich 14 dni")
    status.set_defaults(func=cmd_status)

    krok = sub.add_parser("krok", help="pokaż stan kroków kreatora (JSON) albo zapisz krok jako zrobiony")
    krok.add_argument("--gotowe", metavar="ID", help="zapisz krok jako zrobiony, np. powitanie")
    krok.add_argument("--wartosc", metavar="W", help="wartość zapisana przy kroku (domyślnie „tak”), np. chrome albo reczny")
    krok.set_defaults(func=cmd_krok)

    aktualizuj = sub.add_parser("aktualizuj", help="sprawdź, czy jest nowa wersja programu, i zainstaluj ją po zgodzie")
    aktualizuj.add_argument("--sprawdz", action="store_true",
                            help="tylko sprawdź i zapisz w kreatorze, że jest nowa wersja (niczego nie instaluje)")
    aktualizuj.add_argument("--tak", action="store_true",
                            help="pobierz i zainstaluj nową wersję (bez tego pokazuję tylko, co się zmieniło)")
    aktualizuj.set_defaults(func=cmd_aktualizuj)
    return parser


def _utf8_output() -> None:
    """Polskie znaki na wyjściu także bez PYTHONUTF8 (np. Python uruchomiony z pominięciem trial.cmd na Windowsie)."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "").replace("_", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0
    try:
        try:
            zone, readable = config.settings()["timezone"], True
        except Exception as e:               # plik ustawień jest uszkodzony: wybrane komendy idą dalej w strefie domyślnej
            if args.komenda not in SETTINGS_FREE_COMMANDS or explain(e) is None:
                raise
            zone, readable = None, False
        if readable:
            try:
                planner.set_tz(zone)
            except config.ZONE_ERRORS:       # strefa zostaje poprzednia (domyślna), bo set_tz niczego nie zmienia
                if args.komenda not in SETTINGS_FREE_COMMANDS:
                    warn(config.zone_problem(zone))
                    return 2
        return int(func(args) or 0)
    except KeyboardInterrupt:
        warn("Przerwano.")
        return 130
    except Exception as e:
        message = explain(e)
        if message is None:
            raise
        warn(message)
        return 1


if __name__ == "__main__":
    sys.exit(main())
