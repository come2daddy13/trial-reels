"""Test dymny renderu: pełny przebieg każdego poziomu na krótkim klipie w folderze z polskimi literami.

Sprawdza cały łańcuch naraz: ffmpeg z paczki, font i emotki z paczki, PyAV (długość i rozmiar), cięcie pauz,
zimne otwarcie i nakładkę z hookiem. Folder `Łódź ąę` ze spacją pilnuje, żeby polskie litery w ścieżce
nie psuły żadnego kroku.
"""
import subprocess

import av
import pytest
from PIL import Image

from trial_reels import config, render

REEL = {"code": "T1", "strong": "to jest najmocniejsze zdanie"}
HOOK = "Trzy zmiany, po których śpisz lepiej"
STRONG_WORDS = [(" to", 4.0, 4.2), (" jest", 4.2, 4.5), (" najmocniejsze", 4.5, 5.1), (" zdanie", 5.1, 5.5)]


@pytest.fixture
def clip_root(tmp_path):
    """Folder klienta z polskimi literami i spacją, a w nim 8-sekundowy klip i jego transkrypcja."""
    config.use_root(tmp_path / "Łódź ąę")
    config.SRC.mkdir(parents=True)
    subprocess.run([config.ffmpeg_exe(), "-nostdin", "-hide_banner", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=30:d=8", "-f", "lavfi", "-i", "sine=f=440:d=8",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(config.SRC / "T1.mp4")],
                   check=True, capture_output=True, encoding="utf-8", errors="replace")
    segment = {"start": 4.0, "end": 5.5, "text": "".join(w for w, _, _ in STRONG_WORDS),
               "words": [{"w": w, "s": s, "e": e} for w, s, e in STRONG_WORDS]}
    config.write_json(config.TRANSCRIPTS / "T1.json", {"segments": [segment]})
    return config.ROOT


def version(vid, level, reel):
    return {"id": vid, "code": reel["code"], "level": level, "hook": HOOK, "emoji": "🔥",
            "params": render.params_for(vid, level, reel)}


def streams(path):
    with av.open(str(path)) as container:
        return ([s.codec_context.name for s in container.streams.video],
                [s.codec_context.name for s in container.streams.audio])


def still_of(video, t, out):
    """Jedna klatka gotowego filmu z czasu `t` (s) zapisana w `out`."""
    subprocess.run([config.ffmpeg_exe(), "-nostdin", "-hide_banner", "-v", "error", "-y", "-ss", str(t), "-i",
                    str(video), "-frames:v", "1", "-q:v", "3", str(out)],
                   check=True, capture_output=True, encoding="utf-8", errors="replace")
    return out


def hook_visible(video, t, tmp_path, **overlay):
    """Czy w klatce z czasu `t` widać biały dymek z hookiem (sprawdzamy kawałek obok tekstu)."""
    left, top, _, _ = render.make_overlay(HOOK, "🔥", tmp_path / "wzorzec.png", **overlay)["box"]
    still = still_of(video, t, tmp_path / ("klatka-%s.jpg" % t))
    with Image.open(still) as im:
        band = im.convert("RGB").crop((left + 24, top + 12, left + 84, top + 24))
        return min(band.resize((1, 1), Image.BOX).getpixel((0, 0))) >= 235


@pytest.mark.parametrize("level", config.LEVELS)
def test_render_each_level_makes_a_vertical_1080x1920_h264_aac_clip(clip_root, tmp_path, level):
    vid = "TR-%03d" % (config.LEVELS.index(level) + 1)
    v = version(vid, level, REEL)
    out = render.render(v, REEL)
    assert out == config.OUT / ("%s.mp4" % vid) and out.is_file()
    assert render.dims(out) == (1080, 1920)
    assert 5.0 <= render.probe(out) <= 10.0
    assert streams(out) == (["h264"], ["aac"])
    assert v["file"] == str(out) and v["duration"] == pytest.approx(render.probe(out), abs=0.01)
    assert v["segments"] and v["changes"].startswith("hook tekstowy 0–")
    assert hook_visible(out, 0.5, tmp_path)           # hook jest na początku
    assert not hook_visible(out, 5.0, tmp_path)       # i znika po ok. 3 sekundach


@pytest.mark.parametrize("strong", ["brak", None, "   "])
def test_render_mocna_without_strong_skips_the_cold_open_but_keeps_the_rest(clip_root, tmp_path, strong):
    """Rolka bez mowy (tu: bez zdania strong) na poziomie Mocna: film jak zwykle, tylko bez zimnego otwarcia."""
    plain_reel = {"code": "T1"} if strong == "brak" else {"code": "T1", "strong": strong}
    plain = version("TR-005", "mocna", plain_reel)
    out = render.render(plain, plain_reel)
    assert plain["params"]["cold"] is None and "zimne otwarcie" not in plain["changes"]
    assert render.dims(out) == (1080, 1920) and 5.0 <= render.probe(out) <= 10.0
    assert streams(out) == (["h264"], ["aac"])
    assert plain["segments"][0][0] == pytest.approx(plain["params"]["trim"], abs=0.01)   # film zaczyna się od startu
    assert hook_visible(out, 0.5, tmp_path)


def test_render_mocna_with_strong_puts_the_sentence_first_and_changes_nothing_else(clip_root):
    plain_reel = {"code": "T1"}
    plain = version("TR-005", "mocna", plain_reel)                 # to samo ID wersji: te same losowane parametry
    render.render(plain, plain_reel)
    loud = version("TR-005", "mocna", REEL)
    render.render(loud, REEL)
    assert loud["params"]["cold"] == REEL["strong"] and "zimne otwarcie" in loud["changes"]
    assert loud["segments"][0][0] == pytest.approx(3.92, abs=0.02)         # zdanie z 4,0 s idzie na początek
    assert plain["segments"][0][0] == pytest.approx(plain["params"]["trim"], abs=0.01)
    assert {k: v for k, v in plain["params"].items() if k != "cold"} == {
        k: v for k, v in loud["params"].items() if k != "cold"}


@pytest.mark.parametrize("level", config.LEVELS)
def test_render_a_reel_without_speech_works_at_every_level(clip_root, tmp_path, level):
    """Prawdziwa rolka bez mowy: pusta transkrypcja, brak strong i cuts. Żaden poziom nie sięga po słowa."""
    config.write_json(config.TRANSCRIPTS / "T1.json", {"segments": []})
    reel = {"code": "T1"}
    vid = "TR-%03d" % (10 + config.LEVELS.index(level))
    v = version(vid, level, reel)
    out = render.render(v, reel)
    assert render.dims(out) == (1080, 1920) and 4.0 <= render.probe(out) <= 10.0
    assert streams(out) == (["h264"], ["aac"])
    assert v["params"]["cold"] is None and "zimne otwarcie" not in v["changes"]
    assert v["segments"][0][0] == pytest.approx(v["params"]["trim"], abs=0.01)
    assert hook_visible(out, 0.5, tmp_path)


def test_render_full_length_hook_over_blurred_source(clip_root, tmp_path):
    """Hook przez całą rolkę (mask) i rozmyty pasek obrazu (blur): obie ścieżki ffmpeg naraz."""
    reel = {**REEL, "mask": {"y": 0.2, "min_w": 0.9, "min_h": 0.12},
            "blur": [{"t": [0.5, 3.0], "box": [0, 0.5, 1, 0.1]}]}
    v = version("TR-004", "subtelna", reel)
    out = render.render(v, reel)
    assert render.dims(out) == (1080, 1920) and 5.0 <= render.probe(out) <= 10.0
    assert streams(out) == (["h264"], ["aac"])
    assert v["changes"].startswith("hook tekstowy przez całą rolkę")
    assert hook_visible(out, 0.5, tmp_path, y=0.2, min_w=0.9, min_h=0.12)
    assert hook_visible(out, 5.0, tmp_path, y=0.2, min_w=0.9, min_h=0.12)
    assert list(config.SRC.glob("T1.blur-*.mp4"))
