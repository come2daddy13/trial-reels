"""Minimalny klient Zernio dla trial reels (urllib, bez zależności spoza biblioteki standardowej).

Klucz API czyta z dane/.env (albo ze zmiennej środowiskowej ZERNIO_API_KEY). Konto Instagrama i strefę czasową
dostaje każda funkcja jako parametr. Moduł nie zagląda do ustawień klienta, więc o tym, o które konto chodzi,
decyduje zawsze wywołujący.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config

UPLOAD_TRIES = 4
UPLOAD_WAIT_S = 10

ANALYTICS_MAX_DAYS = 360     # Zernio przyjmuje do 366 dni na zapytanie, bierzemy zapas
ANALYTICS_PAGE_SIZE = 100

DOWNLOAD_TRIES = 3
DOWNLOAD_WAIT_S = 2
DOWNLOAD_TIMEOUT_S = 60      # na każde połączenie i każdy odczyt z osobna, nie na cały plik
DOWNLOAD_CHUNK = 1 << 20
MIN_VIDEO_BYTES = 10_000     # krótszy plik to nie rolka (np. strona z błędem), choćby miał nagłówek MP4
DOWNLOAD_AGENT = "Mozilla/5.0 (compatible; trial-reels)"


# Klucz idzie do nagłówka HTTP, więc ma same widoczne znaki ASCII: bez spacji, tabulatorów, końców linii i liter spoza
# ASCII. Inaczej biblioteka HTTP odrzuca nagłówek błędem, w którego treści stoi cały klucz.
KEY_CHARS = re.compile(r"[!-~]+")


class ZernioError(RuntimeError):
    """Błąd Zernio: `status` to kod HTTP (None, gdy odpowiedzi nie było), a `key` mówi, że to problem z kluczem."""

    def __init__(self, msg: str, status: int | None = None, key: bool = False):
        super().__init__(msg)
        self.status = status
        self.key = key


def _key() -> str:
    """Klucz Zernio do nagłówka. Brak albo znaki, których nagłówek nie uniesie, to `ZernioError` bez wartości klucza."""
    k = (config.env().get("ZERNIO_API_KEY") or "").strip()
    if not k:
        raise ZernioError("brak klucza Zernio w dane/.env", key=True)
    if not KEY_CHARS.fullmatch(k):
        raise ZernioError("klucz Zernio ma niedozwolone znaki (spację, tabulator, koniec linii albo literę spoza ASCII). "
                          "Uruchom komendę klucz i wklej klucz jeszcze raz: w jednej linii, tuż za znakiem =, bez "
                          "spacji.", key=True)
    return k


def _origin(url: str) -> tuple:
    """(schemat, host, port) adresu, z portem domyślnym dla http i https: tak porównujemy, czy to „ten sam adres”."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return scheme, (parts.hostname or "").lower(), port or {"http": 80, "https": 443}.get(scheme)


class _KeepKeyAtHome(urllib.request.HTTPRedirectHandler):
    """Przekierowanie zabiera nagłówek Authorization (klucz Zernio) tylko na ten sam schemat, host i port.

    Domyślna obsługa przekierowań w Pythonie kopiuje nagłówki pod nowy adres, także na obcy host i z https na http,
    więc źle skonfigurowane albo przejęte przekierowanie wysłałoby tam klucz klienta.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and _origin(new.full_url) != _origin(req.full_url):
            new.remove_header("Authorization")
        return new


_HANDLERS = (_KeepKeyAtHome,)


def _urlopen(req, timeout):
    """Jedyne miejsce, które łączy się z siecią (testy je podmieniają). Przekierowania idą przez `_KeepKeyAtHome`."""
    return urllib.request.build_opener(*_HANDLERS).open(req, timeout=timeout)


def _api(method: str, path: str, body=None, params=None, timeout: int = 60):
    key = _key()
    url = config.ZERNIO_BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with _urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ZernioError("%s %s -> %s: %s" % (method, path, e.code, e.read()[:400].decode("utf-8", "replace")),
                          e.code)


def transient(e: Exception) -> bool:
    """Chwilowy błąd (5xx, 429, zerwane połączenie), po którym warto ponowić wysyłkę albo pobieranie pliku."""
    status = e.status if isinstance(e, ZernioError) else getattr(e, "code", None)
    if isinstance(e, (ZernioError, urllib.error.HTTPError)):
        return status is not None and (status >= 500 or status == 429)
    return isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead))


# --- wysyłka pliku ---------------------------------------------------------------

def upload(path) -> str:
    """Presign + PUT z ponowieniem przy chwilowych błędach serwera (zdarza się 502 przy co którejś wysyłce)."""
    for attempt in range(UPLOAD_TRIES):
        try:
            return _upload_once(path)
        except Exception as e:
            if attempt == UPLOAD_TRIES - 1 or not transient(e):
                raise
            time.sleep(UPLOAD_WAIT_S * (attempt + 1))


def _upload_once(path) -> str:
    """Presign + PUT. Zwraca publiczny adres pliku w Zernio."""
    path = Path(path)
    size = path.stat().st_size
    mime = "video/mp4" if path.suffix.lower() == ".mp4" else "image/jpeg"
    b = _api("POST", "/media/presign", {"filename": path.name, "contentType": mime, "size": size})
    req = urllib.request.Request(b["uploadUrl"], data=path.read_bytes(), method="PUT",
                                 headers={"Content-Type": mime, "Content-Length": str(size)})
    with _urlopen(req, timeout=1800) as r:
        if r.status not in (200, 201):
            raise ZernioError("PUT %s" % r.status)
    return b["publicUrl"]


# --- konta i posty ---------------------------------------------------------------

def trial_payload(account_id: str, tz: str, caption: str, media_url: str, when_local: str, thumb_ms: int) -> dict:
    """Trial reel na IG: pokazuje się najpierw osobom, które cię nie obserwują, a do obserwujących puszczasz go
    sam, ręcznie (MANUAL). `when_local` to czas w strefie `tz`, np. 2026-11-20T09:00:00."""
    return {
        "content": caption,
        "mediaItems": [{"type": "video", "url": media_url}],
        "platforms": [{
            "platform": "instagram",
            "accountId": account_id,
            "platformSpecificData": {"trialParams": {"graduationStrategy": "MANUAL"}, "thumbOffset": int(thumb_ms)},
        }],
        "scheduledFor": when_local,
        "timezone": tz,
    }


def create_post(payload: dict) -> dict:
    r = _api("POST", "/posts", payload)
    return r.get("post", r)


def get_post(post_id: str) -> dict:
    r = _api("GET", "/posts/%s" % post_id)
    return r.get("post", r)


def accounts() -> list[dict]:
    """Podłączone konta Instagrama (GET /accounts). Każde ma m.in. `_id`, `username` i `platform`."""
    r = _api("GET", "/accounts")
    items = r if isinstance(r, list) else (r.get("accounts") or r.get("data") or [])
    return [a for a in items if isinstance(a, dict) and str(a.get("platform") or "").lower() == "instagram"]


def _account_of(entry: dict) -> str | None:
    """ID konta z wpisu `platforms[]` posta: Zernio podaje je jako napis albo jako obiekt konta z `_id`."""
    acc = entry.get("accountId")
    if isinstance(acc, dict):
        acc = acc.get("_id") or acc.get("id")
    return None if acc is None else str(acc)


def _is_account(entry: dict, account_id: str) -> bool:
    """Czy wpis `platforms[]` dotyczy tego konta. Wpis bez ID konta liczymy jako możliwy: lepiej pominąć
    termin niż zdublować post."""
    acc = _account_of(entry)
    return acc is None or acc == str(account_id)


def recent_posts(account_id: str) -> list:
    """Ostatnie 100 postów z Zernio (od najdalszego terminu), tylko te, które mają wpis dla tego konta."""
    r = _api("GET", "/posts", params={"limit": 100, "sortBy": "scheduledFor", "sortOrder": "desc"})
    return [p for p in r.get("posts", []) if any(_is_account(x, account_id) for x in p.get("platforms") or [])]


def ig_post_at(account_id: str, when_utc: datetime):
    """Post IG tego konta w Zernio na tę samą minutę (blokada duplikatu przy dwóch uruchomieniach naraz).
    `when_utc` to data ze strefą czasową, w dowolnej strefie."""
    target = when_utc.astimezone(timezone.utc)
    for p in recent_posts(account_id):
        sf = p.get("scheduledFor")
        if not sf:
            continue
        t = datetime.fromisoformat(sf.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)  # bez strefy uznajemy czas za UTC
        same_min = abs((t - target).total_seconds()) < 60
        if same_min and p.get("status") not in ("failed", "cancelled", "deleted") \
                and any(x.get("platform") == "instagram" and _is_account(x, account_id)
                        for x in p.get("platforms") or []):
            return p
    return None


# --- statystyki ------------------------------------------------------------------

def _as_date(value) -> date:
    """Data z napisu RRRR-MM-DD (dłuższy napis ISO też, liczy się pierwszych 10 znaków) albo z date/datetime."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def analytics(account_id: str, from_date, to_date) -> list:
    """Posty IG konta ze statystykami (GET /analytics) z całego zakresu dat, obie granice włącznie.

    Zernio przyjmuje do 366 dni na zapytanie, więc dłuższy zakres dzielę na kolejne, przylegające do siebie
    kawałki (bez dziur i bez nakładania). Zakres od tyłu (od późniejszej daty do wcześniejszej) daje pustą listę.
    """
    start, end = _as_date(from_date), _as_date(to_date)
    out = []
    while start <= end:
        stop = min(start + timedelta(days=ANALYTICS_MAX_DAYS), end)
        out += _analytics_range(account_id, start.isoformat(), stop.isoformat())
        start = stop + timedelta(days=1)
    return out


def _analytics_range(account_id: str, from_date: str, to_date: str) -> list:
    """Wszystkie strony wyników dla jednego zakresu (nie dłuższego niż limit Zernio)."""
    out, page = [], 1
    while True:
        r = _api("GET", "/analytics", params={"accountId": account_id, "platform": "instagram",
                                               "fromDate": from_date, "toDate": to_date,
                                               "limit": ANALYTICS_PAGE_SIZE, "page": page})
        posts = r.get("posts", [])
        out += posts
        pg = r.get("pagination") or {}
        if not posts or page >= int(pg.get("pages") or pg.get("totalPages") or 1):
            return out
        page += 1


# --- pobieranie pliku ------------------------------------------------------------

def _plain_url(url: str) -> str:
    """Adres bez danych logowania, zapytania i fragmentu: w komunikatach nie pokazujemy podpisów ani tokenów."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def download(url: str, dest, tries: int = DOWNLOAD_TRIES) -> Path:
    """Pobiera film MP4 spod `url` do pliku `dest` i zwraca jego ścieżkę.

    Plik powstaje najpierw jako `dest` + „.part” i trafia na miejsce dopiero po sprawdzeniu, więc przerwane
    pobieranie nie zostawia niedokończonego filmu ani nie rusza starego pliku. Chwilowe błędy sieci ponawiam
    (`tries` prób), reszta kończy się od razu. Każda porażka to `ZernioError` z czytelnym komunikatem.
    """
    dest = Path(dest)
    if urllib.parse.urlsplit(url).scheme.lower() not in ("http", "https"):
        raise ZernioError("adres pliku musi zaczynać się od http:// albo https://: %s" % _plain_url(url))
    last: Exception | None = None
    for attempt in range(max(1, tries)):
        try:
            return _download_once(url, dest)
        except Exception as e:
            last = e
            if attempt >= tries - 1 or not transient(e):
                break
            time.sleep(DOWNLOAD_WAIT_S * (attempt + 1))
    if isinstance(last, ZernioError):
        raise last
    if isinstance(last, PermissionError):     # plik pobrany, ale system nie pozwala go zapisać: to nie wina sieci
        raise ZernioError("nie mogę zapisać pobranego pliku %s: system odmawia dostępu (plik może trzymać antywirus albo "
                          "inny program). Spróbuj za chwilę" % dest.name) from last
    raise ZernioError("nie udało się pobrać pliku z %s: %s" % (_plain_url(url), last),
                      getattr(last, "code", None)) from last


def _download_once(url: str, dest: Path) -> Path:
    """Jedna próba: strumień do pliku .part, kontrola nagłówka MP4, rozmiaru i długości, na końcu podmiana."""
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_AGENT})
    try:
        with _urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as r:
            head = b""
            while len(head) < 8:  # bajty 4-8 mówią, czy to MP4 (ftyp); do tego czasu niczego nie zapisujemy
                more = r.read(DOWNLOAD_CHUNK)
                if not more:
                    break
                head += more
            if head[4:8] != b"ftyp":
                raise ZernioError("pod adresem %s nie ma filmu MP4 (to inny plik albo strona z błędem)"
                                  % _plain_url(url))
            announced = _announced_length(r)
            dest.parent.mkdir(parents=True, exist_ok=True)
            size = len(head)
            with open(part, "wb") as f:
                f.write(head)
                while True:
                    chunk = r.read(DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    size += len(chunk)
                f.flush()
                os.fsync(f.fileno())
            if announced is not None and size != announced:
                raise ConnectionError("pobrano %d z %d bajtów" % (size, announced))
            if size <= MIN_VIDEO_BYTES:
                raise ZernioError("plik z %s ma tylko %d B, za mało na film" % (_plain_url(url), size))
        config._replace(part, dest)   # z ponowieniami: na Windowsie świeży plik bywa chwilowo zajęty przez antywirus
        return dest
    except BaseException:
        _remove(part)
        raise


def _announced_length(response) -> int | None:
    """Długość pliku z nagłówka Content-Length (None, gdy serwer jej nie podał albo podał bzdurę)."""
    headers = getattr(response, "headers", None)
    try:
        value = headers.get("Content-Length") if headers is not None else None
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
