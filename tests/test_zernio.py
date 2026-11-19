"""Testy klienta Zernio: ładunek triala, konta, statystyki z podziałem zakresu, ponawianie wysyłki i pobieranie.

Sieć jest zawsze atrapą: żaden test nie łączy się z prawdziwym Zernio i niczego tam nie zapisuje.
"""
import email.message
import io
import json
import socket
import unicodedata
import urllib.error
import urllib.request
import urllib.response
from datetime import date, datetime, timedelta, timezone
from http.client import IncompleteRead
from pathlib import Path

import pytest

from trial_reels import config, zernio

MP4_HEAD = b"\x00\x00\x00\x18ftypmp42"
REAL_URLOPEN = zernio._urlopen          # prawdziwy opener (z obsługą przekierowań) dla testów z atrapą transportu


def names(folder):
    """Nazwy plików w folderze (NFC, żeby wynik nie zależał od systemu plików)."""
    return sorted(unicodedata.normalize("NFC", p.name) for p in folder.iterdir())


def mp4_bytes(size=20_000):
    """Bajty podobne do filmu: nagłówek `ftyp` w bajtach 4-8 i wypełnienie do zadanego rozmiaru."""
    return MP4_HEAD + b"\x01" * (size - len(MP4_HEAD))


class Response(io.BytesIO):
    """Odpowiedź `urlopen`: strumień bajtów z kodem HTTP i nagłówkami."""

    def __init__(self, body=b"", status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class DropsMidway(Response):
    """Odpowiedź, której połączenie zrywa się po pierwszej porcji danych."""

    def read(self, size=-1):
        if self.tell() > 0:
            raise ConnectionResetError("połączenie zerwane")
        return super().read(size)


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Test, który sięgnie po sieć bez własnej atrapy, zawodzi zamiast łączyć się z prawdziwym Zernio."""

    def refuse(*args, **kwargs):
        raise AssertionError("sieć w testach tylko przez atrapę")

    monkeypatch.setattr(zernio, "_urlopen", refuse)
    monkeypatch.setattr(zernio.urllib.request, "urlopen", refuse)


def serve(monkeypatch, *replies):
    """Atrapa `zernio._urlopen`: kolejne wywołania dostają kolejne odpowiedzi (wyjątki są rzucane). Zwraca listę żądań."""
    queue, requests = list(replies), []

    def fake(req, timeout=None):
        requests.append(req)
        reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    monkeypatch.setattr(zernio, "_urlopen", fake)
    return requests


def fake_api(monkeypatch, handler):
    """Atrapa `_api`: zapisuje wywołania, a odpowiedź liczy `handler(method, path, body, params)`."""
    calls = []

    def api(method, path, body=None, params=None, timeout=60):
        calls.append({"method": method, "path": path, "body": body, "params": params})
        return handler(method, path, body, params)

    monkeypatch.setattr(zernio, "_api", api)
    return calls


@pytest.fixture
def sleeps(monkeypatch):
    """Zapisuje czasy oczekiwania zamiast naprawdę czekać."""
    waited = []
    monkeypatch.setattr(zernio.time, "sleep", waited.append)
    return waited


# --- ładunek triala ----------------------------------------------------------

def test_trial_payload_is_manual_trial_for_given_account():
    p = zernio.trial_payload("ACC", "Europe/Warsaw", "Podpis", "https://x/v.mp4", "2026-11-20T09:00:00", 900)
    plat = p["platforms"][0]
    assert plat["accountId"] == "ACC" and plat["platform"] == "instagram"
    assert plat["platformSpecificData"] == {"trialParams": {"graduationStrategy": "MANUAL"}, "thumbOffset": 900}
    assert p["scheduledFor"] == "2026-11-20T09:00:00" and p["timezone"] == "Europe/Warsaw"


def test_trial_payload_carries_caption_video_and_integer_thumb_offset():
    p = zernio.trial_payload("ACC", "Europe/Warsaw", "Zażółć gęślą jaźń 🔥", "https://x/v.mp4",
                             "2026-11-20T09:00:00", 900.7)
    assert p["content"] == "Zażółć gęślą jaźń 🔥"
    assert p["mediaItems"] == [{"type": "video", "url": "https://x/v.mp4"}]
    assert p["platforms"][0]["platformSpecificData"]["thumbOffset"] == 900
    assert len(p["platforms"]) == 1


def test_account_and_timezone_come_from_arguments_never_from_settings(monkeypatch):
    """Ustawienia klienta mówią co innego niż argumenty, a moduł i tak ich nie czyta."""
    config.save_settings({"ig_account_id": "INNE_KONTO", "timezone": "Asia/Tokyo"})

    def refuse():
        raise AssertionError("moduł zernio nie czyta ustawień klienta")

    monkeypatch.setattr(config, "settings", refuse)
    posts = {"posts": [{"_id": "P1", "scheduledFor": "2026-11-20T08:00:00Z", "status": "scheduled",
                        "platforms": [{"platform": "instagram", "accountId": "ACC"}]}]}
    calls = fake_api(monkeypatch, lambda m, path, b, q: {"accounts": []} if path == "/accounts" else posts)

    payload = zernio.trial_payload("ACC", "Europe/Warsaw", "Podpis", "https://x/v.mp4", "2026-11-20T09:00:00", 0)
    assert payload["platforms"][0]["accountId"] == "ACC" and payload["timezone"] == "Europe/Warsaw"
    zernio.accounts()
    zernio.analytics("ACC", "2026-11-01", "2026-11-02")
    assert zernio.recent_posts("ACC") == posts["posts"]
    assert zernio.ig_post_at("ACC", datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)) == posts["posts"][0]
    analytics_call = next(c for c in calls if c["path"] == "/analytics")
    assert analytics_call["params"]["accountId"] == "ACC"


# --- konta -------------------------------------------------------------------

def test_accounts_returns_instagram_only(monkeypatch):
    body = {"accounts": [
        {"_id": "A1", "platform": "instagram", "username": "przyklad.konto"},
        {"_id": "A2", "platform": "tiktok", "username": "przyklad.tt"},
        {"_id": "A3", "platform": "facebook"},
        {"_id": "A4", "platform": "instagram", "username": "drugie.konto"},
    ]}
    calls = fake_api(monkeypatch, lambda m, p, b, q: body)
    found = zernio.accounts()
    assert [a["_id"] for a in found] == ["A1", "A4"]
    assert all(a["platform"] == "instagram" for a in found)
    assert calls == [{"method": "GET", "path": "/accounts", "body": None, "params": None}]


@pytest.mark.parametrize("reply", [
    [{"_id": "A1", "platform": "instagram"}, {"_id": "A2", "platform": "tiktok"}],
    {"data": [{"_id": "A1", "platform": "instagram"}, {"_id": "A2", "platform": "tiktok"}]},
    {"accounts": [{"_id": "A1", "platform": "Instagram"}, {"_id": "A2", "platform": "tiktok"}]},
], ids=["lista", "klucz-data", "wielkie-litery"])
def test_accounts_understands_each_reply_shape(monkeypatch, reply):
    fake_api(monkeypatch, lambda m, p, b, q: reply)
    assert [a["_id"] for a in zernio.accounts()] == ["A1"]


@pytest.mark.parametrize("reply", [{}, {"accounts": []}, {"accounts": None}, []])
def test_accounts_without_any_gives_empty_list(monkeypatch, reply):
    fake_api(monkeypatch, lambda m, p, b, q: reply)
    assert zernio.accounts() == []


# --- statystyki: podział zakresu i strony ------------------------------------

def test_analytics_pages_and_splits_long_ranges(monkeypatch):
    def handler(method, path, body, params):
        page = params["page"]
        posts = [{"_id": "%s-%d-%d" % (params["fromDate"], page, i)} for i in range(2)]
        return {"posts": posts, "pagination": {"page": page, "pages": 3}}

    calls = fake_api(monkeypatch, handler)
    posts = zernio.analytics("ACC", "2025-01-01", "2026-06-30")

    chunks = {}
    for c in calls:
        assert c["method"] == "GET" and c["path"] == "/analytics"
        p = c["params"]
        assert p["accountId"] == "ACC" and p["platform"] == "instagram" and p["limit"] == 100
        chunks.setdefault((p["fromDate"], p["toDate"]), []).append(p["page"])

    assert len(chunks) >= 2
    ranges = list(chunks)
    for (start, stop), pages in chunks.items():
        assert (date.fromisoformat(stop) - date.fromisoformat(start)).days + 1 <= 361
        assert pages == [1, 2, 3]  # każdy kawałek: strony od 1 do pagination.pages
    assert ranges[0][0] == "2025-01-01" and ranges[-1][1] == "2026-06-30"
    for (_, prev_stop), (next_start, _) in zip(ranges, ranges[1:]):
        assert date.fromisoformat(next_start) == date.fromisoformat(prev_stop) + timedelta(days=1)
    assert len(posts) == len(chunks) * 3 * 2
    assert len({p["_id"] for p in posts}) == len(posts)  # nic się nie powtarza


def test_analytics_short_range_is_one_chunk_up_to_360_days_apart(monkeypatch):
    calls = fake_api(monkeypatch, lambda m, p, b, q: {"posts": [{"_id": "x"}], "pagination": {"pages": 1}})
    zernio.analytics("ACC", "2026-11-01", "2026-11-30")
    assert [(c["params"]["fromDate"], c["params"]["toDate"]) for c in calls] == [("2026-11-01", "2026-11-30")]

    calls.clear()
    zernio.analytics("ACC", "2026-01-01", "2026-12-27")  # 360 dni różnicy: jeszcze jedno zapytanie
    assert [(c["params"]["fromDate"], c["params"]["toDate"]) for c in calls] == [("2026-01-01", "2026-12-27")]

    calls.clear()
    zernio.analytics("ACC", "2026-01-01", "2026-12-28")  # 361 dni różnicy: dzielimy, ostatni kawałek ma jeden dzień
    assert [(c["params"]["fromDate"], c["params"]["toDate"]) for c in calls] == [
        ("2026-01-01", "2026-12-27"), ("2026-12-28", "2026-12-28")]


def test_analytics_reversed_range_asks_nothing_and_gives_empty_list(monkeypatch):
    calls = fake_api(monkeypatch, lambda m, p, b, q: pytest.fail("zakres od tyłu nie powinien pytać Zernio"))
    assert zernio.analytics("ACC", "2026-11-30", "2026-11-01") == []
    assert calls == []


def test_analytics_accepts_date_objects_and_total_pages_and_stops_on_empty_page(monkeypatch):
    pages = {1: [{"_id": "a"}, {"_id": "b"}], 2: [{"_id": "c"}], 3: []}

    def handler(method, path, body, params):
        return {"posts": pages[params["page"]], "pagination": {"totalPages": 5}}  # strony 4-5 nie istnieją

    calls = fake_api(monkeypatch, handler)
    posts = zernio.analytics("ACC", date(2026, 11, 1), datetime(2026, 11, 30, 12, 0))
    assert [p["_id"] for p in posts] == ["a", "b", "c"]
    assert [c["params"]["page"] for c in calls] == [1, 2, 3]
    assert calls[0]["params"]["fromDate"] == "2026-11-01" and calls[0]["params"]["toDate"] == "2026-11-30"


# --- ponawianie wysyłki ------------------------------------------------------

def test_upload_retries_transient_errors_only(monkeypatch):
    calls = []

    def flaky(path):
        calls.append(path)
        if len(calls) < 3:
            raise urllib.error.HTTPError("u", 502, "Bad Gateway", None, None)
        return "https://zernio/media/x.mp4"

    monkeypatch.setattr(zernio, "_upload_once", flaky)
    monkeypatch.setattr(zernio.time, "sleep", lambda s: None)
    assert zernio.upload("x.mp4") == "https://zernio/media/x.mp4" and len(calls) == 3
    calls.clear()

    def bad_request(path):
        calls.append(path)
        raise zernio.ZernioError("POST /media/presign -> 400: zły plik", 400)

    monkeypatch.setattr(zernio, "_upload_once", bad_request)
    try:
        zernio.upload("x.mp4")
        assert False, "400 nie powinno być ponawiane"
    except zernio.ZernioError:
        assert len(calls) == 1


def test_upload_gives_up_after_four_tries_with_growing_waits(monkeypatch, sleeps):
    calls = []

    def always_bad_gateway(path):
        calls.append(path)
        raise urllib.error.HTTPError("u", 502, "Bad Gateway", None, None)

    monkeypatch.setattr(zernio, "_upload_once", always_bad_gateway)
    with pytest.raises(urllib.error.HTTPError):
        zernio.upload("x.mp4")
    assert len(calls) == 4 and sleeps == [10, 20, 30]


@pytest.mark.parametrize("name, mime", [("rolka.mp4", "video/mp4"), ("Rolka.MP4", "video/mp4"),
                                         ("okładka.jpg", "image/jpeg")])
def test_upload_once_presigns_then_puts_file_and_returns_public_url(monkeypatch, tmp_path, name, mime):
    file = tmp_path / "Łódź ąę" / name
    file.parent.mkdir()
    file.write_bytes(b"0123456789")
    calls = fake_api(monkeypatch, lambda m, p, b, q: {"uploadUrl": "https://storage.example/put/abc",
                                                      "publicUrl": "https://cdn.example/abc"})
    requests = serve(monkeypatch, Response(status=200))

    assert zernio.upload(file) == "https://cdn.example/abc"
    assert calls == [{"method": "POST", "path": "/media/presign", "params": None,
                      "body": {"filename": name, "contentType": mime, "size": 10}}]
    put = requests[0]
    assert put.get_method() == "PUT" and put.full_url == "https://storage.example/put/abc"
    assert put.data == b"0123456789"
    assert put.get_header("Content-type") == mime and put.get_header("Content-length") == "10"


def test_upload_once_rejects_unexpected_put_status(monkeypatch, tmp_path):
    file = tmp_path / "rolka.mp4"
    file.write_bytes(b"abc")
    fake_api(monkeypatch, lambda m, p, b, q: {"uploadUrl": "https://storage.example/put", "publicUrl": "https://x"})
    serve(monkeypatch, Response(status=204))
    with pytest.raises(zernio.ZernioError, match="PUT 204"):
        zernio.upload(file)


@pytest.mark.parametrize("error, expected", [
    (zernio.ZernioError("x", 502), True),
    (zernio.ZernioError("x", 503), True),
    (zernio.ZernioError("x", 429), True),
    (zernio.ZernioError("x", 400), False),
    (zernio.ZernioError("x", 404), False),
    (zernio.ZernioError("brak statusu"), False),
    (urllib.error.HTTPError("u", 500, "x", None, None), True),
    (urllib.error.HTTPError("u", 404, "x", None, None), False),
    (urllib.error.URLError("brak sieci"), True),
    (TimeoutError(), True),
    (ConnectionResetError(), True),
    (IncompleteRead(b"ab"), True),
    (ValueError("x"), False),
])
def test_transient_classification(error, expected):
    assert zernio.transient(error) is expected


# --- klucz i wywołania API ---------------------------------------------------

def test_missing_key_message():
    with pytest.raises(zernio.ZernioError) as e:
        zernio._api("GET", "/accounts")
    assert str(e.value) == "brak klucza Zernio w dane/.env" and e.value.status is None


def test_empty_key_in_env_file_counts_as_missing():
    config.ENV.parent.mkdir(parents=True, exist_ok=True)
    config.ENV.write_text("ZERNIO_API_KEY=\n", encoding="utf-8")
    with pytest.raises(zernio.ZernioError, match="brak klucza Zernio"):
        zernio._api("GET", "/accounts")


def test_key_comes_from_env_file_and_environment_variable_wins(monkeypatch):
    config.ENV.parent.mkdir(parents=True, exist_ok=True)
    config.ENV.write_text("ZERNIO_API_KEY=klucz-z-pliku\n", encoding="utf-8")
    seen = serve(monkeypatch, Response(b"{}"), Response(b"{}"))
    zernio._api("GET", "/accounts")
    monkeypatch.setenv("ZERNIO_API_KEY", "klucz-z-otoczenia")
    zernio._api("GET", "/accounts")
    assert [r.get_header("Authorization") for r in seen] == ["Bearer klucz-z-pliku", "Bearer klucz-z-otoczenia"]


def test_key_from_the_environment_goes_to_the_header_without_its_line_end(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "klucz-testowy\n")
    seen = serve(monkeypatch, Response(b"{}"))
    zernio._api("GET", "/accounts")
    assert seen[0].get_header("Authorization") == "Bearer klucz-testowy"


@pytest.mark.parametrize("source,bad", [("env", "x9x9 ze-spacja"), ("env", "x9x9\nw-dwoch-liniach"),
                                        ("plik", "x9x9\tz-tabulatorem"), ("plik", "x9x9-z-literą-ą"),
                                        ("plik", "x9x9 ze-spacja-w-pliku")])
def test_a_key_with_characters_a_header_cannot_carry_is_refused_without_showing_it(monkeypatch, source, bad):
    """D3: taki klucz nie idzie do nagłówka (błąd nagłówka wypisałby go w całości) ani do komunikatu."""
    if source == "env":
        monkeypatch.setenv("ZERNIO_API_KEY", bad)
    else:
        config.ENV.parent.mkdir(parents=True, exist_ok=True)
        config.ENV.write_text("ZERNIO_API_KEY=%s\n" % bad, encoding="utf-8")
    seen = serve(monkeypatch)
    with pytest.raises(zernio.ZernioError) as caught:
        zernio._api("GET", "/accounts")
    error = caught.value
    assert seen == [] and error.key and error.status is None
    assert "x9x9" not in str(error) and "klucz" in str(error).lower() and "\n" not in str(error)


# --- D4: klucz nie idzie za przekierowaniem do innego hosta ani na http -------------------------------------------

def test_the_key_follows_a_redirect_only_to_the_same_scheme_host_and_port():
    handler = zernio._KeepKeyAtHome()
    req = urllib.request.Request("https://zernio.com/api/v1/posts", headers={"Authorization": "Bearer klucz-testowy"})

    def moved(url):
        return handler.redirect_request(req, io.BytesIO(), 302, "Found", {}, url)

    for same in ("https://zernio.com/api/v1/posts/", "https://ZERNIO.com:443/api/v1/inne"):
        assert moved(same).get_header("Authorization") == "Bearer klucz-testowy", same
    for other in ("https://obcy.example.net/x", "http://zernio.com/api/v1/posts", "https://zernio.com:8443/x",
                  "https://api.zernio.com/x"):
        new = moved(other)
        assert new.full_url == other and new.get_header("Authorization") is None, other


class Transport(urllib.request.BaseHandler):
    """Atrapa sieci pod prawdziwym openerem: odpowiedzi według adresu (kod, Location, treść), bez gniazd.

    Zapisuje każde żądanie jako (adres, nagłówek Authorization), więc widać, dokąd poszedł klucz.
    """

    handler_order = 50                  # przed prawdziwymi HTTPHandler i HTTPSHandler

    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def http_open(self, req):
        return self._answer(req)

    def https_open(self, req):
        return self._answer(req)

    def _answer(self, req):
        self.seen.append((req.full_url, req.get_header("Authorization")))
        status, location, body = self.routes[req.full_url]
        headers = email.message.Message()
        if location:
            headers["Location"] = location
        response = urllib.response.addinfourl(io.BytesIO(body), headers, req.full_url, status)
        response.msg = "OK" if status == 200 else "Found"
        return response


def test_api_keeps_the_key_at_home_through_a_chain_of_redirects(monkeypatch):
    """D4: klucz idzie tylko tam, skąd przyszło przekierowanie (ten sam schemat, host i port), a nie dalej."""
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("prawdziwe połączenie"))
    monkeypatch.setenv("ZERNIO_API_KEY", "klucz-testowy")
    monkeypatch.setattr(config, "ZERNIO_BASE", "https://api.example.com/v1")
    transport = Transport({
        "https://api.example.com/v1/accounts": (302, "/v1/accounts/", b""),
        "https://api.example.com/v1/accounts/": (302, "https://obcy.example.net/zbieram", b""),
        "https://obcy.example.net/zbieram": (302, "https://api.example.com/v1/wraca", b""),
        "https://api.example.com/v1/wraca": (302, "http://api.example.com/v1/po-http", b""),
        "http://api.example.com/v1/po-http": (200, None, b'{"accounts": []}'),
    })
    monkeypatch.setattr(zernio, "_HANDLERS", zernio._HANDLERS + (transport,))
    monkeypatch.setattr(zernio, "_urlopen", REAL_URLOPEN)
    assert zernio._api("GET", "/accounts") == {"accounts": []}
    assert transport.seen == [
        ("https://api.example.com/v1/accounts", "Bearer klucz-testowy"),
        ("https://api.example.com/v1/accounts/", "Bearer klucz-testowy"),      # ten sam schemat, host i port
        ("https://obcy.example.net/zbieram", None),                            # inny host
        ("https://api.example.com/v1/wraca", None),                            # po obcym hoście klucz już nie wraca
        ("http://api.example.com/v1/po-http", None),                           # z https na http
    ]


def test_every_request_to_the_network_goes_through_the_opener_that_guards_the_key():
    assert zernio._HANDLERS[0] is zernio._KeepKeyAtHome
    assert issubclass(zernio._KeepKeyAtHome, urllib.request.HTTPRedirectHandler)   # zastępuje domyślną obsługę
    source = Path(zernio.__file__).read_text(encoding="utf-8")
    assert source.count("urllib.request.urlopen(") == 0 and source.count("_urlopen(") >= 4


def test_api_builds_url_with_query_sends_json_and_parses_reply(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "klucz-testowy")
    seen = serve(monkeypatch, Response(json.dumps({"ok": True, "zażółć": "ł"}).encode("utf-8")), Response(b""))
    out = zernio._api("POST", "/posts", {"content": "Zażółć"}, {"a": 1, "b": "x y"})
    req = seen[0]
    assert out == {"ok": True, "zażółć": "ł"}
    assert req.full_url == config.ZERNIO_BASE + "/posts?a=1&b=x+y"
    assert req.get_method() == "POST" and req.get_header("Authorization") == "Bearer klucz-testowy"
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data.decode("utf-8")) == {"content": "Zażółć"}

    assert zernio._api("GET", "/posts/P1") == {}  # pusta odpowiedź to pusty słownik
    assert seen[1].data is None and seen[1].full_url == config.ZERNIO_BASE + "/posts/P1"


def test_api_http_error_becomes_zernio_error_with_status_and_body(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "klucz-testowy")
    err = urllib.error.HTTPError("https://zernio.example/x", 422, "Unprocessable", {},
                                 io.BytesIO('{"error": "zła data"}'.encode("utf-8")))
    serve(monkeypatch, err)
    with pytest.raises(zernio.ZernioError) as e:
        zernio._api("POST", "/posts", {})
    assert e.value.status == 422 and "POST /posts -> 422" in str(e.value) and "zła data" in str(e.value)
    assert "klucz-testowy" not in str(e.value)


# --- posty -------------------------------------------------------------------

def test_create_post_and_get_post_unwrap_post_key(monkeypatch):
    calls = fake_api(monkeypatch, lambda m, p, b, q: {"post": {"_id": "P1"}} if m == "POST" else {"_id": "P2"})
    assert zernio.create_post({"content": "x"}) == {"_id": "P1"}
    assert zernio.get_post("P2") == {"_id": "P2"}
    assert calls == [{"method": "POST", "path": "/posts", "body": {"content": "x"}, "params": None},
                     {"method": "GET", "path": "/posts/P2", "body": None, "params": None}]


def make_post(scheduled, status="scheduled", platform="instagram", account="ACC", **extra):
    return {"_id": "P-%s" % scheduled, "scheduledFor": scheduled, "status": status,
            "platforms": [{"platform": platform, "accountId": account}], **extra}


def test_recent_posts_asks_for_newest_hundred_and_keeps_only_given_account(monkeypatch):
    mine = make_post("2026-11-20T08:00:00.000Z")
    as_object = make_post("2026-11-20T09:00:00.000Z", account={"_id": "ACC", "username": "przyklad.konto"})
    unknown_owner = {"_id": "P-bez-konta", "platforms": [{"platform": "instagram"}]}
    other = make_post("2026-11-20T10:00:00.000Z", account="INNE")
    without_platforms = {"_id": "P-puste", "platforms": []}
    calls = fake_api(monkeypatch, lambda m, p, b, q: {"posts": [mine, as_object, unknown_owner, other,
                                                                  without_platforms]})
    assert zernio.recent_posts("ACC") == [mine, as_object, unknown_owner]
    assert calls == [{"method": "GET", "path": "/posts", "body": None,
                      "params": {"limit": 100, "sortBy": "scheduledFor", "sortOrder": "desc"}}]
    fake_api(monkeypatch, lambda m, p, b, q: {})
    assert zernio.recent_posts("ACC") == []


WHEN = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)


def test_ig_post_at_finds_the_post_of_that_account_in_the_same_minute(monkeypatch):
    near = make_post("2026-11-20T08:00:30.000Z")
    fake_api(monkeypatch, lambda m, p, b, q: {"posts": [near]})
    assert zernio.ig_post_at("ACC", WHEN) == near
    # ta sama chwila podana w innej strefie to nadal ta sama chwila
    assert zernio.ig_post_at("ACC", datetime(2026, 11, 20, 9, 0, tzinfo=timezone(timedelta(hours=1)))) == near
    assert zernio.ig_post_at("ACC", datetime(2026, 11, 20, 7, 59, 31, tzinfo=timezone.utc)) == near  # 59 s różnicy


@pytest.mark.parametrize("post", [
    make_post("2026-11-20T08:01:00.000Z"),                 # równo minutę później
    make_post("2026-11-20T07:59:00.000Z"),                 # równo minutę wcześniej
    make_post("2026-11-20T08:00:00.000Z", account="INNE"),  # to samo oko, ale inne konto
    make_post("2026-11-20T08:00:00.000Z", platform="tiktok"),
    make_post("2026-11-20T08:00:00.000Z", status="failed"),
    make_post("2026-11-20T08:00:00.000Z", status="cancelled"),
    make_post("2026-11-20T08:00:00.000Z", status="deleted"),
    {"_id": "P-bez-terminu", "status": "draft", "platforms": [{"platform": "instagram", "accountId": "ACC"}]},
], ids=["minuta-po", "minuta-przed", "inne-konto", "inna-platforma", "failed", "cancelled", "deleted", "bez-terminu"])
def test_ig_post_at_ignores_other_times_accounts_platforms_and_dead_posts(monkeypatch, post):
    fake_api(monkeypatch, lambda m, p, b, q: {"posts": [post]})
    assert zernio.ig_post_at("ACC", WHEN) is None


def test_ig_post_at_matches_account_given_as_object_and_timestamp_without_zone(monkeypatch):
    as_object = make_post("2026-11-20T08:00:10", account={"_id": "ACC"})  # bez „Z”: uznajemy za UTC
    fake_api(monkeypatch, lambda m, p, b, q: {"posts": [as_object]})
    assert zernio.ig_post_at("ACC", WHEN) == as_object


# --- pobieranie pliku --------------------------------------------------------

def test_download_rejects_non_mp4(monkeypatch, tmp_path, sleeps):
    dest = tmp_path / "rolka.mp4"
    serve(monkeypatch, Response(b"<html>"))
    with pytest.raises(zernio.ZernioError):
        zernio.download("https://cdn.example/x.mp4", dest)
    assert names(tmp_path) == []


def test_download_does_not_create_folders_or_part_file_for_non_mp4(monkeypatch, tmp_path):
    dest = tmp_path / "nowy" / "folder" / "rolka.mp4"
    serve(monkeypatch, Response(b"<html>" + b"x" * 50_000))
    with pytest.raises(zernio.ZernioError, match="MP4"):
        zernio.download("https://cdn.example/x.mp4", dest)
    assert names(tmp_path) == []


def test_download_streams_mp4_into_new_folder_and_leaves_no_part_file(monkeypatch, tmp_path):
    body = mp4_bytes(3_000_000)  # większy niż jedna porcja odczytu
    requests = serve(monkeypatch, Response(body, headers={"Content-Length": str(len(body))}))
    dest = tmp_path / "Łódź ąę" / "dane" / "rolka próbna.mp4"
    assert zernio.download("https://cdn.example/x.mp4?podpis=tajne", dest) == dest
    assert dest.read_bytes() == body
    assert names(dest.parent) == ["rolka próbna.mp4"]
    assert requests[0].full_url == "https://cdn.example/x.mp4?podpis=tajne"


@pytest.mark.parametrize("size, accepted", [(10_000, False), (10_001, True), (200, False)])
def test_download_needs_more_than_ten_thousand_bytes(monkeypatch, tmp_path, size, accepted):
    dest = tmp_path / "rolka.mp4"
    serve(monkeypatch, Response(mp4_bytes(size)))
    if accepted:
        zernio.download("https://cdn.example/x.mp4", dest)
        assert dest.stat().st_size == size
    else:
        with pytest.raises(zernio.ZernioError):
            zernio.download("https://cdn.example/x.mp4", dest)
        assert names(tmp_path) == []


def test_download_retries_transient_errors_then_succeeds(monkeypatch, tmp_path, sleeps):
    body = mp4_bytes()
    requests = serve(monkeypatch, urllib.error.URLError("brak sieci"),
                     urllib.error.HTTPError("https://cdn.example/x.mp4", 503, "Unavailable", None, None),
                     Response(body))
    dest = tmp_path / "rolka.mp4"
    assert zernio.download("https://cdn.example/x.mp4", dest) == dest
    assert dest.read_bytes() == body and len(requests) == 3 and sleeps == [2, 4]


def test_download_retries_connection_dropped_midway_and_leaves_no_part_file(monkeypatch, tmp_path, sleeps):
    body = mp4_bytes()
    serve(monkeypatch, DropsMidway(body), Response(body))
    dest = tmp_path / "rolka.mp4"
    zernio.download("https://cdn.example/x.mp4", dest)
    assert dest.read_bytes() == body and names(tmp_path) == ["rolka.mp4"]


def test_download_retries_when_server_sent_fewer_bytes_than_announced(monkeypatch, tmp_path, sleeps):
    body = mp4_bytes()
    requests = serve(monkeypatch, Response(body, headers={"Content-Length": str(len(body) + 500)}),
                     Response(body, headers={"Content-Length": str(len(body))}))
    dest = tmp_path / "rolka.mp4"
    zernio.download("https://cdn.example/x.mp4", dest)
    assert dest.read_bytes() == body and len(requests) == 2


def test_download_gives_up_after_given_number_of_tries(monkeypatch, tmp_path, sleeps):
    requests = serve(monkeypatch, *[DropsMidway(mp4_bytes()) for _ in range(3)])
    with pytest.raises(zernio.ZernioError, match="nie udało się pobrać"):
        zernio.download("https://cdn.example/x.mp4", tmp_path / "rolka.mp4")
    assert len(requests) == 3 and names(tmp_path) == []

    requests.clear()
    serve(monkeypatch, urllib.error.URLError("a"), urllib.error.URLError("b"))
    with pytest.raises(zernio.ZernioError):
        zernio.download("https://cdn.example/x.mp4", tmp_path / "rolka.mp4", tries=2)


def test_download_does_not_retry_client_errors_and_keeps_the_status(monkeypatch, tmp_path, sleeps):
    requests = serve(monkeypatch, urllib.error.HTTPError("https://cdn.example/x.mp4", 403, "Forbidden", None, None))
    with pytest.raises(zernio.ZernioError) as e:
        zernio.download("https://cdn.example/x.mp4", tmp_path / "rolka.mp4")
    assert e.value.status == 403 and len(requests) == 1 and sleeps == []


def test_download_failure_keeps_existing_file_untouched(monkeypatch, tmp_path):
    dest = tmp_path / "rolka.mp4"
    dest.write_bytes(b"stary plik")
    serve(monkeypatch, Response(b"<html>"))
    with pytest.raises(zernio.ZernioError):
        zernio.download("https://cdn.example/x.mp4", dest)
    assert dest.read_bytes() == b"stary plik" and names(tmp_path) == ["rolka.mp4"]


def test_download_replaces_existing_file_on_success(monkeypatch, tmp_path):
    dest = tmp_path / "rolka.mp4"
    dest.write_bytes(b"stary plik")
    body = mp4_bytes()
    serve(monkeypatch, Response(body))
    zernio.download("https://cdn.example/x.mp4", dest)
    assert dest.read_bytes() == body


def blocked_then_free(monkeypatch, failures):
    """Atrapa `os.replace`: pierwsze `failures` wywołań kończy się PermissionError (plik trzyma antywirus albo indeksator),
    potem podmienia plik naprawdę. Zwraca (czasy oczekiwania, lista prób); czas nie płynie naprawdę."""
    real_replace, waits, attempts = config.os.replace, [], []

    def replace(src, dst):
        attempts.append(1)
        if len(attempts) <= failures:
            raise PermissionError("plik jest otwarty w innym programie")
        return real_replace(src, dst)

    monkeypatch.setattr(config.os, "replace", replace)
    monkeypatch.setattr(config.time, "sleep", waits.append)
    return waits, attempts


def test_download_waits_out_a_blocked_final_rename_like_every_other_write(monkeypatch, tmp_path):
    """Na Windowsie świeżo zapisanego pliku często trzyma antywirus: to PermissionError, a nie błąd sieci."""
    body = mp4_bytes()
    requests = serve(monkeypatch, Response(body))
    waits, attempts = blocked_then_free(monkeypatch, failures=2)
    dest = tmp_path / "rolka.mp4"
    assert zernio.download("https://cdn.example/x.mp4", dest) == dest
    assert dest.read_bytes() == body and names(tmp_path) == ["rolka.mp4"]
    assert len(requests) == 1 and len(attempts) == 3 and waits == [0.1, 0.1]          # plik nie jest pobierany drugi raz


def test_download_that_cannot_save_the_file_says_so_instead_of_blaming_the_network(monkeypatch, tmp_path):
    serve(monkeypatch, Response(mp4_bytes()))
    waits, attempts = blocked_then_free(monkeypatch, failures=99)
    with pytest.raises(zernio.ZernioError) as caught:
        zernio.download("https://cdn.example/x.mp4", tmp_path / "rolka.mp4")
    text = str(caught.value)
    assert "nie mogę zapisać" in text and "rolka.mp4" in text and "antywirus" in text and "nie udało się pobrać" not in text
    assert len(attempts) == 6 and waits == [0.1] * 5 and names(tmp_path) == []        # żadnego pliku .part


@pytest.mark.parametrize("url", ["file:///etc/hosts", "ftp://cdn.example/x.mp4", "cdn.example/x.mp4", ""])
def test_download_accepts_only_http_and_https(monkeypatch, tmp_path, url):
    with pytest.raises(zernio.ZernioError, match="http"):
        zernio.download(url, tmp_path / "rolka.mp4")  # atrapa sieci z autouse nie została wywołana
    assert names(tmp_path) == []


def test_download_error_does_not_show_query_string_of_the_address(monkeypatch, tmp_path, sleeps):
    serve(monkeypatch, urllib.error.HTTPError("x", 404, "Not Found", None, None))
    with pytest.raises(zernio.ZernioError) as e:
        zernio.download("https://uzytkownik:haslo@example.com/sciezka/x.mp4?podpis=tajne#a", tmp_path / "rolka.mp4")
    text = str(e.value)
    assert "example.com/sciezka/x.mp4" in text and "podpis" not in text and "tajne" not in text
    assert "uzytkownik" not in text and "haslo" not in text
