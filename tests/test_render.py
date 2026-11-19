"""Testy renderu: font i emotki z paczki, nakładka z hookiem, parametry wersji, cięcia oraz ffmpeg i PyAV.

Klipy testowe są krótkie i małe. Robi je ten sam ffmpeg, którego używa silnik, a niektóre leżą w folderze
z polskimi literami i spacją, bo tak wygląda część komputerów klientów.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageFont

from trial_reels import config, render

# Komplet emotek w paczce (bez U+FE0F, bo nazwa pliku go nie ma).
BUNDLED = "🔥 👀 🤯 ⚡ ✅ 🎯 💡 🚀 📈 💰 ⏰ 📌 👇 👉 🙌 💪 😮 😳 🤔 😅 😎 🧠 ❤ ⭐ 🏆 📱 💬 🛑 ❌ ✨"


def run_ffmpeg(*args):
    subprocess.run([config.ffmpeg_exe(), "-nostdin", "-hide_banner", "-v", "error", "-y", *map(str, args)],
                   check=True, capture_output=True, encoding="utf-8", errors="replace")


def make_clip(path, seconds=2, size="360x640"):
    """Krótki pionowy klip z obrazem testowym i tonem 440 Hz."""
    path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=s=%s:r=30:d=%s" % (size, seconds),
               "-f", "lavfi", "-i", "sine=f=440:d=%s" % seconds,
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path)
    return path


def write_transcript(code, words):
    """Transkrypcja w kształcie, który zapisuje whisper: segmenty ze słowami (w, s, e)."""
    segment = {"start": words[0][1], "end": words[-1][2], "text": "".join(w for w, _, _ in words),
               "words": [{"w": w, "s": s, "e": e} for w, s, e in words]}
    config.write_json(config.TRANSCRIPTS / ("%s.json" % code), {"segments": [segment]})


def alpha_bbox(path):
    with Image.open(path) as im:
        return im.getchannel("A").getbbox()


# --- emotki i font z paczki --------------------------------------------------

def test_emoji_lookup_ignores_variation_selector():
    assert render.emoji_png("❤️") == render.emoji_png("❤") is not None
    assert render.emoji_png("🦄") is None
    assert set(render.ALT_EMOJI) <= set(render.emoji_set())


def test_emoji_key_drops_variation_selector_and_keeps_joiners():
    assert render.emoji_key("❤️") == "2764"
    assert render.emoji_key("🔥") == "1f525"
    assert render.emoji_key("\U0001f468‍\U0001f4bb") == "1f468_200d_1f4bb"


def test_emoji_png_without_emoji_is_none():
    assert render.emoji_png(None) is None and render.emoji_png("") is None and render.emoji_png("️") is None


def test_emoji_set_is_the_bundled_folder():
    emoji = render.emoji_set()
    files = sorted(p.stem for p in (config.ASSETS / "emoji").glob("*.png"))
    assert isinstance(emoji, tuple) and len(emoji) == len(files)
    assert [render.emoji_key(e) for e in emoji] == files
    assert not any("️" in e for e in emoji)
    assert {e.replace("️", "") for e in BUNDLED.split()} <= set(emoji)
    assert all(render.emoji_png(e).is_file() for e in emoji)


def test_emoji_set_skips_files_that_are_not_emoji_names(tmp_path, monkeypatch):
    folder = tmp_path / "zasoby" / "emoji"
    folder.mkdir(parents=True)
    for name in ("1f525.png", "2764.png", "notatka.png", "2764_fe0f.png"):
        Image.new("RGBA", (128, 128), (255, 0, 0, 255)).save(folder / name)
    monkeypatch.setattr(config, "ASSETS", tmp_path / "zasoby")
    assert render.emoji_set() == ("🔥", "❤")  # kolejność nazw plików, bez pliku z fe0f i bez „notatki”


def test_bundled_font_emoji_and_licenses_are_intact():
    font = ImageFont.truetype(render.font_path(), 40)
    assert font.getname() == ("Poppins", "Bold")
    for e in render.emoji_set():
        with Image.open(render.emoji_png(e)) as im:
            assert im.size == (128, 128) and im.mode == "RGBA", e
    for name in ("fonts/OFL.txt", "emoji/LICENSE", "emoji/LICENSE-APACHE-2.0", "ZRODLA.md"):
        assert (config.ASSETS / name).is_file(), name


def test_font_path_reports_missing_font_in_polish(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ASSETS", tmp_path / "pusto")
    with pytest.raises(FileNotFoundError, match="Brak fontu Poppins"):
        render.font_path()


def test_text_layout_does_not_depend_on_the_installed_raqm():
    """Ten sam silnik układu tekstu wszędzie, więc hook zawija się tak samo na Macu i na Windowsie."""
    assert render._font(64).layout_engine == ImageFont.Layout.BASIC


# --- nakładka z hookiem ------------------------------------------------------

def test_overlay_is_full_frame_rgba(tmp_path):
    info = render.make_overlay("Zażółć gęślą jaźń, to działa", "🔥", tmp_path / "o.png")
    with Image.open(tmp_path / "o.png") as im:
        assert im.size == (1080, 1920) and im.mode == "RGBA" and info["box"][2] <= 1080


def test_overlay_wraps_a_long_hook_into_at_most_three_lines(tmp_path):
    hook = "Wieczorny kubek wody zmienia twój sen w tydzień"
    assert len(hook) <= 50
    info = render.make_overlay(hook, None, tmp_path / "o.png")
    assert 2 <= len(info["lines"]) <= 3 and 44 <= info["font"] <= 64
    assert info["box"][2] <= 900  # 820 px tekstu i po 40 px marginesu z każdej strony


def test_overlay_without_emoji_is_just_the_bubble(tmp_path):
    info = render.make_overlay("Śpij lepiej", None, tmp_path / "o.png")
    left, top, bw, bh = info["box"]
    x0, y0, x1, y1 = alpha_bbox(tmp_path / "o.png")
    assert (x0, y0) == (left, top) and abs(x1 - (left + bw)) <= 1 and abs(y1 - (top + bh)) <= 1


def test_overlay_unknown_emoji_leaves_no_sticker(tmp_path):
    render.make_overlay("Śpij lepiej", None, tmp_path / "bez.png")
    render.make_overlay("Śpij lepiej", "🦄", tmp_path / "nieznana.png")
    with Image.open(tmp_path / "bez.png") as a, Image.open(tmp_path / "nieznana.png") as b:
        assert ImageChops.difference(a, b).getbbox() is None


def test_overlay_sticker_sits_on_the_bubble_corner_inside_the_frame(tmp_path):
    plain = render.make_overlay("Śpij lepiej", None, tmp_path / "bez.png")
    with_emoji = render.make_overlay("Śpij lepiej", "🔥", tmp_path / "z.png")
    assert plain["box"] == with_emoji["box"]
    left, top, bw, bh = plain["box"]
    with Image.open(tmp_path / "bez.png") as a, Image.open(tmp_path / "z.png") as b:
        x0, y0, x1, y1 = ImageChops.difference(a, b).getbbox()
    assert y0 < top                       # naklejka wystaje ponad dymek
    assert x0 > left + bw // 2            # i siedzi przy jego prawym rogu
    assert x1 <= render.W - 6             # nie wychodzi poza kadr


def test_every_bundled_emoji_makes_a_rotated_sticker_116_px_wide():
    for e in render.emoji_set():
        sticker = render._emoji_img(e, 116)
        assert sticker is not None and sticker.mode == "RGBA", e
        assert sticker.width >= 116 and sticker.height > 0, e  # po obrocie o -8 stopni płótno jest szersze niż 116


def test_overlay_keeps_the_bubble_in_the_safe_band_and_honours_minimum_size(tmp_path):
    high = render.make_overlay("Hook", None, tmp_path / "g.png", y=0.0)
    low = render.make_overlay("Hook", None, tmp_path / "d.png", y=1.0)
    assert high["box"][1] == int(0.085 * render.H)
    assert low["box"][1] + low["box"][3] <= int(0.78 * render.H)
    big = render.make_overlay("Hook", None, tmp_path / "m.png", min_w=0.9, min_h=0.1)
    assert big["box"][2] >= int(0.9 * render.W) and big["box"][3] >= int(0.1 * render.H)


# --- parametry wersji --------------------------------------------------------

def test_params_are_deterministic_per_version_id():
    assert render.params_for("TR-001", "srednia", {}) == render.params_for("TR-001", "srednia", {})
    p = render.params_for("TR-002", "srednia", {})
    assert 1.05 <= p["zoom"] <= 1.10 and 1.03 <= p["tempo"] <= 1.06


def test_each_level_changes_its_own_things():
    reel = {"strong": "to jest najmocniejsze zdanie"}
    light = render.params_for("TR-010", "subtelna", reel)
    medium = render.params_for("TR-010", "srednia", reel)
    strong = render.params_for("TR-010", "mocna", reel)
    assert (light["zoom"], light["tempo"], light["pauses"], light["cold"]) == (1.0, 1.0, False, None)
    assert medium["pauses"] is True and medium["cold"] is None and medium["zoom"] > 1.0
    assert strong["cold"] == "to jest najmocniejsze zdanie" and strong["pauses"] is False
    assert 0.08 <= light["trim"] <= 0.35 and 2.6 <= light["hook_end"] <= 3.2


def test_mocna_without_a_strong_sentence_works_and_only_skips_the_cold_open():
    """Rolka bez mowy nie ma zdania `strong`: poziom Mocna nie robi wtedy zimnego otwarcia, a reszta zostaje."""
    plain = render.params_for("TR-001", "mocna", {})                  # nie rzuca wyjątku
    assert plain["cold"] is None and plain["pauses"] is False
    assert 1.0 <= plain["zoom"] <= 1.06 and 1.0 <= plain["tempo"] <= 1.03
    with_strong = render.params_for("TR-001", "mocna", {"strong": "to jest najmocniejsze zdanie"})
    assert with_strong["cold"] == "to jest najmocniejsze zdanie"
    assert {k: v for k, v in plain.items() if k != "cold"} == {k: v for k, v in with_strong.items() if k != "cold"}


@pytest.mark.parametrize("strong", [None, "", "   ", "\n"])
def test_an_empty_or_blank_strong_counts_as_no_strong_sentence(strong):
    assert render.params_for("TR-002", "mocna", {"strong": strong})["cold"] is None
    assert render.params_for("TR-002", "mocna", {"code": "X"})["cold"] is None


def test_the_other_levels_never_use_the_strong_sentence():
    reel = {"strong": "to jest najmocniejsze zdanie"}
    assert render.params_for("TR-003", "subtelna", reel)["cold"] is None
    assert render.params_for("TR-003", "srednia", reel)["cold"] is None


def test_describe_leaves_out_the_cold_open_when_there_is_none():
    p = render.params_for("TR-004", "mocna", {})
    text = render.describe({"params": p, "emoji": "🔥"}, {})
    assert "zimne otwarcie" not in text and text.startswith("hook tekstowy 0–")


# --- cięcia i transkrypcja ---------------------------------------------------

def test_keep_segments_removes_cuts():
    segs = render.keep_segments(0.2, 30.0, [(10.0, 12.0), (29.0, 99.0)])
    assert segs == [(0.2, 10.0), (12.0, 29.0)]


def test_keep_segments_drops_fragments_shorter_than_a_fifth_of_a_second():
    assert render.keep_segments(0.0, 10.0, [(0.1, 4.0)]) == [(4.0, 10.0)]


def test_find_phrase_survives_whisper_splitting_e_mail():
    words = [(" podaj", 1.0, 1.2), (" mi", 1.2, 1.4), (" swój", 1.4, 1.6), (" adres", 1.6, 2.0), (" e", 2.0, 2.2),
             ("-mail,", 2.2, 2.4), (" a", 2.6, 2.8)]
    write_transcript("X", words)
    assert render.find_phrase("X", "podaj mi swój adres e-mail") == (1.0, 2.4)
    assert render.find_phrase("X", "adres e-mail, a") == (1.6, 2.8)


def test_find_phrase_ignores_diacritics_case_and_punctuation():
    write_transcript("P", [(" Gęś", 0.5, 0.9), (" ćma,", 0.9, 1.3), (" JAŹŃ!", 1.3, 1.8), (" Zażółć", 2.0, 2.5)])
    assert render.find_phrase("P", "ges cma jazn") == (0.5, 1.8)
    assert render.find_phrase("P", "zażółć") == (2.0, 2.5)


def test_find_phrase_reads_utf8_with_bom(tmp_path):
    tr = {"segments": [{"words": [{"w": " zażółć", "s": 1.0, "e": 1.5}]}]}
    path = config.TRANSCRIPTS / "B.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(tr, ensure_ascii=False).encode("utf-8"))
    assert render.find_phrase("B", "zażółć") == (1.0, 1.5)


def test_find_phrase_errors_name_the_reel():
    write_transcript("X", [(" to", 1.0, 1.2), (" jest", 1.2, 1.5)])
    with pytest.raises(ValueError, match="nie ma frazy w X"):
        render.find_phrase("X", "zupełnie inne zdanie")
    with pytest.raises(FileNotFoundError, match="Brak transkrypcji rolki Y"):
        render.find_phrase("Y", "to jest")


def test_reel_cuts_come_from_transcript_phrases():
    write_transcript("C", [(" zapisz", 5.0, 5.4), (" się", 5.4, 5.6), (" teraz", 5.6, 6.0), (" koniec", 8.0, 8.5)])
    reel = {"code": "C", "cuts": [{"from": "zapisz się", "to": "teraz"}, {"from": "koniec", "to": None}]}
    assert render.reel_cuts(reel) == [pytest.approx((4.95, 6.1)), pytest.approx((7.95, 10 ** 6 + 0.1))]
    assert render.reel_cuts({"code": "C"}) == []


# --- filtry ffmpeg -----------------------------------------------------------

def test_blur_covers_email_band_only_in_its_time_window():
    graph, last = render.blur_filter([{"t": [10.6, 13.6], "box": [0, 0, 1, 0.36]}], 720, 1280)
    assert "crop=720:460:0:0" in graph and "between(t,10.6,13.6)" in graph and last == "b0"


@pytest.mark.parametrize("entry", [
    {"t": [0, "1)':movie=dane/src/x.mp4"], "box": [0, 0, 1, 0.3]},          # tekst dopisany do grafu filtrów
    {"t": [0], "box": [0, 0, 1, 0.3]}, {"t": [0, 1, 2], "box": [0, 0, 1, 0.3]}, {"t": ["0", "1"], "box": [0, 0, 1, 0.3]},
    {"t": [0, float("nan")], "box": [0, 0, 1, 0.3]}, {"t": [True, 1], "box": [0, 0, 1, 0.3]},
    {"t": [2, 1], "box": [0, 0, 1, 0.3]}, {"t": [-1, 1], "box": [0, 0, 1, 0.3]},
    {"t": [0, 1], "box": [0, 0, 1]}, {"t": [0, 1], "box": [0, 0, "1", 0.3]}, {"t": [0, 1], "box": [0, 0, 1.5, 0.3]},
    {"t": [0, 1], "box": [0.5, 0, 0.6, 0.3]}, {"t": [0, 1], "box": [0, 0, 0, 0.3]}, {"t": [0, 1]}, "nie-obiekt",
])
def test_blur_filter_takes_only_numbers_that_fit_the_frame(entry):
    """D6: `t` trafia do grafu filtrów ffmpeg, więc tekst w nim mógłby dopisać filtr (np. obraz z dysku na rolce)."""
    with pytest.raises(ValueError) as caught:
        render.blur_filter([entry], 720, 1280)
    assert "blur" in str(caught.value) and "\n" not in str(caught.value)


def test_blur_filter_writes_times_as_plain_numbers():
    graph, _ = render.blur_filter([{"t": [1, 2.5], "box": [0, 0, 1, 0.5]}], 720, 1280)
    assert "between(t,1,2.5)" in graph


def test_paths_from_reel_codes_and_version_ids_never_leave_their_folders():
    """D6: kod rolki i numer wersji z plików w dane/ trafiają do nazw plików, więc muszą mieć bezpieczny kształt."""
    for bad in ("../../poza", "a/b", "C:x"):
        with pytest.raises(config.UserError):
            render.source({"code": bad})
        with pytest.raises(config.UserError):
            render.find_phrase(bad, "fraza")
    with pytest.raises(config.UserError, match="TR-001"):
        render.render({"id": "../../poza", "params": render.params_for("TR-001", "subtelna", {}), "hook": "H"},
                      {"code": "Cabc123XYZ_"})
    assert not list(config.ROOT.parent.glob("poza*"))


def test_blur_radius_fits_thin_bands():
    """Promień rozmycia jest mniejszy od ćwiartki mniejszego boku paska, bo inaczej ffmpeg odrzuca filtr."""
    wide, _ = render.blur_filter([{"t": [0, 1], "box": [0, 0, 1, 0.36]}], 720, 1280)
    thin, _ = render.blur_filter([{"t": [0, 1], "box": [0, 0.5, 1, 0.1]}], 720, 1280)
    tiny, _ = render.blur_filter([{"t": [0, 1], "box": [0, 0.5, 1, 0.02]}], 720, 1280)
    assert "luma_radius=40" in wide and "luma_radius=31" in thin and "luma_radius=5" in tiny


def test_filtergraph_overlays_the_hook_window_or_the_whole_reel():
    p = render.params_for("TR-005", "srednia", {})
    window = render.filtergraph([(0.2, 3.0), (4.0, 6.0)], p, False)
    whole = render.filtergraph([(0.2, 3.0)], p, True)
    assert "concat=n=2:v=1:a=1" in window and "overlay=0:0:eof_action=pass" in window and "alpha=1" in window
    assert "concat=n=1:v=1:a=1" in whole and "overlay=0:0:shortest=1" in whole and "alpha=1" not in whole
    assert "atempo=%s" % p["tempo"] in window


def test_describe_lists_the_changes_in_polish():
    p = {"hook_end": 2.8, "trim": 0.2, "sat": 1.03, "contrast": 1.02, "zoom": 1.07, "tempo": 1.04,
         "cold": "to jest zdanie", "thumb_ms": 900}
    text = render.describe({"params": p, "emoji": "🔥", "pauses_cut": 2}, {"cuts": [{}]})
    for part in ("hook tekstowy 0–2,8 s", "emotka 🔥", "zimne otwarcie zdaniem „to jest zdanie”", "start od 0,2 s",
                 "nasycenie ×1,03, kontrast ×1,02", "przybliżenie 7%", "tempo ×1,04", "wycięte pauzy: 2",
                 "wycięte CTA ze słowem-kluczem", "okładka: kadr z 0,9 s"):
        assert part in text
    masked = render.describe({"params": {**p, "zoom": 1.0, "tempo": 1.0, "cold": None}}, {"mask": {"y": 0.2}})
    assert "hook tekstowy przez całą rolkę" in masked and "przybliżenie" not in masked and "tempo" not in masked


# --- ffmpeg z paczki i PyAV ---------------------------------------------------

def test_probe_and_dims_read_the_video_through_pyav(tmp_path):
    clip = make_clip(tmp_path / "Łódź ąę" / "klip ze spacją.mp4", seconds=2, size="320x568")
    assert render.dims(clip) == (320, 568)
    duration = render.probe(clip)
    assert isinstance(duration, float) and 1.9 <= duration <= 2.2


def test_dims_without_a_video_stream_says_so(tmp_path):
    wav = tmp_path / "dźwięk.wav"
    run_ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=1", wav)
    with pytest.raises(ValueError, match="obrazu"):
        render.dims(wav)
    assert render.probe(wav) == pytest.approx(1.0, abs=0.1)


def test_silences_finds_the_gap_between_two_tones(tmp_path):
    wav = tmp_path / "pauza.wav"
    run_ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=1", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1",
               "-f", "lavfi", "-i", "sine=f=440:d=1",
               "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]", "-map", "[a]", wav)
    (start, end), = render.silences(wav)
    assert start == pytest.approx(1.0, abs=0.05) and end == pytest.approx(2.0, abs=0.05)


def test_source_renders_the_blur_copy_only_once():
    make_clip(config.SRC / "B1.mp4", seconds=2, size="320x568")
    assert render.source({"code": "B1"}) == config.SRC / "B1.mp4"
    reel = {"code": "B1", "blur": [{"t": [0.2, 1.0], "box": [0, 0, 1, 0.3]}]}
    blurred = render.source(reel)
    assert blurred.parent == config.SRC and blurred.name.startswith("B1.blur-") and blurred.is_file()
    assert render.dims(blurred) == (320, 568)
    stamp = blurred.stat().st_mtime_ns
    assert render.source(reel) == blurred and blurred.stat().st_mtime_ns == stamp
    assert not list(config.SRC.glob("*.tmp.mp4"))


def test_source_moves_the_blur_copy_into_place_with_the_same_retries_as_other_writes(monkeypatch):
    make_clip(config.SRC / "B2.mp4", seconds=2, size="320x568")
    real_replace, attempts, waits = config.os.replace, [], []

    def replace(src, dst):
        attempts.append(1)
        if len(attempts) <= 2:
            raise PermissionError("plik jest otwarty w innym programie")
        return real_replace(src, dst)

    monkeypatch.setattr(config.os, "replace", replace)
    monkeypatch.setattr(config.time, "sleep", waits.append)
    blurred = render.source({"code": "B2", "blur": [{"t": [0.2, 1.0], "box": [0, 0, 1, 0.3]}]})
    assert blurred.is_file() and blurred.name.startswith("B2.blur-")
    assert len(attempts) == 3 and waits == [0.1, 0.1] and not list(config.SRC.glob("*.tmp.mp4"))


def test_hook_frame_writes_the_still_in_a_polish_folder_it_creates(tmp_path):
    make_clip(config.SRC / "F1.mp4", seconds=2, size="360x640")
    folder = tmp_path / "Łódź ąę" / "nowy folder"  # brakujące foldery tworzy sam silnik
    hook = "Trzy zmiany, po których śpisz lepiej"
    out = render.hook_frame({"code": "F1"}, hook, "🔥", 1.0, folder / "hook.jpg")
    left, top, bw, bh = render.make_overlay(hook, "🔥", tmp_path / "ov.png")["box"]
    with Image.open(out) as im:
        assert im.size == (1080, 1920)
        band = im.convert("RGB").crop((left + 24, top + 12, left + 84, top + 24))  # biały dymek nad tekstem
        assert min(band.resize((1, 1), Image.BOX).getpixel((0, 0))) >= 235


def test_hook_frame_past_the_end_of_the_clip_reports_the_length_in_one_polish_line(tmp_path):
    clip = make_clip(config.SRC / "F2.mp4", seconds=1, size="320x568")
    length = render.fmt(render.probe(clip))
    with pytest.raises(RuntimeError) as caught:
        render.hook_frame({"code": "F2"}, "Hook", None, 30.0, tmp_path / "nic.jpg")
    message = str(caught.value)
    assert "\n" not in message and "klatki z 30 s" in message
    assert "Film ma tylko %s s" % length in message and "--t" in message
    assert not (tmp_path / "nic.jpg").exists()


def test_hook_frame_keeps_the_ffmpeg_noise_off_the_terminal(tmp_path, capfd):
    """ffmpeg pisze o błędach po angielsku, kilkanaście linii: klient ma zobaczyć tylko jedną linię po polsku."""
    make_clip(config.SRC / "F4.mp4", seconds=1, size="320x568")
    with pytest.raises(RuntimeError):
        render.hook_frame({"code": "F4"}, "Hook", None, 30.0, tmp_path / "nic.jpg")
    captured = capfd.readouterr()
    assert captured.out == "" and captured.err == ""


def test_hook_frame_of_a_damaged_file_says_so_in_one_line_without_ffmpeg_noise(tmp_path, capfd):
    broken = config.SRC / "F3.mp4"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"to nie jest film" * 200)
    with pytest.raises(RuntimeError) as caught:
        render.hook_frame({"code": "F3"}, "Hook", None, 1.0, tmp_path / "nic.jpg")
    message = str(caught.value)
    assert "\n" not in message and "klatki z 1 s" in message and "uszkodzony" in message
    assert "Film ma tylko" not in message                      # tu nie wiemy, jak długi jest film, więc go nie zgadujemy
    captured = capfd.readouterr()
    assert captured.out == "" and captured.err == ""


def test_a_time_inside_the_film_but_at_its_very_end_does_not_say_the_film_is_too_short(monkeypatch, tmp_path):
    """Tuż przy końcu filmu klatki często już nie ma. Zdanie „film ma tylko 12,75 s, więc nie ma klatki z 12,7 s” brzmi
    wtedy sprzecznie, więc program mówi, że chodzi o sam koniec, i podaje czas, który jeszcze jest bezpieczny.
    (Liczby są ułamkami o dokładnym zapisie binarnym, żeby granica marginesu nie zależała od zaokrągleń.)"""
    monkeypatch.setattr(render, "probe", lambda path: 12.75)
    film = tmp_path / "film.mp4"
    near_end = render._grab_problem(film, 12.7)
    assert near_end == ("Film ma 12,75 s, a tuż przed jego końcem nie ma już klatki do wyciągnięcia, więc nie ma jej "
                        "w 12,7 s. Podaj w opcji --t czas mniejszy niż 12,5 s.")
    assert "\n" not in near_end and "tylko" not in near_end
    assert render._grab_problem(film, 12.5).startswith("Film ma 12,75 s, a tuż przed")      # granica marginesu
    assert render._grab_problem(film, 12.25).startswith("Nie udało się wyciągnąć klatki")   # dalej od końca to inny kłopot
    assert render._grab_problem(film, 12.75) == ("Film ma tylko 12,75 s, więc nie ma w nim klatki z 12,75 s. "
                                                 "Podaj mniejszy czas w opcji --t.")
    assert render._grab_problem(film, 30) == ("Film ma tylko 12,75 s, więc nie ma w nim klatki z 30 s. "
                                              "Podaj mniejszy czas w opcji --t.")


def test_a_very_short_film_never_suggests_a_negative_time(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "probe", lambda path: 0.2)
    message = render._grab_problem(tmp_path / "krotki.mp4", 0.1)
    assert "mniejszy niż 0 s" in message and "-" not in message.split("niż")[1]


def test_hook_frame_at_the_very_end_either_works_or_explains_itself(tmp_path):
    clip = make_clip(config.SRC / "F6.mp4", seconds=2, size="320x568")
    length = render.probe(clip)
    try:
        still = render.hook_frame({"code": "F6"}, "Hook", None, length - 0.01, tmp_path / "koniec.jpg")
    except RuntimeError as e:
        message = str(e)
        assert "Film ma %s s" % render.fmt(length) in message and "tylko" not in message and "mniejszy niż" in message
    else:                                                    # niektóre wersje ffmpeg biorą wtedy ostatnią klatkę
        assert still.is_file()


def test_a_failed_frame_keeps_the_previous_one_and_leaves_no_temporary_file(tmp_path):
    """Nieudane kadr nie kasuje klatki, którą klient ma już otwartą z poprzedniego wywołania."""
    make_clip(config.SRC / "F7.mp4", seconds=1, size="320x568")
    reel = {"code": "F7"}
    folder = tmp_path / "klatki"
    still = folder / "kadr.jpg"
    render.hook_frame(reel, "Hook", None, 0.5, still)
    before = still.read_bytes()
    assert [p.name for p in folder.iterdir()] == ["kadr.jpg"]                           # sukces nie zostawia plików tymczasowych
    with pytest.raises(RuntimeError):
        render.hook_frame(reel, "Hook", None, 30.0, still)
    assert still.read_bytes() == before and [p.name for p in folder.iterdir()] == ["kadr.jpg"]
    render.hook_frame(reel, "Inny hook", None, 0.2, still)                               # udane kadr nadal nadpisuje plik
    assert still.read_bytes() != before and [p.name for p in folder.iterdir()] == ["kadr.jpg"]


def test_hook_frame_just_before_the_end_still_works_and_after_it_does_not(tmp_path):
    clip = make_clip(config.SRC / "F5.mp4", seconds=2, size="320x568")
    length = render.probe(clip)
    assert render.hook_frame({"code": "F5"}, "Hook", None, 1.5, tmp_path / "srodek.jpg").is_file()
    with pytest.raises(RuntimeError, match="Film ma tylko"):
        render.hook_frame({"code": "F5"}, "Hook", None, length + 5, tmp_path / "po-koncu.jpg")


def test_the_only_way_to_take_a_still_is_the_hook_frame_the_kadr_command_uses():
    """`render.frame` (klatka bez dymka) nie miała wywołań w programie, tylko w testach, więc jej nie ma."""
    assert not hasattr(render, "frame") and callable(render.hook_frame)


def test_the_font_and_the_emoji_load_from_a_program_folder_with_polish_letters_and_a_space(tmp_path):
    """Program leży w folderze klienta, np. C:\\Users\\Łukasz Ząb\\trial-reels, więc font i emotki z assets/ ładują się
    z takiej ścieżki (dotąd testy przenosiły tam tylko dane, a kod i zasoby zostawały pod ścieżką repo)."""
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / "Łukasz Ząb" / "Łódź ąę" / "trial-reels"
    shutil.copytree(repo / "trial_reels", home / "trial_reels", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(repo / "assets", home / "assets")
    (home / "VERSION").write_text("0.0.0\n", encoding="utf-8")
    out = home / "dane" / "dymek.png"
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "import trial_reels\n"
        "from trial_reels import config, render\n"
        "home = Path(sys.argv[1])\n"
        "assert Path(trial_reels.__file__).resolve().is_relative_to(home.resolve()), trial_reels.__file__\n"
        "assert Path(render.font_path()).resolve().is_relative_to(home.resolve()), render.font_path()\n"
        "assert render.emoji_png('🔥') is not None and render.emoji_png('🔥').resolve().is_relative_to(home.resolve())\n"
        "box = render.make_overlay('Trzy zmiany, po których śpisz lepiej', '🔥', Path(sys.argv[2]))['box']\n"
        "print(box[2], box[3])\n")
    done = subprocess.run([sys.executable, "-c", script, str(home), str(out)], cwd=home, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert done.returncode == 0, done.stderr
    with Image.open(out) as im:
        assert im.size == (render.W, render.H) and im.getchannel("A").getbbox() is not None      # dymek i emotka narysowane

