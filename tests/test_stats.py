"""Testy odczytu wyników z panelu Instagrama: parser liczb, skrypt dla przeglądarki i lista wersji do odczytu.

Skrypt z panelu uruchamiamy w Node z atrapą strony (jeśli Node jest zainstalowany), więc sprawdzamy jego działanie,
a nie tylko tekst.
"""
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trial_reels import planner, stats

WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=WARSAW)


# --- parser liczb ---------------------------------------------------------------

@pytest.mark.parametrize("raw,val", [("1234", 1234), ("1 234", 1234), ("1\u00a0234", 1234), ("12,3 tys.", 12300),
                                     ("1,2 mln", 1200000), ("1.2K", 1200), ("1.2M", 1200000), ("12,345", 12345),
                                     ("0", 0)])
def test_parse_count(raw, val):
    assert stats.parse_count(raw) == val


@pytest.mark.parametrize("raw,val", [
    ("1\u202f234", 1234),            # wąska spacja, taką daje część systemów
    ("  12,3 TYS.  ", 12300),        # wielkie litery i spacje na brzegach
    ("12,3tys", 12300),              # bez kropki i bez spacji
    ("2 mln", 2000000),
    ("1,25 tys.", 1250),
    ("0,5 mln", 500000),
    ("1 234 tys.", 1234000),         # spacja w liczbie przy skrócie
    ("1,0005 tys.", 1001),           # zaokrąglenie od połowy w górę, bez błędów zmiennoprzecinkowych
    ("1.234", 1234),                 # bez skrótu każdy separator to tysiące
    ("1,234,567", 1234567),
    (1234, 1234),
])
def test_parse_count_edge_cases(raw, val):
    assert stats.parse_count(raw) == val


@pytest.mark.parametrize("raw", ["", "   ", "abc", "12 abc", "tys.", "1.2.3 tys.", "-5", "1,2,3 mln", ".", None])
def test_parse_count_rejects_what_is_not_a_number(raw):
    with pytest.raises(ValueError):
        stats.parse_count(raw)


def test_parse_count_error_is_in_polish():
    with pytest.raises(ValueError, match="Nie rozumiem liczby"):
        stats.parse_count("bardzo dużo")


# --- skrypt dla przeglądarki ----------------------------------------------------

def test_js_odczyt_only_reads_the_page():
    js = stats.JS_ODCZYT
    for label in ("Wyświetlenia", "Obserwowanie", "Views", "Follows", "20000"):
        assert label in js
    for forbidden in ("fetch(", "XMLHttpRequest", ".click(", "sendBeacon", "localStorage", "document.cookie",
                      "WebSocket", ".submit(", "dispatchEvent", "window.open", "location.href =", "location.assign",
                      "eval("):
        assert forbidden not in js, forbidden


HARNESS = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let clock = 0, reads = 0;
Date.now = () => (clock += input.step);
global.setTimeout = (fn) => { fn(); return 0; };
global.location = { pathname: input.pathname };
global.document = { body: {} };
Object.defineProperty(global.document.body, 'innerText', {
  get() { reads += 1; return reads > input.early_reads ? input.text : input.early_text; },
});
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction(input.script)().then(out => process.stdout.write(JSON.stringify({ out, reads })));
"""

PL_PAGE = ("Statystyki rolki\nWyświetlenia\nWyświetlenia\n12\u00a0345\nPolubienia\n812\n"
           "Aktywność w profilu\nOdwiedziny profilu\n77\nObserwowanie\n9\n")
EN_PAGE = ("Reel insights\nViews\nViews\n12.3K\nLikes\n812\n"
           "Profile activity\nProfile visits\n77\nFollows\n9\n")


def run_page(tmp_path, text, pathname="/insights/media/555/", early_reads=0, early_text="", step=1000):
    """Uruchamia JS_ODCZYT w Node na atrapie strony. Zwraca (wynik jako słownik, ile razy skrypt czytał stronę)."""
    # W konsoli przeglądarki wartością skryptu jest ostatnie wyrażenie. W Node dajemy mu `return`.
    script = stats.JS_ODCZYT
    cut = script.rindex("JSON.stringify(")
    script = script[:cut] + "return " + script[cut:]
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    payload = json.dumps({"script": script, "text": text, "pathname": pathname, "early_reads": early_reads,
                          "early_text": early_text, "step": step})
    done = subprocess.run(["node", str(harness)], input=payload, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    assert done.returncode == 0, done.stderr
    data = json.loads(done.stdout)
    return json.loads(data["out"]), data["reads"]


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="do sprawdzenia skryptu potrzebny jest Node")


@needs_node
def test_js_odczyt_reads_the_polish_panel(tmp_path):
    out, _ = run_page(tmp_path, PL_PAGE)
    assert out == {"pk": "555", "views_raw": "12\u00a0345", "follows_raw": "9", "lang": "pl"}
    assert stats.parse_count(out["views_raw"]) == 12345 and stats.parse_count(out["follows_raw"]) == 9


@needs_node
def test_js_odczyt_reads_the_english_panel(tmp_path):
    out, _ = run_page(tmp_path, EN_PAGE)
    assert out == {"pk": "555", "views_raw": "12.3K", "follows_raw": "9", "lang": "en"}
    assert stats.parse_count(out["views_raw"]) == 12300


@needs_node
def test_js_odczyt_waits_until_both_labels_are_there(tmp_path):
    early = "Wyświetlenia\nWyświetlenia\n12 345\n"  # liczba wyświetleń jest, obserwowania jeszcze nie
    out, reads = run_page(tmp_path, PL_PAGE, early_reads=3, early_text=early)
    assert out["follows_raw"] == "9" and out["lang"] == "pl"
    assert reads == 4


@needs_node
def test_js_odczyt_gives_up_after_twenty_seconds_and_says_why(tmp_path):
    out, reads = run_page(tmp_path, "Coś zupełnie innego na stronie\nBez liczb", step=7000)
    assert out["pk"] == "555" and "error" in out and out["login"] is False
    assert "views_raw" not in out and "follows_raw" not in out
    assert 2 <= reads <= 5                                    # skrypt nie czeka w nieskończoność
    assert "Coś zupełnie innego" in out["tekst"]               # fragment strony pomaga ustalić, co poszło nie tak


@needs_node
def test_js_odczyt_recognizes_the_login_page(tmp_path):
    out, _ = run_page(tmp_path, "Zaloguj się\nNazwa użytkownika\nHasło", pathname="/accounts/login/", step=9000)
    assert out["login"] is True and "error" in out
    out, _ = run_page(tmp_path, "Log in\nPhone number, username or email", pathname="/insights/media/9/", step=9000)
    assert out["login"] is True and out["pk"] == "9"


# --- lista wersji do odczytu ----------------------------------------------------

@pytest.fixture(autouse=True)
def polish_time():
    planner.set_tz("Europe/Warsaw")  # strefa wraca po teście sama (conftest)


def version(vid, code, age_days, *, hours=0, **extra):
    slot = (NOW - timedelta(days=age_days, hours=hours)).strftime("%Y-%m-%dT%H:%M:00")
    v = {"id": vid, "code": code, "slot": slot, "status": "opublikowana",
         "ig_url": "https://www.instagram.com/reel/%s/" % ("A" * 8 + vid[-3:]), "ig_media_id": "9%s" % vid[-3:]}
    v.update(extra)
    return v


def as_dict(*versions):
    return {v["id"]: v for v in versions}


def test_panel_url():
    assert stats.panel_url("123456") == "https://www.instagram.com/insights/media/123456/"


def test_todo_takes_published_versions_aged_3_to_35_days():
    vs = as_dict(
        version("TR-001", "R1", 2, hours=23),                   # za świeża (2 dni)
        version("TR-002", "R1", 3),                             # równo 3 dni: już można
        version("TR-003", "R1", 20),
        version("TR-004", "R1", 35),                            # ostatni dzień odczytów
        version("TR-005", "R1", 36),                            # za stara
        version("TR-006", "R1", 10, status="zaplanowana"),      # jeszcze nie wyszła
        version("TR-007", "R1", 10, status="blad"),
        version("TR-008", "R1", 10, skip_stats=True),           # wyłączona z pomiaru
    )
    assert [t["id"] for t in stats.todo(vs, NOW, sample=False)] == ["TR-004", "TR-003", "TR-002"]


def test_todo_item_has_id_pk_and_english_panel_url_only():
    vs = as_dict(version("TR-010", "R1", 5, ig_media_id="2781944041176925823"))
    assert stats.todo(vs, NOW, sample=False) == [
        {"id": "TR-010", "pk": "2781944041176925823",
         "url": "https://www.instagram.com/insights/media/2781944041176925823/?hl=en"}]


def test_todo_urls_always_end_with_hl_en_so_panel_labels_are_english():
    vs = as_dict(version("TR-013", "R1", 5), version("TR-014", "R2", 9), version("TR-015", "R3", 12))
    urls = [item["url"] for item in stats.todo(vs, NOW, sample=False)]
    assert len(urls) == 3 and all(u.endswith("/?hl=en") for u in urls)
    assert all(u.startswith("https://www.instagram.com/insights/media/") for u in urls)
    assert sorted(item["url"] for item in stats.todo(vs, NOW, sample=True)) == sorted(urls)  # próbka też


def test_todo_works_out_the_pk_from_the_reel_link_when_the_version_has_none():
    v = version("TR-011", "R1", 5, ig_url="https://www.instagram.com/reel/AAAAAB/")
    del v["ig_media_id"]
    lost = version("TR-012", "R1", 5)
    del lost["ig_media_id"]
    del lost["ig_url"]
    got = stats.todo(as_dict(v, lost), NOW, sample=False)
    assert got == [{"id": "TR-011", "pk": "1", "url": "https://www.instagram.com/insights/media/1/?hl=en"}]


def test_todo_skips_versions_read_in_the_last_6_days():
    five_days = (NOW - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
    six_days = (NOW - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M")
    vs = as_dict(
        version("TR-020", "R1", 12, read_at=five_days),         # czytana 5 dni temu: za wcześnie
        version("TR-021", "R1", 12, read_at=six_days),          # 6 dni: czas na nowy odczyt
        version("TR-022", "R1", 12),                            # nigdy nie czytana
        version("TR-023", "R1", 12, read_at="nie-data"),        # zepsuty zapis daty nie blokuje odczytu
    )
    assert [t["id"] for t in stats.todo(vs, NOW, sample=False)] == ["TR-021", "TR-022", "TR-023"]


def test_stats_todo_sample_one_newest_per_reel():
    vs = as_dict(
        version("TR-030", "R1", 20), version("TR-031", "R1", 10), version("TR-032", "R1", 5),
        version("TR-033", "R2", 8), version("TR-034", "R2", 30),
        version("TR-035", "R3", 2),                              # za świeża, więc R3 nie ma próbki
    )
    sample = stats.todo(vs, NOW, sample=True)
    assert sorted(t["id"] for t in sample) == ["TR-032", "TR-033"]
    assert [t["id"] for t in stats.todo(vs, NOW, sample=False)] == ["TR-034", "TR-030", "TR-031", "TR-033", "TR-032"]


def test_todo_sample_ignores_versions_that_are_not_due():
    yesterday = (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    vs = as_dict(version("TR-040", "R1", 20), version("TR-041", "R1", 5, read_at=yesterday))
    assert [t["id"] for t in stats.todo(vs, NOW, sample=True)] == ["TR-040"]  # najnowsza była czytana wczoraj


def test_todo_accepts_a_list_and_nothing_at_all():
    assert [t["id"] for t in stats.todo([version("TR-050", "R1", 5)], NOW, sample=False)] == ["TR-050"]
    assert stats.todo({}, NOW, sample=False) == [] and stats.todo({}, NOW, sample=True) == []


def test_todo_counts_days_in_the_planner_time_zone():
    planner.set_tz("Asia/Tokyo")
    now = datetime(2026, 11, 20, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    slot = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:00")
    vs = {"TR-060": {"id": "TR-060", "code": "R1", "slot": slot, "status": "opublikowana", "ig_media_id": "7"}}
    assert [t["id"] for t in stats.todo(vs, now, sample=False)] == ["TR-060"]
