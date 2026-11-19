"""Wspólna konfiguracja testów: każdy test pracuje na własnym, pustym folderze klienta."""
import sys
from pathlib import Path

import pytest

# Pozwala uruchomić testy także samym `pytest`, nie tylko przez `python -m pytest`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trial_reels import config, planner  # noqa: E402

# Zmienne, które na komputerze deweloperskim mogłyby podmienić dane testu na prawdziwe.
CLEARED_ENV = (
    "ZERNIO_API_KEY",
    "TRIAL_REELS_RELEASES_URL",
    "TRIAL_REELS_STRAZNIK_LISTA",
    "TRIAL_REELS_ROOT",
)


@pytest.fixture(autouse=True)
def client_folder(tmp_path, monkeypatch):
    """Dane testu leżą w tmp_path/klient, a zmienne z prawdziwego otoczenia nie wpływają na wynik.

    Strefa planera (`planner.set_tz`) też wraca po teście do poprzedniej, więc komenda, która ją ustawia, nie psuje
    następnych testów.
    """
    for name in CLEARED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(planner, "TZ", planner.TZ)  # zapisuje obecną strefę i przywraca ją po teście
    previous = config.ROOT
    config.use_root(tmp_path / "klient")
    yield
    config.use_root(previous)


@pytest.fixture
def make_post():
    """Fabryka postów w kształcie odpowiedzi Zernio `GET /analytics` (dane wymyślone, adresy z example.com)."""

    def make(code, views=1000, *, published="2026-09-01T08:00:00.000Z", caption="Przykładowy podpis rolki",
             product="REELS", media_type="VIDEO", ad=False, shared=True, media=True,
             likes=0, comments=0, shares=0, saves=0):
        return {
            "_id": "post-" + code,
            "analytics": {"views": views, "likes": likes, "comments": comments, "shares": shares, "saves": saves,
                          "follows": 0, "reach": views},
            "content": caption,
            "isAd": ad,
            "isSharedToFeed": shared,
            "mediaItems": ([{"type": "video", "url": "https://cdn.example.com/%s.mp4" % code,
                             "thumbnail": "https://cdn.example.com/%s.jpg" % code}] if media else []),
            "mediaProductType": product,
            "mediaType": media_type,
            "platformPostUrl": "https://www.instagram.com/reel/%s/" % code,
            "publishedAt": published,
        }

    return make


CTA = "Napisz „PRZEWODNIK” w komentarzu, a wyślę ci poradnik. Zaobserwuj @przyklad.konto"
SPEECH = [" Cześć,", " to", " jest", " najmocniejsze", " zdanie", " rolki.", " Napisz", " przewodnik", " w",
          " komentarzu", " i", " obserwuj."]


@pytest.fixture
def make_reel():
    """Fabryka kompletnej, poprawnej rolki z puli (wymyślone teksty, nick i słowo-klucz)."""

    def make(code="Cabc123XYZ_"):
        return {
            "code": code, "name": "Przykładowa rolka", "media_id": "1", "active": True, "hook_y": 0.17,
            "caption": "Zobacz, jak to ogarnąć.\n\n" + CTA,
            "cta": CTA,
            "cta_variants": ["Skomentuj „PRZEWODNIK”, a wyślę ci poradnik. Zaobserwuj @przyklad.konto",
                             "Zostaw „PRZEWODNIK” pod rolką i obserwuj @przyklad.konto"],
            "extras": ["Zapisz sobie na później.", "Wyślij to komuś, kto tego potrzebuje.",
                       "Wróć do tego za tydzień.", "Pokaż to swojemu zespołowi."],
            "strong": "to jest najmocniejsze zdanie rolki",
            "cuts": [{"from": "napisz przewodnik", "to": "w komentarzu"}],
        }

    return make


@pytest.fixture
def make_hooks():
    """Fabryka banku hooków rolki: `n` hooków z kolejnymi emotkami z paczki."""
    from trial_reels import render

    def make(n=3):
        emoji = render.emoji_set()
        return [{"id": "h%02d" % (i + 1), "text": "Krótki hook numer %d" % (i + 1), "emoji": emoji[i]}
                for i in range(n)]

    return make


@pytest.fixture
def put_reel_files():
    """Zapisuje w folderze klienta plik filmu (atrapa) i transkrypcję rolki z kilkoma słowami z czasami."""

    def put(code="Cabc123XYZ_", video=True, transcript=True):
        if video:
            config.SRC.mkdir(parents=True, exist_ok=True)
            (config.SRC / ("%s.mp4" % code)).write_bytes(b"film")
        if transcript:
            t, words = 0.0, []
            for w in SPEECH:
                words.append({"w": w, "s": t, "e": t + 0.4})
                t += 0.5
            config.write_json(config.TRANSCRIPTS / ("%s.json" % code), {"segments": [{"words": words}]})

    return put
