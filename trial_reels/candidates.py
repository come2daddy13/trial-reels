"""Kandydaci na zwycięskie rolki, wpisy puli i sprawdzanie puli przed renderem.

Kandydaci powstają z odpowiedzi Zernio `GET /analytics`. Każdy post ma m.in. `platformPostUrl`, `content`,
`publishedAt`, `isAd`, `isSharedToFeed`, `mediaProductType`, `mediaItems[]` i `analytics{views, likes, comments,
shares, saves, …}`. Pula (`dane/pula.json`) to lista rolek, z których powstają triale, a `dane/hooki.json` to banki
hooków w układzie {kod rolki: [hooki]}.

Ten moduł nie ładuje od razu PIL ani PyAV (robi to dopiero `validate`), więc komendy, które ich nie potrzebują,
a przede wszystkim `doktor`, działają także na zepsutej instalacji.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from . import captions, config

# Alfabet kodu rolki w adresie. Kod to liczba zapisana w systemie o podstawie 64 (ID mediów Instagrama).
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
IG_EPOCH_MS = 1314220021721  # od tej chwili (24.08.2011) liczą czas górne bity ID mediów

CAPTION_MAX = 2200      # tyle znaków przyjmuje podpis na Instagramie
HOOK_MAX = 50
MIN_HOOKS = 3
MIN_EXTRAS = 4
CAPTIONS_MAX_CHECKED = 600   # górna granica sprawdzanych podpisów (zwykle wystarcza okres rotacji, patrz captions.period)
NAME_WORDS, NAME_CHARS = 5, 40

_CODE = r"[A-Za-z0-9_-]{6,64}"
_URL_CODE = re.compile(r"/(?:reels?|p|tv)/(%s)(?:[/?#]|$)" % _CODE)
_BARE_CODE = re.compile(_CODE)
_EMOJI_PARTS = frozenset("\ufe0e\ufe0f\u200d\u20e3")  # selektory wariantu, łącznik, ramka klawisza


# --- kod rolki i ID mediów ------------------------------------------------------

def valid_code(code) -> bool:
    """Czy napis wygląda na kod rolki: od 6 do 64 liter, cyfr, „-” albo „_” (taki sam kod stoi w adresie rolki).

    Kod trafia do nazw plików (dane/src/<kod>.mp4), więc wpis z czymś innym, na przykład z całym adresem, odrzucamy.
    """
    return isinstance(code, str) and _BARE_CODE.fullmatch(code) is not None


def shortcode(url) -> str | None:
    """Kod rolki z adresu (…/reel/KOD/, …/reels/KOD/, …/p/KOD/, także z nickiem i parametrami) albo sam kod.

    Zwraca None, gdy napis nie wygląda na rolkę.
    """
    if not isinstance(url, str):
        return None
    text = url.strip()
    found = _URL_CODE.search(text)
    if found:
        return found.group(1)
    return text if valid_code(text) else None


def media_id(url) -> str | None:
    """ID mediów rolki (liczba jako napis), czyli jej kod odczytany w systemie o podstawie 64. None, gdy to nie rolka."""
    code = shortcode(url)
    if not code:
        return None
    n = 0
    for ch in code:
        n = n * 64 + ALPHA.index(ch)
    return str(n)


def created_at(pk) -> datetime | None:
    """Kiedy powstała rolka, odczytane z jej ID mediów (górne bity to milisekundy od 24.08.2011), w UTC.

    None, gdy ID nie jest liczbą albo wychodzi z niego data sprzed 2012 roku, czyli nie jest to ID rolki.
    """
    try:
        when = datetime.fromtimestamp(((int(pk) >> 23) + IG_EPOCH_MS) / 1000, timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return when if when.year >= 2012 else None


# --- napisy i emotki ------------------------------------------------------------

def _is_emoji_part(ch: str) -> bool:
    """Znak emotki: symbol (kategoria So), modyfikator koloru skóry, flaga w znacznikach, selektor wariantu, łącznik."""
    cp = ord(ch)
    return (ch in _EMOJI_PARTS or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F
            or unicodedata.category(ch) == "So")


def strip_emoji(text: str) -> str:
    """Tekst bez emotek (kolejne spacje zostają, więc przed dalszą obróbką użyj `split()`)."""
    return "".join(ch for ch in str(text or "") if not _is_emoji_part(ch))


def preview(text: str, limit: int = 40) -> str:
    """Początek podpisu do tabeli: bez emotek, w jednej linii, skrócony do `limit` znaków (z „…”)."""
    flat = " ".join(strip_emoji(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def short_name(caption: str) -> str:
    """Nazwa rolki z podpisu: pierwsze 5 słów bez emotek, najwyżej 40 znaków."""
    words = strip_emoji(caption).split()[:NAME_WORDS]
    return " ".join(words)[:NAME_CHARS].rstrip()


# --- wybór kandydatów -----------------------------------------------------------

def media_url(post) -> str | None:
    """Adres pliku wideo rolki: `mediaItems[0].url` z odpowiedzi Zernio (None, gdy Zernio pliku nie ma)."""
    items = post.get("mediaItems") if isinstance(post, dict) else None
    if isinstance(items, list) and items and isinstance(items[0], dict):
        url = items[0].get("url")
        if isinstance(url, str) and url.strip():
            return url
    return None


def _count(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_time(value) -> datetime | None:
    """Czas z napisu ISO (z literą Z albo przesunięciem). Czas bez strefy uznajemy za UTC."""
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _candidate(post, latest: datetime) -> dict | None:
    """Kandydat z jednego posta albo None, gdy post odpada (nie rolka, reklama, wersja próbna, za świeży, bez kodu)."""
    if not isinstance(post, dict):
        return None
    if str(post.get("mediaProductType") or "").upper() != "REELS":
        return None
    if post.get("isSharedToFeed") is False:        # trial albo rolka tylko z zakładki Rolki: nie jest oryginałem
        return None
    if post.get("isAd"):
        return None
    if str(post.get("platform") or "instagram").lower() != "instagram":
        return None
    url = post.get("platformPostUrl")
    code = shortcode(url)
    published = parse_time(post.get("publishedAt"))
    if not code or published is None or published > latest:
        return None
    stats = post.get("analytics") if isinstance(post.get("analytics"), dict) else {}
    return {
        "code": code,
        "url": url,
        "pk": media_id(code),
        "views": _count(stats.get("views")),
        "likes": _count(stats.get("likes")),
        "comments": _count(stats.get("comments")),
        "shares": _count(stats.get("shares")),
        "saves": _count(stats.get("saves")),
        "published": post.get("publishedAt"),
        "caption": post.get("content") or "",
        "media_url": media_url(post),
    }


def select(posts, now: datetime, top: int = 25, min_age_days: int = 7) -> list[dict]:
    """Kandydaci na zwycięskie rolki z postów Zernio, od najczęściej oglądanej.

    Bierzemy tylko rolki IG (`mediaProductType` REELS), bez reklam i bez wersji próbnych (`isSharedToFeed` false),
    nie młodsze niż `min_age_days` (mniej wyświetleń nie ma wtedy jeszcze o czym świadczyć). Kod, który się
    powtarza, liczy się raz, z większą liczbą wyświetleń. `now` bez strefy czasowej uznajemy za UTC.
    """
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    latest = now - timedelta(days=min_age_days)
    best: dict[str, dict] = {}
    for post in posts or []:
        cand = _candidate(post, latest)
        if cand is None:
            continue
        known = best.get(cand["code"])
        if known is None or cand["views"] > known["views"]:
            best[cand["code"]] = cand
    return sorted(best.values(), key=lambda c: c["views"], reverse=True)[:top]


def rank(cands: list[dict]) -> tuple[list[dict], bool]:
    """Kolejność wyboru do puli: najpierw rolki z odczytem obserwujących (od największej liczby), potem po
    wyświetleniach.

    Drugi wynik mówi, czy jakakolwiek rolka ma odczyt obserwujących. Bez niego ranking idzie tylko po wyświetleniach,
    a to słabsza miara.
    """
    def key(c):
        follows = c.get("panel_follows")
        return (0 if follows is not None else 1, -(follows or 0), -(c.get("views") or 0))

    return sorted(cands, key=key), any(c.get("panel_follows") is not None for c in cands)


def pool_entry(c: dict) -> dict:
    """Wpis do puli z kandydata. Resztę pól (cta, extras, strong, cuts…) dopisuje się przy ustawianiu rolki."""
    caption = c.get("caption") or ""
    return {
        "code": c["code"],
        "name": short_name(caption) or c["code"],
        "media_id": c.get("pk") or media_id(c["code"]),
        "caption": caption,
        "active": True,
        "hook_y": 0.17,
    }


# --- pliki z danymi -------------------------------------------------------------

def _load(path, expected: type, shape: str):
    data = config.read_json(path, expected())
    if not isinstance(data, expected):
        raise config.UserError("Plik dane/%s ma zły układ: powinien zawierać %s. Napraw go albo usuń, a potem uruchom "
                               "komendę jeszcze raz." % (path.name, shape))
    return data


def load_pool() -> list:
    """Pula rolek z dane/pula.json (pusta lista, gdy pliku jeszcze nie ma)."""
    return _load(config.POOL, list, "listę rolek")


def save_pool(pool: list) -> None:
    config.write_json(config.POOL, pool)


def load_candidates() -> list:
    """Lista kandydatów z dane/kandydaci.json (pusta, gdy pliku jeszcze nie ma)."""
    return _load(config.CANDIDATES, list, "listę kandydatów")


def save_candidates(cands: list) -> None:
    config.write_json(config.CANDIDATES, cands)


def load_hooks() -> dict:
    """Banki hooków z dane/hooki.json w układzie {kod rolki: [hooki]} (pusty słownik, gdy pliku jeszcze nie ma)."""
    return _load(config.HOOKS, dict, "banki hooków (kod rolki i lista hooków)")


# --- sprawdzanie puli -----------------------------------------------------------

def reel_label(reel: dict) -> str:
    """„Rolka NAZWA (KOD)” albo „Rolka KOD”, gdy rolka nie ma nazwy: tak komunikaty nazywają rolkę."""
    name = reel.get("name")
    code = reel["code"]
    return "Rolka %s (%s)" % (name, code) if name and name != code else "Rolka %s" % code


def _quoted(text, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return "„%s”" % (text if len(text) <= limit else text[: limit - 1] + "…")


def speech_words(code: str) -> int | None:
    """Ile słów ma transkrypcja rolki. 0 to rolka bez mowy (muzyka, napisy na ekranie).

    None, gdy transkrypcji nie ma albo nie da się jej odczytać: o tym mówią inne kontrole, a rolki bez mowy po
    uszkodzonym pliku nie poznamy.
    """
    try:
        data = config.read_json(config.TRANSCRIPTS / ("%s.json" % code))
    except (ValueError, OSError):     # uszkodzony JSON to też ValueError
        return None
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        return None
    return sum(len(s["words"]) for s in segments if isinstance(s, dict) and isinstance(s.get("words"), list))


def _phrase_state(render, code: str, phrase) -> str:
    """„ok”, „brak” (frazy nie ma w transkrypcji) albo „uszkodzona” (transkrypcji nie da się odczytać)."""
    try:
        render.find_phrase(code, phrase)
    except json.JSONDecodeError:   # to też ValueError, więc sprawdzamy to pierwsze
        return "uszkodzona"
    except ValueError:
        return "brak"
    except (KeyError, TypeError, AttributeError, OSError):
        return "uszkodzona"
    return "ok"


def _file_problems(render, label: str, reel: dict, notes: list | None = None) -> list[str]:
    """Plik wideo, transkrypcja oraz frazy `strong` i `cuts` w transkrypcji.

    Rolka bez mowy (transkrypcja ma 0 słów) nie potrzebuje ani `strong`, ani `cuts`: to nie problem, tylko informacja
    w `notes`. Problemem jest dopiero rolka bez mowy, która te pola ma, bo nie ma w czym szukać ich fraz.
    """
    code = reel["code"]
    out = []
    if not (config.SRC / ("%s.mp4" % code)).is_file():
        out.append("%s: brak pliku dane/src/%s.mp4. Uruchom komendę pobierz albo wrzuć oryginał pod tą nazwą, "
                   "albo wyłącz rolkę (active: false)." % (label, code))
    if not (config.TRANSCRIPTS / ("%s.json" % code)).is_file():
        out.append("%s: brak transkrypcji (dane/transkrypcje/%s.json). Uruchom komendę transkrybuj." % (label, code))
        return out                                   # bez transkrypcji nie ma czego szukać
    phrases = []                                     # (opis, fraza)
    if reel.get("strong"):
        phrases.append(("zdania z pola strong", reel["strong"]))
    for cut in reel.get("cuts") or []:
        if not isinstance(cut, dict) or not cut.get("from"):
            out.append("%s: wpis w polu cuts nie ma fragmentu from." % label)
            continue
        for key in ("from", "to"):
            if cut.get(key):
                phrases.append(("fragmentu z pola cuts (%s)" % ("początek" if key == "from" else "koniec"), cut[key]))
    if speech_words(code) == 0:
        if phrases:
            out.append("%s: rolka nie ma mowy (transkrypcja ma 0 słów), więc pola strong i cuts nie mają sensu. Usuń je "
                       "z dane/pula.json." % label)
        elif notes is not None:
            notes.append("%s: rolka bez mowy (transkrypcja ma 0 słów), więc nie potrzebuje pól strong ani cuts. Poziom "
                         "zmian Mocna jej nie dotyczy, bo nie ma zdania na zimne otwarcie." % label)
        return out
    for what, phrase in phrases:
        state = _phrase_state(render, code, phrase)
        if state == "uszkodzona":
            out.append("%s: nie mogę sprawdzić fraz, bo transkrypcja jest uszkodzona. Usuń plik "
                       "dane/transkrypcje/%s.json i uruchom komendę transkrybuj jeszcze raz." % (label, code))
            break
        if state == "brak":
            out.append("%s: %s %s nie ma w transkrypcji." % (label, what, _quoted(phrase)))
    return out


def _text_problems(label: str, reel: dict) -> list[str]:
    """Wezwanie do działania (cta), jego warianty, dopiski i długość podpisów.

    `cta` jest opcjonalne: gdy go brak albo jest puste, kontroli CTA nie ma (warianty bez `cta` i tak nigdy nie
    trafiają do podpisu), a dopiski i długość podpisu sprawdzamy jak zawsze.
    """
    out = []
    cta = reel.get("cta")
    caption = reel.get("caption") or ""
    with_cta = captions.has_cta(reel)
    variants = [v for v in (reel.get("cta_variants") or []) if isinstance(v, str)] if with_cta else []
    extras = [x for x in (reel.get("extras") or []) if isinstance(x, str)]
    if cta is not None and not isinstance(cta, str):
        out.append("%s: pole cta ma być tekstem (dokładnym fragmentem podpisu), a jest czymś innym." % label)
    if with_cta and cta not in caption:
        out.append("%s: tekstu z pola cta nie ma w podpisie (caption). Skopiuj CTA z podpisu dokładnie." % label)
    keep = captions.must_keep(cta) if with_cta else set()
    for variant in variants:
        lost = keep - captions.must_keep(variant)
        if lost:
            out.append("%s: wariant CTA %s gubi: %s. Zostaw w nim nick (@…) i słowo-klucz w „…”."
                       % (label, _quoted(variant), ", ".join(sorted(lost))))
    if len(extras) < MIN_EXTRAS:
        out.append("%s: za mało dopisków w polu extras (jest %d, potrzeba co najmniej %d)."
                   % (label, len(extras), MIN_EXTRAS))
    for text in variants + extras:
        if "—" in text:
            out.append("%s: dopisek albo wariant CTA %s ma myślnik „—”. Zamień go na kropkę, przecinek albo "
                       "dwukropek." % (label, _quoted(text)))
    return out + _caption_problems(label, reel)


def _caption_problems(label: str, reel: dict) -> list[str]:
    """Długość podpisów kolejnych wersji: żaden nie może przekroczyć limitu Instagrama.

    Zaproszenie i dopisek rotują osobno, więc sprawdzamy tyle wersji, ile wynosi okres rotacji (`captions.period`):
    dopiero potem podpisy się powtarzają i nie ma już nowych kombinacji.
    """
    count = max(1, min(captions.period(reel), CAPTIONS_MAX_CHECKED))
    try:
        lengths = [len(captions.compose(reel, n)) for n in range(count)]
    except (TypeError, AttributeError):
        return ["%s: nie mogę złożyć podpisu, bo pola caption, cta_variants albo extras mają zły format." % label]
    worst = max(range(count), key=lambda n: lengths[n])
    if lengths[worst] > CAPTION_MAX:
        return ["%s: podpis wersji %d ma %d znaków, a Instagram przyjmuje najwyżej %d."
                % (label, worst + 1, lengths[worst], CAPTION_MAX)]
    return []


def _hook_problems(label: str, code: str, hooks, emoji_ok: set, minimum: int = MIN_HOOKS) -> list[str]:
    """Bank hooków rolki: co najmniej `minimum` (domyślnie 3), każdy z unikalnym id, tekstem do 50 znaków i emotką z
    paczki."""
    bank = hooks.get(code) if isinstance(hooks, dict) else None
    bank = bank if isinstance(bank, list) else []
    out = []
    if len(bank) < minimum:
        out.append("%s: za mało hooków w hooki.json (jest %d, potrzeba co najmniej %d)."
                   % (label, len(bank), minimum))
    seen = set()
    for i, hook in enumerate(bank, start=1):
        if not isinstance(hook, dict):
            out.append("%s: hook nr %d ma zły format (powinien mieć pola id, text i emoji)." % (label, i))
            continue
        hid = hook.get("id")
        tag = "hook %s" % (hid if hid else "nr %d" % i)
        if not hid:
            out.append("%s: %s nie ma id." % (label, tag))
        elif hid in seen:
            out.append("%s: id „%s” powtarza się w hookach tej rolki." % (label, hid))
        seen.add(hid)
        text = hook.get("text")
        if not isinstance(text, str) or not text.strip():
            out.append("%s: %s: brak tekstu." % (label, tag))
        else:
            if len(text) > HOOK_MAX:
                out.append("%s: %s: tekst ma %d znaków, a limit to %d." % (label, tag, len(text), HOOK_MAX))
            if strip_emoji(text) != text:
                out.append("%s: %s: w tekście jest emotka. Emotka ma być osobno, w polu emoji." % (label, tag))
        emoji = hook.get("emoji")
        if not isinstance(emoji, str) or not emoji:
            out.append("%s: %s: brak emotki." % (label, tag))
        elif "\ufe0f" in emoji:
            out.append("%s: %s: emotka ma niewidoczny znak U+FE0F. Wpisz samą emotkę bez niego." % (label, tag))
        elif emoji not in emoji_ok:
            out.append("%s: %s: emotki „%s” nie ma w zestawie (assets/emoji). Wybierz inną." % (label, tag, emoji))
    return out


def plan_problems(reel: dict, hooks, emoji_ok: set) -> list[str]:
    """Problemy rolki, przez które jej wersje wyszłyby złe albo odrzuciłby je Instagram, jako polskie komunikaty.

    To tylko to, co psuje wersję po drodze: hooki (id, tekst do 50 znaków bez emotki, emotka z paczki), długość
    wszystkich podpisów i wpisy `blur` (render odrzuca inne niż liczby w kadrze). Plików i transkrypcji nie sprawdza
    (to robi render, wersja po wersji), a bank może mieć nawet jeden hook: pełne sprawdzenie (co najmniej 3 hooki,
    dopiski, CTA) robi `validate`.
    """
    from . import render  # PIL i PyAV ładują się dopiero tu (patrz opis modułu)

    label = reel_label(reel)
    return (_hook_problems(label, reel["code"], hooks, emoji_ok, minimum=1) + _caption_problems(label, reel)
            + _blur_problems(render, label, reel))


def validate(pool: list, hooks: dict, notes: list | None = None) -> list[str]:
    """Problemy w puli jako polskie komunikaty (pusta lista, gdy wszystko gra). Sprawdza tylko aktywne rolki.

    Rolka musi mieć plik dane/src/<kod>.mp4 i transkrypcję, a `strong` i każdy fragment `cuts` musi się w niej
    znajdować. Rolka bez mowy (transkrypcja ma 0 słów) nie musi mieć ani `strong`, ani `cuts`: informację o niej
    dopisuje do `notes` (jeśli podano listę), a problemami zostają tylko rzeczy do naprawienia.
    `cta` ma występować w podpisie, a każdy jego wariant ma zachować nick i słowo-klucz. `extras` ma co najmniej 4
    pozycje bez „—”, a podpis każdej wersji (aż podpisy zaczną się powtarzać) ma najwyżej 2200 znaków. W `hooks` ma
    być co najmniej 3 hooki rolki, każdy z unikalnym `id`, tekstem do 50 znaków i emotką z `render.emoji_set()` bez
    U+FE0F.
    """
    from . import render  # PIL i PyAV ładują się dopiero tu (patrz opis modułu)

    emoji_ok = set(render.emoji_set())
    problems = []
    for reel in pool:
        if not isinstance(reel, dict):
            problems.append("Wpis w puli ma zły format (powinien być obiektem z polami code, name, caption…).")
            continue
        if not reel.get("active", True):
            continue
        code = reel.get("code")
        if not code or not isinstance(code, str):
            problems.append("Wpis w puli nie ma kodu rolki (pole code).")
            continue
        if not valid_code(code):
            problems.append("Rolka %s: kod ma niedozwolone znaki albo jest za krótki. Kod to sam ciąg liter, cyfr, „-” "
                            "i „_” z adresu rolki (instagram.com/reel/KOD/), bez reszty adresu." % _quoted(code))
            continue
        label = reel_label(reel)
        problems += _file_problems(render, label, reel, notes)
        problems += _blur_problems(render, label, reel)
        problems += _text_problems(label, reel)
        problems += _hook_problems(label, code, hooks, emoji_ok)
    return problems


def _blur_problems(render, label: str, reel: dict) -> list[str]:
    """Pole `blur`: lista wpisów z dwiema liczbami `t` i czterema `box` (te same zasady, co przy renderze)."""
    blur = reel.get("blur")
    if blur is None:
        return []
    if not isinstance(blur, list):
        return ["%s: pole blur ma być listą wpisów {\"t\": [od, do], \"box\": [x, y, szerokość, wysokość]}." % label]
    out = []
    for i, entry in enumerate(blur, start=1):
        problem = render.blur_problem(entry)
        if problem:
            out.append("%s: wpis nr %d w polu blur: %s." % (label, i, problem))
    return out
