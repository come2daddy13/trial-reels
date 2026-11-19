"""Testy kandydatów na zwycięskie rolki, wpisów puli i sprawdzania puli przed renderem.

Kody rolek, nicki i teksty są wymyślone. Kod rolki to napis z alfabetu Instagrama (A-Z, a-z, 0-9, „-”, „_”).
"""
import base64
from datetime import datetime, timedelta, timezone

import pytest

from trial_reels import candidates, captions, config, render

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
CODE = "Cabc123XYZ_"


def iso(days_ago, hours=0):
    """Czas publikacji w formacie, który zwraca Zernio (UTC z literą Z)."""
    return (NOW - timedelta(days=days_ago, hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --- kod rolki i ID mediów ------------------------------------------------------

def test_media_id_is_the_code_read_as_a_base64_number():
    expected = int.from_bytes(base64.urlsafe_b64decode("A" + CODE), "big")  # „A” to zero, więc dopełnia do 12 znaków
    assert candidates.media_id("https://www.instagram.com/reel/%s/" % CODE) == str(expected)
    assert candidates.media_id("https://www.instagram.com/reel/%s/" % CODE) == "2781944041176925823"


def test_media_id_counts_in_base_64_with_the_instagram_alphabet():
    assert candidates.media_id("https://www.instagram.com/p/AAAAAB/") == "1"
    assert candidates.media_id("https://www.instagram.com/p/AAAAA_/") == "63"
    assert candidates.media_id("https://www.instagram.com/p/AAAABA/") == "64"


@pytest.mark.parametrize("url,expected", [
    ("https://www.instagram.com/reel/%s/" % CODE, CODE),
    ("https://www.instagram.com/reel/%s" % CODE, CODE),
    ("https://www.instagram.com/reel/%s/?igsh=MXx4eXo%%3D" % CODE, CODE),
    ("https://instagram.com/reels/%s/" % CODE, CODE),
    ("https://www.instagram.com/p/%s/" % CODE, CODE),
    ("https://www.instagram.com/przyklad.konto/reel/%s/" % CODE, CODE),
    ("  %s  " % CODE, CODE),
    ("https://www.instagram.com/przyklad.konto/", None),
    ("https://example.com/", None),
    ("https://www.instagram.com/reel/ab/", None),
    ("", None),
    (None, None),
])
def test_shortcode_from_links_and_bare_codes(url, expected):
    assert candidates.shortcode(url) == expected


def test_media_id_of_something_that_is_not_a_reel_is_none():
    assert candidates.media_id("https://example.com/") is None
    assert candidates.media_id(None) is None
    assert candidates.media_id("") is None


def test_created_at_reads_the_time_inside_the_media_id():
    when = datetime(2026, 3, 14, 9, 26, 53, tzinfo=timezone.utc)
    pk = str(((int(when.timestamp() * 1000) - candidates.IG_EPOCH_MS) << 23) | 1234)
    assert candidates.created_at(pk) == when
    assert candidates.created_at("nie-liczba") is None
    assert candidates.created_at(None) is None
    assert candidates.created_at("1") is None  # taki numer wypadałby w 2011 roku, więc to nie jest ID rolki


@pytest.mark.parametrize("code,expected", [
    (CODE, True), ("AAAAAB", True), ("a-b_c-d", True),
    ("abc", False), ("", False), (None, False), (123456, False),
    ("https://www.instagram.com/reel/%s/" % CODE, False), ("../Cabc123XYZ_", False), ("Cabc 123XYZ", False),
    ("A" * 64, True), ("A" * 65, False),
])
def test_valid_code(code, expected):
    assert candidates.valid_code(code) is expected


def test_a_code_longer_than_a_file_name_should_be_is_not_read_from_an_address():
    assert candidates.shortcode("https://www.instagram.com/reel/%s/" % ("A" * 64)) == "A" * 64
    assert candidates.shortcode("https://www.instagram.com/reel/%s/" % ("A" * 65)) is None



def test_validate_reports_blur_entries_that_are_not_plain_numbers_inside_the_frame(make_reel, make_hooks, put_reel_files):
    """D6: sprawdz-pule zgłasza zły wpis blur, zanim render wstawi go do grafu filtrów ffmpeg."""
    put_reel_files(CODE)
    reel = make_reel(CODE)
    reel["blur"] = [{"t": [0, "1)':movie=x"], "box": [0, 0, 1, 0.3]}, {"t": [1, 2], "box": [0, 0, 1, 0.3]},
                    {"t": [1, 2], "box": [0.5, 0, 0.8, 0.3]}]
    problems = candidates.validate([reel], {CODE: make_hooks(3)})
    assert [p.split(": ", 1)[1].split(":")[0] for p in problems] == ["wpis nr 1 w polu blur", "wpis nr 3 w polu blur"]
    reel["blur"] = {"t": [1, 2]}
    assert len(candidates.validate([reel], {CODE: make_hooks(3)})) == 1
    reel["blur"] = [{"t": [1, 2], "box": [0, 0, 1, 0.3]}]
    assert candidates.validate([reel], {CODE: make_hooks(3)}) == []

# --- wybór kandydatów -----------------------------------------------------------

def test_select_filters_and_sorts(make_post):
    posts = [
        make_post("Aaaaaa1", 500, published=iso(30)),
        make_post("Bbbbbb2", 900, published=iso(60), likes=40, comments=5, shares=3, saves=7,
                  caption="Podpis z hashtagiem #przyklad"),
        make_post("Cccccc3", 700, published=iso(10)),
        make_post("Ddddd44", 99999, published=iso(3)),                                   # młodsza niż 7 dni
        make_post("Eeeee55", 8000, published=iso(30), product="FEED", media_type="IMAGE"),  # zdjęcie
        make_post("Ffffff6", 7000, published=iso(30), ad=True),                           # reklama
        make_post("Bbbbbb2", 100, published=iso(60)),                                     # powtórzony kod
        make_post("Gggggg7", 6000, published=iso(30), shared=False),                      # wersja próbna
        make_post("Hhhhhh8", 5000, published=iso(30), product="STORY"),                   # relacja
    ]
    got = candidates.select(posts, NOW)
    assert [c["code"] for c in got] == ["Bbbbbb2", "Cccccc3", "Aaaaaa1"]
    assert got[0] == {
        "code": "Bbbbbb2",
        "url": "https://www.instagram.com/reel/Bbbbbb2/",
        "pk": candidates.media_id("Bbbbbb2"),
        "views": 900, "likes": 40, "comments": 5, "shares": 3, "saves": 7,
        "published": iso(60),
        "caption": "Podpis z hashtagiem #przyklad",
        "media_url": "https://cdn.example.com/Bbbbbb2.mp4",
    }
    assert [c["code"] for c in candidates.select(posts, NOW, top=2)] == ["Bbbbbb2", "Cccccc3"]


def test_select_never_offers_trials_or_reels_hidden_from_the_feed(make_post):
    hidden = make_post("Aaaaaa1", 5000, published=iso(30), shared=False)
    unknown = make_post("Bbbbbb2", 100, published=iso(30))
    del unknown["isSharedToFeed"]  # brak pola nie jest odmową, odrzucamy tylko wyraźne „false”
    assert [c["code"] for c in candidates.select([hidden, unknown], NOW)] == ["Bbbbbb2"]


def test_select_keeps_the_copy_with_most_views_when_a_code_repeats(make_post):
    posts = [make_post("Aaaaaa1", 100, published=iso(30)), make_post("Aaaaaa1", 400, published=iso(30)),
             make_post("Aaaaaa1", 400, published=iso(30), caption="druga kopia")]
    got = candidates.select(posts, NOW)
    assert len(got) == 1 and got[0]["views"] == 400 and got[0]["caption"] == "Przykładowy podpis rolki"


def test_select_age_limit_is_inclusive_and_configurable(make_post):
    seven_days = make_post("Aaaaaa1", 10, published=iso(7))
    almost = make_post("Bbbbbb2", 20, published=iso(6, hours=23))
    assert [c["code"] for c in candidates.select([seven_days, almost], NOW)] == ["Aaaaaa1"]
    assert [c["code"] for c in candidates.select([seven_days, almost], NOW, min_age_days=1)] == ["Bbbbbb2", "Aaaaaa1"]
    assert candidates.select([seven_days, almost], NOW, min_age_days=30) == []


def test_select_accepts_a_naive_now_as_utc(make_post):
    posts = [make_post("Aaaaaa1", 10, published=iso(30)), make_post("Bbbbbb2", 20, published=iso(2))]
    got = candidates.select(posts, NOW.replace(tzinfo=None))
    assert [c["code"] for c in got] == ["Aaaaaa1"]


def test_select_copes_with_posts_missing_optional_fields(make_post):
    bare = make_post("Aaaaaa1", published=iso(30))
    for key in ("analytics", "mediaItems", "content", "isAd"):
        del bare[key]
    no_date = make_post("Bbbbbb2", 50)
    del no_date["publishedAt"]
    no_url = make_post("Cccccc3", 60, published=iso(30))
    del no_url["platformPostUrl"]
    got = candidates.select([bare, no_date, no_url, "to nie jest post", None], NOW)
    assert got == [{"code": "Aaaaaa1", "url": "https://www.instagram.com/reel/Aaaaaa1/",
                    "pk": candidates.media_id("Aaaaaa1"), "views": 0, "likes": 0, "comments": 0, "shares": 0,
                    "saves": 0, "published": iso(30), "caption": "", "media_url": None}]
    assert candidates.select([], NOW) == [] and candidates.select(None, NOW) == []


def test_media_url_is_the_first_media_item(make_post):
    post = make_post("Aaaaaa1")
    assert candidates.media_url(post) == "https://cdn.example.com/Aaaaaa1.mp4"
    assert candidates.media_url(make_post("Aaaaaa1", media=False)) is None
    del post["mediaItems"]
    assert candidates.media_url(post) is None
    assert candidates.media_url({"mediaItems": [{"type": "video"}]}) is None


# --- ranking i wpis do puli -----------------------------------------------------

def test_rank_prefers_follows_then_views():
    cands = [
        {"code": "A", "views": 5000},                                 # bez odczytu obserwujących
        {"code": "B", "views": 100, "panel_follows": 9},
        {"code": "C", "views": 900, "panel_follows": 9},
        {"code": "D", "views": 10, "panel_follows": 30},
        {"code": "E", "views": 8000, "panel_follows": 0},             # odczyt jest, ale obserwujących brak
    ]
    ranked, measured = candidates.rank(cands)
    assert [c["code"] for c in ranked] == ["D", "C", "B", "E", "A"]
    assert measured is True
    ranked, measured = candidates.rank([{"code": "X", "views": 1}, {"code": "Y", "views": 2}])
    assert [c["code"] for c in ranked] == ["Y", "X"] and measured is False
    assert candidates.rank([]) == ([], False)


def test_pool_entry_has_the_documented_fields():
    cand = {"code": CODE, "pk": "2781944041176925823", "views": 1,
            "caption": "🔥 Jak zdobywać klientów z Instagrama bez reklam i bez tańców"}
    assert candidates.pool_entry(cand) == {
        "code": CODE, "name": "Jak zdobywać klientów z Instagrama", "media_id": "2781944041176925823",
        "caption": cand["caption"], "active": True, "hook_y": 0.17,
    }


def test_pool_entry_name_is_five_words_without_emoji_cut_to_forty_characters():
    caption = "❤️ 🔥 Pierwsze 👇 drugie\ntrzecie, czwarte i piąte szóste"
    name = candidates.pool_entry({"code": CODE, "pk": "1", "caption": caption})["name"]
    assert name == "Pierwsze drugie trzecie, czwarte i"
    long = "Superdługiesłowoooooooooooooooo kolejnesłowoooooooooooooooo trzecie"
    name = candidates.pool_entry({"code": CODE, "pk": "1", "caption": long})["name"]
    assert name == long[:40].rstrip() and len(name) <= 40


def test_pool_entry_name_falls_back_to_the_code():
    assert candidates.pool_entry({"code": CODE, "pk": "1", "caption": ""})["name"] == CODE
    assert candidates.pool_entry({"code": CODE, "pk": "1", "caption": "🔥🔥 👇"})["name"] == CODE
    assert candidates.pool_entry({"code": CODE, "pk": "1"})["caption"] == ""


def test_pool_entry_computes_media_id_when_the_candidate_has_no_pk():
    assert candidates.pool_entry({"code": "AAAAAB", "caption": "x"})["media_id"] == "1"


# --- pula i hooki z plików ------------------------------------------------------

def test_load_and_save_pool_candidates_and_hooks(tmp_path):
    assert candidates.load_pool() == [] and candidates.load_candidates() == [] and candidates.load_hooks() == {}
    candidates.save_pool([{"code": CODE, "name": "Zażółć gęślą"}])
    candidates.save_candidates([{"code": CODE, "views": 3}])
    config.write_json(config.HOOKS, {CODE: [{"id": "h01", "text": "Tekst", "emoji": "🔥"}]})
    assert candidates.load_pool() == [{"code": CODE, "name": "Zażółć gęślą"}]
    assert candidates.load_candidates() == [{"code": CODE, "views": 3}]
    assert candidates.load_hooks()[CODE][0]["id"] == "h01"
    assert "Zażółć" in config.POOL.read_text(encoding="utf-8")


def test_loading_a_file_of_the_wrong_shape_is_a_clear_error():
    config.write_json(config.POOL, {"code": CODE})
    with pytest.raises(config.UserError, match="pula.json"):
        candidates.load_pool()
    config.write_json(config.HOOKS, [1, 2])
    with pytest.raises(config.UserError, match="hooki.json"):
        candidates.load_hooks()


# --- sprawdzanie puli -----------------------------------------------------------

def say(problems):
    return "\n".join(problems)


def test_validate_accepts_a_complete_reel(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    assert candidates.validate([make_reel()], {CODE: make_hooks()}) == []


def test_validate_skips_reels_that_are_switched_off(make_reel):
    reel = make_reel()
    reel["active"] = False
    assert candidates.validate([reel], {}) == []  # bez pliku, transkrypcji i hooków, a mimo to czysto
    assert candidates.validate([], {}) == []


def test_validate_reports_a_missing_video_file(make_reel, make_hooks, put_reel_files):
    put_reel_files(video=False)
    problems = candidates.validate([make_reel()], {CODE: make_hooks()})
    assert len(problems) == 1
    assert CODE in problems[0] and "dane/src/%s.mp4" % CODE in problems[0]


def test_validate_reports_missing_transcript_and_bad_hook(make_reel, make_hooks, put_reel_files):
    put_reel_files(transcript=False)
    hooks = make_hooks()
    hooks[0]["text"] = "x" * 51                 # za długi
    hooks[1]["emoji"] = "🦄"                    # nie ma jej w zestawie
    problems = say(candidates.validate([make_reel()], {CODE: hooks}))
    assert "brak transkrypcji" in problems and "dane/transkrypcje/%s.json" % CODE in problems
    assert "51 znaków" in problems and "limit to 50" in problems
    assert "emotki „🦄” nie ma w zestawie" in problems
    assert "h01" in problems and "h02" in problems and "h03" not in problems
    assert "strong" not in problems and "cuts" not in problems  # bez transkrypcji nie sprawdzamy fraz


def test_validate_checks_that_strong_and_cuts_are_in_the_transcript(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    reel = make_reel()
    reel["strong"] = "tego zdania nikt nie powiedział"
    reel["cuts"] = [{"from": "napisz przewodnik", "to": "w komentarzu"},
                    {"from": "tego początku nie ma", "to": "obserwuj"},
                    {"from": "napisz przewodnik", "to": "tego końca nie ma"},
                    {"from": "obserwuj", "to": None}]
    problems = candidates.validate([reel], {CODE: make_hooks()})
    assert len(problems) == 3
    assert "strong" in problems[0] and "tego zdania nikt nie powiedział" in problems[0]
    assert "cuts" in problems[1] and "tego początku nie ma" in problems[1]
    assert "cuts" in problems[2] and "tego końca nie ma" in problems[2]


# --- rolka bez mowy (transkrypcja ma 0 słów) ------------------------------------

def put_empty_transcript(code=CODE, **extra):
    """Transkrypcja rolki, w której nikt nie mówi: Whisper z filtrem głosu nie zostawia żadnego segmentu."""
    config.write_json(config.TRANSCRIPTS / ("%s.json" % code), {"segments": [], **extra})


def speechless_reel(make_reel):
    reel = make_reel()
    del reel["strong"], reel["cuts"]
    return reel


def test_speech_words_counts_the_words_of_a_transcript(put_reel_files):
    assert candidates.speech_words(CODE) is None                       # transkrypcji nie ma
    put_reel_files()
    assert candidates.speech_words(CODE) == 12
    put_empty_transcript()
    assert candidates.speech_words(CODE) == 0
    config.write_json(config.TRANSCRIPTS / ("%s.json" % CODE),
                      {"segments": [{"start": 0, "end": 1, "text": "", "words": []}, {"start": 1, "end": 2, "text": ""}]})
    assert candidates.speech_words(CODE) == 0                          # segmenty bez słów to też cisza
    config.write_json(config.TRANSCRIPTS / ("%s.json" % CODE), {"zle": "to nie transkrypcja"})
    assert candidates.speech_words(CODE) is None
    (config.TRANSCRIPTS / ("%s.json" % CODE)).write_text("{nie json", encoding="utf-8")
    assert candidates.speech_words(CODE) is None                       # uszkodzony plik to nie „rolka bez mowy”


def test_validate_does_not_require_strong_or_cuts_for_a_reel_without_speech(make_reel, make_hooks, put_reel_files):
    put_reel_files(transcript=False)
    put_empty_transcript()
    reel = speechless_reel(make_reel)
    assert "strong" not in reel and "cuts" not in reel
    assert candidates.validate([reel], {CODE: make_hooks()}) == []        # bez trzeciego argumentu działa jak dawniej
    notes = []
    assert candidates.validate([reel], {CODE: make_hooks()}, notes) == []
    assert len(notes) == 1
    assert CODE in notes[0] and "Przykładowa rolka" in notes[0]
    assert "bez mowy" in notes[0] and "0 słów" in notes[0] and "strong" in notes[0] and "cuts" in notes[0]


def test_validate_says_nothing_about_speech_for_a_reel_that_has_it(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    notes = []
    assert candidates.validate([make_reel()], {CODE: make_hooks()}, notes) == [] and notes == []
    reel = make_reel()
    del reel["strong"], reel["cuts"]                                      # mowa jest, a strong i cuts nie są wymagane
    assert candidates.validate([reel], {CODE: make_hooks()}, notes) == [] and notes == []


def test_validate_notes_a_reel_without_speech_only_when_its_transcript_is_empty_and_readable(
        make_reel, make_hooks, put_reel_files):
    missing, damaged, silent, off = "Dddddd44", "Eeeeee55", "Ffffff66", "Gggggg77"
    for code in (missing, damaged, silent):
        put_reel_files(code, transcript=False)                           # każda ma film, transkrypcje różnią się
    (config.TRANSCRIPTS).mkdir(parents=True, exist_ok=True)
    (config.TRANSCRIPTS / ("%s.json" % damaged)).write_text("{nie json", encoding="utf-8")
    put_empty_transcript(silent)
    put_empty_transcript(off)                                            # rolka wyłączona, więc w ogóle jej nie sprawdzamy
    pool = []
    for code in (missing, damaged, silent, off):
        reel = speechless_reel(make_reel)
        reel["code"] = code
        pool.append(reel)
    pool[-1]["active"] = False
    notes = []
    problems = candidates.validate(pool, {code: make_hooks() for code in (missing, damaged, silent, off)}, notes)
    assert len(notes) == 1 and silent in notes[0]                         # tylko pusta i czytelna transkrypcja
    assert len(problems) == 1 and missing in problems[0] and "brak transkrypcji" in problems[0]


def test_validate_a_reel_without_speech_that_still_has_strong_or_cuts_is_one_clear_problem(make_reel, make_hooks,
                                                                                         put_reel_files):
    put_reel_files(transcript=False)
    put_empty_transcript()
    notes = []
    problems = candidates.validate([make_reel()], {CODE: make_hooks()}, notes)     # make_reel ma strong i cuts
    assert len(problems) == 1 and notes == []
    assert CODE in problems[0] and "nie ma mowy" in problems[0] and "0 słów" in problems[0]
    assert "strong" in problems[0] and "cuts" in problems[0] and "Usuń" in problems[0]
    assert "nie ma w transkrypcji" not in problems[0]                         # jedna wskazówka zamiast skargi na każdą frazę


def test_validate_reports_a_damaged_transcript_instead_of_crashing(make_reel, make_hooks, put_reel_files):
    put_reel_files(transcript=False)
    config.write_json(config.TRANSCRIPTS / ("%s.json" % CODE), {"zle": "to nie transkrypcja"})
    problems = say(candidates.validate([make_reel()], {CODE: make_hooks()}))
    assert "transkrypcja jest uszkodzona" in problems


def test_validate_checks_the_cta_and_its_variants(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    reel = make_reel()
    reel["cta"] = "Napisz „INNE” do @przyklad.konto"                 # tego tekstu nie ma w podpisie
    reel["caption"] = "Sam podpis bez wezwania"
    problems = say(candidates.validate([reel], {CODE: make_hooks()}))
    assert "pola cta nie ma w podpisie" in problems

    reel = make_reel()
    reel["cta_variants"] = ["Skomentuj „PRZEWODNIK” i obserwuj @inne.konto",       # zły nick
                            "Skomentuj w komentarzu i obserwuj @przyklad.konto",  # brak słowa-klucza
                            "Zostaw „PRZEWODNIK” i obserwuj @przyklad.konto"]        # dobry
    problems = candidates.validate([reel], {CODE: make_hooks()})
    assert len(problems) == 2
    assert "@inne.konto" in problems[0] and "gubi: @przyklad.konto" in problems[0]
    assert "w komentarzu" in problems[1] and "gubi: „PRZEWODNIK”" in problems[1]


@pytest.mark.parametrize("cta", ["brak pola", None, "", "   "])
def test_validate_skips_every_cta_check_when_the_reel_has_no_cta(make_reel, make_hooks, put_reel_files, cta):
    """Wezwanie do działania jest opcjonalne: bez niego nie ma co sprawdzać w podpisie ani w wariantach."""
    put_reel_files()
    reel = make_reel()
    reel["caption"] = "Sam podpis bez wezwania"
    reel["cta_variants"] = ["Skomentuj „INNE” i obserwuj @inne.konto",       # u rolki z cta: gubi nick i słowo-klucz
                            "Zostaw komentarz — i obserwuj"]                  # u rolki z cta: długi myślnik
    del reel["cta"]
    if cta != "brak pola":
        reel["cta"] = cta
    assert candidates.validate([reel], {CODE: make_hooks()}) == []


def test_validate_still_checks_extras_and_caption_length_when_there_is_no_cta(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    reel = make_reel()
    del reel["cta"]
    reel["extras"] = ["Jeden.", "Dwa — trzy.", "Cztery."]
    problems = say(candidates.validate([reel], {CODE: make_hooks()}))
    assert "extras" in problems and "jest 3" in problems and "myślnik" in problems
    reel["extras"] = ["Jeden.", "Dwa.", "Trzy.", "Cztery."]
    reel["caption"] = "A" * 2300
    assert "podpis wersji 4 ma 2309 znaków" in say(candidates.validate([reel], {CODE: make_hooks()}))   # najdłuższy dopisek


def test_validate_still_checks_the_cta_when_there_is_one(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    reel = make_reel()
    reel["cta_variants"] = ["Skomentuj „INNE” i obserwuj @inne.konto"]
    assert len(candidates.validate([reel], {CODE: make_hooks()})) == 1


def test_validate_reports_a_cta_that_is_not_text(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    reel = make_reel()
    reel["cta"] = ["to nie jest tekst"]
    problems = candidates.validate([reel], {CODE: make_hooks()})
    assert len(problems) == 1 and "cta" in problems[0] and "tekstem" in problems[0]


def test_validate_requires_four_extras_without_dashes(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    reel = make_reel()
    reel["extras"] = ["Jeden.", "Dwa.", "Trzy."]
    problems = say(candidates.validate([reel], {CODE: make_hooks()}))
    assert "extras" in problems and "jest 3" in problems and "co najmniej 4" in problems

    reel = make_reel()
    reel["extras"][2] = "Zapisz to — przyda się"
    reel["cta_variants"][1] = "Zostaw „PRZEWODNIK” — obserwuj @przyklad.konto"
    problems = candidates.validate([reel], {CODE: make_hooks()})
    assert len(problems) == 2 and all("myślnik" in p for p in problems)


def test_validate_limits_every_composed_caption_to_2200_characters(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    reel = make_reel()
    reel["caption"] = "A" * 1900 + "\n\n" + reel["cta"]  # wersje 1-3 mieszczą się w limicie
    reel["extras"][3] = "D" * 300                          # dopiero czwarta wersja (i co czwarta po niej) go przekracza
    problems = candidates.validate([reel], {CODE: make_hooks()})
    assert len(problems) == 1
    assert "podpis wersji 4" in problems[0] and "2200" in problems[0]


def test_validate_checks_captions_until_they_start_repeating(make_reel, make_hooks, put_reel_files):
    """Zaproszenie i dopisek rotują osobno, więc najdłuższa para trafia się dopiero w wersji 20, a nie w pierwszych 12."""
    put_reel_files()
    reel = make_reel()
    reel["cta_variants"] = ["Skomentuj „PRZEWODNIK”, a wyślę ci poradnik. Zaobserwuj @przyklad.konto",
                            "Zostaw „PRZEWODNIK” pod rolką i obserwuj @przyklad.konto",
                            "Napisz „PRZEWODNIK” i obserwuj @przyklad.konto " + "w" * 600]       # 4 wersje zaproszenia
    reel["extras"] = ["Zapisz.", "Wyślij dalej.", "Wróć za tydzień.", "Pokaż zespołowi.", "e" * 600]    # 5 dopisków
    reel["caption"] = "A" * 1000 + "\n\n" + reel["cta"]
    assert captions.compose(reel, 3) != captions.compose(reel, 19) and len(captions.compose(reel, 19)) > 2200
    assert all(len(captions.compose(reel, n)) <= 2200 for n in range(19))        # wcześniej żaden podpis nie przekracza
    problems = candidates.validate([reel], {CODE: make_hooks()})
    assert len(problems) == 1 and "podpis wersji 20 ma" in problems[0] and "2200" in problems[0]


def test_plan_problems_are_only_about_hooks_and_captions(make_reel, make_hooks):
    emoji_ok = set(render.emoji_set())
    reel = make_reel()
    assert candidates.plan_problems(reel, {CODE: make_hooks(1)}, emoji_ok) == []     # jeden hook wystarczy do planu
    bank = make_hooks(3)
    bank[1]["text"] = "x" * 51
    bank[2]["emoji"] = "🦄"
    problems = candidates.plan_problems(reel, {CODE: bank}, emoji_ok)
    assert len(problems) == 2 and "tekst ma 51 znaków, a limit to 50" in problems[0]
    assert "„🦄” nie ma w zestawie" in problems[1]
    assert all(p.startswith("Rolka Przykładowa rolka (%s): " % CODE) for p in problems)
    reel["extras"] = ["Z" * 2300] * 4                                                 # brak plików nie jest tu problemem
    assert any("podpis wersji 1 ma" in p for p in candidates.plan_problems(reel, {CODE: make_hooks()}, emoji_ok))
    assert candidates.reel_label({"code": CODE}) == "Rolka %s" % CODE


def test_validate_hook_bank_rules(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    assert "za mało hooków" in say(candidates.validate([make_reel()], {CODE: make_hooks(2)}))
    assert "jest 0" in say(candidates.validate([make_reel()], {}))
    assert "jest 0" in say(candidates.validate([make_reel()], {CODE: "to nie lista"}))

    hooks = make_hooks(4)
    hooks[1]["id"] = "h01"                                # powtórzone id
    del hooks[2]["emoji"]                                 # brak emotki
    hooks[3]["emoji"] = "\u2764\ufe0f"                    # serce z niewidocznym znakiem U+FE0F
    problems = say(candidates.validate([make_reel()], {CODE: hooks}))
    assert "id „h01” powtarza się" in problems
    assert "brak emotki" in problems
    assert "U+FE0F" in problems


def test_validate_hook_text_must_exist_and_stay_free_of_emoji(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    hooks = make_hooks()
    hooks[0]["text"] = ""
    hooks[1]["text"] = "Hook z emotką 🔥 w tekście"
    problems = say(candidates.validate([make_reel()], {CODE: hooks}))
    assert "hook h01: brak tekstu" in problems
    assert "hook h02: w tekście jest emotka" in problems


def test_validate_names_the_reel_in_every_message(make_reel, put_reel_files):
    put_reel_files(video=False)
    problems = candidates.validate([make_reel()], {})
    assert problems and all(CODE in p and "Przykładowa rolka" in p for p in problems)


def test_validate_walks_every_active_reel(make_reel, make_hooks, put_reel_files):
    put_reel_files()
    put_reel_files("Dddddd44", video=False)
    problems = candidates.validate([make_reel(), make_reel("Dddddd44")],
                                   {CODE: make_hooks(), "Dddddd44": make_hooks()})
    assert len(problems) == 1 and "Dddddd44" in problems[0]


def test_validate_survives_a_pool_entry_without_a_code():
    problems = candidates.validate([{"name": "Bez kodu"}], {})
    assert len(problems) == 1 and "kodu" in problems[0]


def test_validate_rejects_codes_that_would_not_make_a_file_name(make_reel, make_hooks, put_reel_files):
    for bad in ("https://www.instagram.com/reel/%s/" % CODE, "../etc/passwd", "kr\u00f3tki"):
        reel = make_reel()
        reel["code"] = bad
        problems = candidates.validate([reel], {bad: make_hooks()})
        assert len(problems) == 1 and "niedozwolone znaki" in problems[0], bad
