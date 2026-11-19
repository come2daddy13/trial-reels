"""Testy podpisów wersji triala: wariant CTA zachowuje @nick i słowo-klucz, a dopisek zmienia tekst każdej wersji."""
import copy

import pytest

from trial_reels import captions

SLEEP_CTA = "Zaobserwuj @przyklad.konto i napisz „SEN” w komentarzu 🔥"
PLAN_CTA = "Napisz „PLAN” w komentarzu, a wyślę ci szablon."


@pytest.fixture
def pool():
    """Trzy wymyślone rolki: z @nickiem i słowem-kluczem, tylko ze słowem-kluczem i bez wariantów CTA."""
    return [
        {
            "name": "Rolka o śnie",
            "code": "Cabc123XYZ_",
            "caption": "Trzy proste zmiany, po których śpisz lepiej. Sprawdź je w tydzień.\n\n" + SLEEP_CTA,
            "cta": SLEEP_CTA,
            "cta_variants": [
                "Napisz „SEN” w komentarzu i zaobserwuj @przyklad.konto 🔥",
                "Zaobserwuj @przyklad.konto, a „SEN” zostaw w komentarzu 🔥",
                "Chcesz więcej? Zaobserwuj @przyklad.konto i wpisz „SEN” pod rolką 🔥",
            ],
            "extras": [
                "Zapisz tę rolkę na później.",
                "Wyślij ją komuś, kto słabo śpi.",
                "Daj znać w komentarzu, co u ciebie działa.",
                "Więcej takich rolek znajdziesz na profilu.",
                "Którą zmianę wypróbujesz pierwszą?",
            ],
        },
        {
            "name": "Rolka o planowaniu",
            "code": "Cdef456UVW-",
            "caption": "Zaplanuj cały tydzień w 10 minut.\n\n" + PLAN_CTA,
            "cta": PLAN_CTA,
            "cta_variants": [
                "Zostaw „PLAN” w komentarzu, to wyślę ci szablon.",
                "Wpisz „PLAN” pod rolką, a dostaniesz szablon.",
            ],
            "extras": ["Zapisz na później.", "Wyślij komuś z zespołu.", "Wróć do tego w poniedziałek.", "Działa też w pracy."],
        },
        {
            "name": "Rolka bez wariantów CTA",
            "code": "Cghi789RST_",
            "caption": "Jak zaparzyć dobrą kawę w domu, bez ekspresu.",
            "extras": ["Zapisz na później.", "Pokaż to komuś, kto pije kawę.", "Co zmieniasz w swojej kawie?", "Więcej na profilu."],
        },
    ]


def test_caption_variants_keep_cta_and_change_text_each_version(pool):
    for r in pool:
        if r.get("cta_variants"):
            assert r["cta"] in r["caption"], r["name"]
            for v in r["cta_variants"]:
                assert captions.must_keep(r["cta"]) <= captions.must_keep(v), (r["name"], v)
        added = r.get("cta_variants", []) + r.get("extras", [])
        assert len(r.get("extras", [])) >= 4, r["name"]
        assert not [x for x in added if "—" in x], r["name"]  # bez myślników
        texts = [captions.compose(r, n) for n in range(12)]
        assert all(a != b for a, b in zip(texts, texts[1:])), r["name"]
        assert len(set(texts[:4])) == 4 and all(t != r["caption"] for t in texts), r["name"]
        assert max(len(t) for t in texts) <= 2200, r["name"]


def test_every_version_keeps_the_opening_line_and_the_cta_essentials(pool):
    for r in pool:
        opening = r["caption"].split("\n")[0]
        for n in range(12):
            text = captions.compose(r, n)
            assert text.startswith(opening), (r["name"], n)
            if r.get("cta"):
                assert captions.must_keep(r["cta"]) <= captions.must_keep(text), (r["name"], n)


def test_caption_keyword_cta_rotates_original_first():
    reel = {"caption": "Skomentuj „PLAN” 🔥", "cta": "Skomentuj „PLAN” 🔥",
            "cta_variants": ["Napisz „PLAN” w komentarzu"], "extras": ["A", "B", "C"]}
    assert captions.compose(reel, 0) == "Skomentuj „PLAN” 🔥\n\nA"
    assert captions.compose(reel, 1) == "Napisz „PLAN” w komentarzu\n\nB"
    assert captions.must_keep("Zaobserwuj @przyklad.konto, serio 🔥") == {"@przyklad.konto"}


def test_must_keep_collects_handles_and_quoted_keywords():
    assert captions.must_keep(SLEEP_CTA) == {"@przyklad.konto", "„SEN”"}
    assert captions.must_keep("Napisz „SEN” i zaobserwuj @przyklad.konto.") == {"„SEN”", "@przyklad.konto"}  # kropka kończy zdanie
    assert captions.must_keep("Bez niczego do zachowania") == set()


def test_variant_that_loses_handle_or_keyword_is_detected():
    needed = captions.must_keep(SLEEP_CTA)
    assert not needed <= captions.must_keep("Napisz „SEN” w komentarzu 🔥")  # zniknął @nick
    assert not needed <= captions.must_keep("Zaobserwuj @przyklad.konto i napisz w komentarzu 🔥")  # zniknęło słowo-klucz
    assert not needed <= captions.must_keep("Zaobserwuj @inne.konto i napisz „SEN” w komentarzu 🔥")  # inny @nick


def test_compose_without_variants_only_appends_extras():
    reel = {"caption": "Treść rolki", "extras": ["A", "B"]}
    assert [captions.compose(reel, n) for n in range(3)] == ["Treść rolki\n\nA", "Treść rolki\n\nB", "Treść rolki\n\nA"]


@pytest.mark.parametrize("cta", ["brak pola", None, "", "   ", ["lista zamiast tekstu"]])
def test_compose_without_a_cta_only_appends_extras_even_when_variants_are_there(cta):
    """Rolka nie musi mieć wezwania do działania: bez `cta` podpis się nie zmienia, a dopiski rotują jak zwykle."""
    reel = {"caption": "Treść z „PLAN” w środku", "cta_variants": ["Inne „PLAN”"], "extras": ["A", "B", "C", "D"]}
    if cta != "brak pola":
        reel["cta"] = cta
    assert [captions.compose(reel, n) for n in range(5)] == [
        "Treść z „PLAN” w środku\n\nA", "Treść z „PLAN” w środku\n\nB", "Treść z „PLAN” w środku\n\nC",
        "Treść z „PLAN” w środku\n\nD", "Treść z „PLAN” w środku\n\nA"]


def test_compose_without_a_cta_and_without_extras_is_the_plain_caption():
    assert captions.compose({"caption": "Sam podpis", "cta": "", "cta_variants": ["x"]}, 3) == "Sam podpis"


def test_compose_without_extras_only_rotates_cta():
    reel = {"caption": "Zobacz „X” teraz", "cta": "Zobacz „X” teraz", "cta_variants": ["Sprawdź „X” teraz"]}
    assert [captions.compose(reel, n) for n in range(3)] == ["Zobacz „X” teraz", "Sprawdź „X” teraz", "Zobacz „X” teraz"]


def test_compose_leaves_caption_alone_when_cta_is_not_in_it():
    reel = {"caption": "Inna treść", "cta": "Zobacz „X”", "cta_variants": ["Sprawdź „X”"]}
    assert captions.compose(reel, 1) == "Inna treść"


def test_compose_replaces_only_the_first_occurrence_of_cta():
    reel = {"caption": "Zobacz „X”. Jeszcze raz: Zobacz „X”.", "cta": "Zobacz „X”", "cta_variants": ["Sprawdź „X”"]}
    assert captions.compose(reel, 1) == "Sprawdź „X”. Jeszcze raz: Zobacz „X”."


def test_compose_strips_trailing_whitespace_before_extra():
    assert captions.compose({"caption": "Treść  \n\n", "extras": ["Dopisek"]}, 0) == "Treść\n\nDopisek"


def test_compose_of_bare_reel_is_empty_and_never_changes_the_reel(pool):
    assert captions.compose({}, 5) == ""
    before = copy.deepcopy(pool)
    for r in pool:
        for n in range(6):
            captions.compose(r, n)
    assert pool == before


# --- okres rotacji podpisów --------------------------------------------------------

def test_period_is_the_least_common_multiple_of_the_cta_options_and_the_extras():
    reel = {"caption": "Zobacz „X”", "cta": "Zobacz „X”", "cta_variants": ["A „X”", "B „X”", "C „X”"],
            "extras": ["1", "2", "3", "4", "5"]}
    assert captions.period(reel) == 20                                    # 4 wersje zaproszenia (z oryginałem) i 5 dopisków
    texts = [captions.compose(reel, n) for n in range(60)]
    assert texts[:20] == texts[20:40] == texts[40:] and len(set(texts[:20])) == 20     # po 20 wersjach podpisy się powtarzają


@pytest.mark.parametrize("reel,expected", [
    ({"caption": "Treść", "extras": ["A", "B", "C", "D"]}, 4),                                   # bez zaproszenia rotują same dopiski
    ({"caption": "Zobacz „X”", "cta": "Zobacz „X”", "cta_variants": ["A „X”"]}, 2),             # bez dopisków rotuje samo zaproszenie
    ({"caption": "Treść"}, 1),                                                                   # nic nie rotuje
    ({"caption": "Treść", "cta": "Zobacz „X”", "cta_variants": ["A „X”"], "extras": ["a", "b", "c"]}, 3),   # cta nie ma w podpisie
    ({"caption": "Zobacz „X”", "cta": "Zobacz „X”", "cta_variants": ["A „X”", "B „X”"], "extras": list("abcd")}, 12),
    ({"caption": "Zobacz „X”", "cta": "Zobacz „X”", "cta_variants": ["A „X”"], "extras": list("abcdef")}, 6),
    ({"caption": None, "cta": "Zobacz „X”", "cta_variants": ["A „X”"], "extras": 7}, 1),         # zły format: błąd zgłosi compose
    ({}, 1),
])
def test_period_follows_what_compose_really_rotates(reel, expected):
    assert captions.period(reel) == expected
    if isinstance(reel.get("extras"), list) or "extras" not in reel:
        texts = [captions.compose(reel, n) for n in range(expected * 3)]
        assert texts[:expected] == texts[expected:expected * 2] == texts[expected * 2:]

