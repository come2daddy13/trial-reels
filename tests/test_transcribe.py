"""Testy transkrypcji: dekodowanie dźwięku przez ffmpeg z paczki i zapis słów z czasami.

Model Whispera jest atrapą (prawdziwy waży ponad 1 GB), a dźwięk w testach dekodowania powstaje na miejscu.
"""
import json
import math
import os
import subprocess
import wave
from types import SimpleNamespace

import faster_whisper
import numpy as np
import pytest

from trial_reels import config, transcribe


def write_wav(path, samples, rate=16000, channels=1):
    """Zapisuje próbki int16 jako plik WAV (mono albo stereo z przeplotem)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return path


def make_video(path, audio=True, seconds=1):
    """Krótki film H.264 z dźwiękiem AAC (sinus 440 Hz) albo bez dźwięku."""
    cmd = [config.ffmpeg_exe(), "-nostdin", "-hide_banner", "-v", "error", "-y",
           "-f", "lavfi", "-i", "testsrc2=s=160x120:r=10:d=%s" % seconds]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=f=440:d=%s" % seconds]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else []) + [str(path)]
    subprocess.run(cmd, check=True, capture_output=True, encoding="utf-8", errors="replace")
    return path


# --- dekodowanie dźwięku -----------------------------------------------------

def test_decode_audio_gives_float32_mono_scaled_by_32768(tmp_path):
    samples = np.linspace(-32768, 32767, 1600).astype(np.int16)
    out = transcribe.decode_audio(write_wav(tmp_path / "ton.wav", samples))
    assert out.dtype == np.float32 and out.ndim == 1
    assert np.array_equal(out, samples.astype(np.float32) / 32768.0)
    assert out.min() == -1.0 and out.max() < 1.0


def test_decode_audio_downmixes_and_resamples_to_16k_mono(tmp_path):
    rate = 44100
    t = np.arange(rate) / rate  # sekunda dźwięku
    tone = (0.5 * 32767 * np.sin(2 * math.pi * 440 * t)).astype(np.int16)
    stereo = np.column_stack([tone, tone]).ravel()
    out = transcribe.decode_audio(write_wav(tmp_path / "stereo.wav", stereo, rate=rate, channels=2))
    assert out.dtype == np.float32 and out.ndim == 1
    assert abs(len(out) - 16000) <= 32
    assert 0.4 < float(np.abs(out).max()) < 0.6


def test_decode_audio_reads_sound_from_a_video_file(tmp_path):
    out = transcribe.decode_audio(make_video(tmp_path / "film.mp4"))
    assert out.dtype == np.float32 and abs(len(out) - 16000) <= 2400  # AAC dokłada kilkadziesiąt ms ciszy
    assert float(np.abs(out).max()) > 0.05


def test_decode_audio_handles_polish_letters_and_spaces_in_path(tmp_path):
    samples = (1000 * np.sin(np.arange(1600))).astype(np.int16)
    wav = write_wav(tmp_path / "Łódź ąę" / "nagranie próbne.wav", samples)
    out = transcribe.decode_audio(str(wav))  # tekst jak i Path
    assert len(out) == 1600
    assert len(transcribe.decode_audio(wav)) == 1600


def test_decode_audio_does_not_use_the_faster_whisper_decoder(tmp_path, monkeypatch):
    """`faster_whisper.decode_audio` psuje się z PyAV 19, więc nasz dekoder nie może po nią sięgać."""
    def refuse(*args, **kwargs):
        raise AssertionError("nie wolno wołać faster_whisper.decode_audio")

    monkeypatch.setattr(faster_whisper, "decode_audio", refuse)
    monkeypatch.setattr(faster_whisper.audio, "decode_audio", refuse)
    wav = write_wav(tmp_path / "ton.wav", np.zeros(1600, dtype=np.int16))
    assert len(transcribe.decode_audio(wav)) == 1600


def test_decode_audio_missing_file_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match="nie-ma.mp4"):
        transcribe.decode_audio(tmp_path / "nie-ma.mp4")


def test_decode_audio_video_without_sound_says_so(tmp_path):
    silent = make_video(tmp_path / "bez-dzwieku.mp4", audio=False)
    with pytest.raises(RuntimeError, match="nie ma dźwięku") as e:
        transcribe.decode_audio(silent)
    assert "bez-dzwieku.mp4" in str(e.value)


def test_decode_audio_garbage_file_shows_ffmpeg_message(tmp_path):
    garbage = tmp_path / "to-nie-film.mp4"
    garbage.write_text("zwykły tekst", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ffmpeg nie odczytał dźwięku") as e:
        transcribe.decode_audio(garbage)
    assert "to-nie-film.mp4" in str(e.value)


# --- słowa z czasami ---------------------------------------------------------

def test_to_words_json_shape():
    seg = SimpleNamespace(start=0.12345, end=2.5, text=" Cześć, to test.", words=[
        SimpleNamespace(word=" Cześć,", start=0.12345, end=0.6789, probability=0.9),
        SimpleNamespace(word=" to", start=0.7, end=0.80049, probability=0.8),
        SimpleNamespace(word=" test.", start=0.9, end=2.5, probability=0.7),
    ])
    out = transcribe.to_words_json(iter([seg]))  # generator, jak od Whispera, też działa
    assert out == {"segments": [{
        "start": 0.123, "end": 2.5, "text": " Cześć, to test.",
        "words": [{"w": " Cześć,", "s": 0.123, "e": 0.679},
                  {"w": " to", "s": 0.7, "e": 0.8},
                  {"w": " test.", "s": 0.9, "e": 2.5}],
    }]}
    assert json.loads(json.dumps(out, ensure_ascii=False)) == out


def test_to_words_json_keeps_segment_order_and_handles_numpy_numbers():
    first = SimpleNamespace(start=np.float32(0.0), end=np.float32(1.23456), text=" a",
                            words=[SimpleNamespace(word=" a", start=np.float32(0.0), end=np.float32(1.23456))])
    second = SimpleNamespace(start=2.0, end=3.0, text=" b", words=[])
    out = transcribe.to_words_json([first, second])
    assert [s["text"] for s in out["segments"]] == [" a", " b"]
    assert out["segments"][0]["end"] == 1.235 and out["segments"][0]["words"][0]["e"] == 1.235
    json.dumps(out)  # liczby numpy zostały zamienione na zwykłe


def test_to_words_json_tolerates_segments_without_words_and_empty_input():
    assert transcribe.to_words_json([]) == {"segments": []}
    no_words = SimpleNamespace(start=0, end=1, text=" x", words=None)
    missing_attr = SimpleNamespace(start=1, end=2, text=" y")
    out = transcribe.to_words_json([no_words, missing_attr])
    assert [s["words"] for s in out["segments"]] == [[], []]
    assert out["segments"][0]["start"] == 0 and out["segments"][1]["end"] == 2


# --- transkrypcja z atrapą modelu --------------------------------------------

class FakeModel:
    """Atrapa WhisperModel: zapisuje, jak ją utworzono i wywołano."""
    instances = []

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs, self.calls = args, kwargs, []
        FakeModel.instances.append(self)

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        words = [SimpleNamespace(word=" Zażółć", start=0.0, end=0.5, probability=1.0),
                 SimpleNamespace(word=" gęślą", start=0.5, end=1.0, probability=1.0)]
        seg = SimpleNamespace(start=0.0, end=1.0, text=" Zażółć gęślą", words=words)
        return iter([seg]), SimpleNamespace(language=kwargs.get("language"))


@pytest.fixture
def fake_model(monkeypatch):
    FakeModel.instances = []
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    monkeypatch.setattr(transcribe, "_MODEL_CACHE", {})  # model z poprzedniego testu nie może przeżyć
    return FakeModel


def test_transcribe_writes_words_json_in_utf8_and_returns_the_path(tmp_path, monkeypatch, fake_model):
    audio = np.ones(16000, dtype=np.float32)
    decoded = []
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: decoded.append(src) or audio)
    out = tmp_path / "Łódź ąę" / "transkrypcje" / "T1.json"

    result = transcribe.transcribe(tmp_path / "film.mp4", out)

    assert result == out and decoded == [tmp_path / "film.mp4"]
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"segments": [{"start": 0.0, "end": 1.0, "text": " Zażółć gęślą", "words": [
        {"w": " Zażółć", "s": 0.0, "e": 0.5}, {"w": " gęślą", "s": 0.5, "e": 1.0}]}]}
    assert "Zażółć" in out.read_text(encoding="utf-8")  # polskie litery bez zamiany na \uXXXX
    model = fake_model.instances[0]
    assert model.args == ("large-v3-turbo",) and model.kwargs == {"device": "cpu", "compute_type": "int8"}
    got_audio, kwargs = model.calls[0]
    assert got_audio is audio and kwargs == {"language": "pl", "word_timestamps": True, "vad_filter": True}


def test_transcribe_passes_model_and_language_through(tmp_path, monkeypatch, fake_model):
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(8, dtype=np.float32))
    transcribe.transcribe("film.mp4", str(tmp_path / "T2.json"), model="small", language="en")
    model = fake_model.instances[0]
    assert model.args == ("small",) and model.calls[0][1]["language"] == "en"
    assert (tmp_path / "T2.json").is_file()


def test_transcribe_of_silent_audio_writes_empty_transcript_without_loading_the_model(tmp_path, monkeypatch,
                                                                                       fake_model):
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.zeros(0, dtype=np.float32))
    out = tmp_path / "T3.json"
    assert transcribe.transcribe("film.mp4", out) == out
    assert json.loads(out.read_text(encoding="utf-8")) == {"segments": []}
    assert fake_model.instances == []


def test_transcribe_filters_out_non_speech_so_a_reel_without_speech_has_zero_words(tmp_path, monkeypatch, fake_model):
    """Muzyka i napisy na ekranie bez mowy: filtr aktywności głosu odcina je, więc Whisper nie wymyśla zdań."""
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(16000, dtype=np.float32))
    seen = []

    class Silent(FakeModel):
        def transcribe(self, audio, **kwargs):
            seen.append(kwargs)
            return iter([]), SimpleNamespace(language="pl")   # po filtrze nie zostało nic

    monkeypatch.setattr(faster_whisper, "WhisperModel", Silent)
    out = tmp_path / "bez-mowy.json"
    assert transcribe.transcribe("film.mp4", out) == out
    assert seen[0]["vad_filter"] is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"segments": []} and sum(len(s["words"]) for s in data["segments"]) == 0


def test_the_installed_faster_whisper_knows_the_vad_filter_option():
    """Gdyby nowsza wersja pakietu usunęła tę opcję, wyszłoby to tu, a nie dopiero u klienta przy pierwszej rolce."""
    import inspect

    assert "vad_filter" in inspect.signature(faster_whisper.WhisperModel.transcribe).parameters


def test_transcribe_fails_before_loading_the_model_when_there_is_no_sound(tmp_path, fake_model):
    with pytest.raises(FileNotFoundError):
        transcribe.transcribe(tmp_path / "nie-ma.mp4", tmp_path / "T4.json")
    assert fake_model.instances == [] and not (tmp_path / "T4.json").exists()


# --- jeden model na proces ---------------------------------------------------

def test_transcribe_loads_the_model_once_per_process(tmp_path, monkeypatch, fake_model):
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(8, dtype=np.float32))
    for n in range(3):
        transcribe.transcribe("film%d.mp4" % n, tmp_path / ("T%d.json" % n))
    assert len(fake_model.instances) == 1
    assert len(fake_model.instances[0].calls) == 3
    assert all((tmp_path / ("T%d.json" % n)).is_file() for n in range(3))


def test_transcribe_keeps_one_model_per_name(tmp_path, monkeypatch, fake_model):
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(8, dtype=np.float32))
    transcribe.transcribe("a.mp4", tmp_path / "a.json")
    transcribe.transcribe("b.mp4", tmp_path / "b.json", model="small")
    transcribe.transcribe("c.mp4", tmp_path / "c.json")
    transcribe.transcribe("d.mp4", tmp_path / "d.json", model="small")
    assert [m.args for m in fake_model.instances] == [("large-v3-turbo",), ("small",)]


def test_a_model_that_failed_to_load_is_not_remembered(tmp_path, monkeypatch, fake_model):
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(8, dtype=np.float32))
    attempts = []

    class Flaky(FakeModel):
        def __init__(self, *args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise OSError("brak połączenia")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(faster_whisper, "WhisperModel", Flaky)
    with pytest.raises(OSError):
        transcribe.transcribe("a.mp4", tmp_path / "a.json")
    transcribe.transcribe("a.mp4", tmp_path / "a.json")          # druga próba ładuje model od nowa
    assert len(attempts) == 2 and (tmp_path / "a.json").is_file()


# --- czy model leży już na dysku ---------------------------------------------

def test_default_model_is_the_turbo_one():
    assert transcribe.DEFAULT_MODEL == "large-v3-turbo"


def test_model_cached_looks_for_the_big_model_file(tmp_path, monkeypatch):
    asked = []

    def where(name, local_files_only=False, **kwargs):
        asked.append((name, local_files_only))
        return str(tmp_path)

    monkeypatch.setattr(faster_whisper, "download_model", where)
    assert transcribe.model_cached() is False                     # folder jest, ale bez pliku model.bin
    (tmp_path / "model.bin").write_bytes(b"x")
    assert transcribe.model_cached() is True
    assert transcribe.model_cached("small") is True
    assert asked == [("large-v3-turbo", True)] * 2 + [("small", True)]  # pytamy tylko dysk, bez internetu


def test_model_cached_is_false_when_the_model_is_not_on_disk(monkeypatch):
    def missing(name, local_files_only=False, **kwargs):
        raise FileNotFoundError("Cannot find an appropriate cached snapshot folder")

    monkeypatch.setattr(faster_whisper, "download_model", missing)
    assert transcribe.model_cached() is False

    def bad_name(name, local_files_only=False, **kwargs):
        raise ValueError("Invalid model size")

    monkeypatch.setattr(faster_whisper, "download_model", bad_name)
    assert transcribe.model_cached("nie-ma-takiego") is False


# --- Windows: model w ścieżce bez polskich liter ---------------------------------

POLISH_CACHE = "C:\\Users\\Łukasz Ząb\\.cache\\huggingface\\hub"
ASCII_CACHE = "C:\\Users\\Anna Nowak\\.cache\\huggingface\\hub"


def as_windows(monkeypatch, cache=POLISH_CACHE, **environ):
    """Udaje Windows tylko dla modułu transkrypcji (zmiana os.name dla całego procesu zepsułaby ścieżki w innych modułach):
    system, zmienne środowiskowe i domyślny folder pamięci podręcznej Hugging Face z polskimi literami."""
    monkeypatch.setattr(transcribe, "os", SimpleNamespace(name="nt", environ=environ))
    monkeypatch.setattr(transcribe, "hub_cache", lambda: cache)


def test_model_root_is_the_ascii_public_folder_on_windows_when_the_cache_path_has_polish_letters(monkeypatch):
    """CTranslate2 (natywna biblioteka) potrafi nie otworzyć pliku modelu ze ścieżki w rodzaju C:\\Users\\Łukasz Ząb\\…"""
    as_windows(monkeypatch, PUBLIC="D:\\Wspolne")
    assert transcribe.model_root() == "D:\\Wspolne\\trial-reels-model"


def test_model_root_reads_the_real_os_name_and_the_real_environment(monkeypatch):
    """Ten sam wybór folderu, ale z prawdziwym os.name i zmienną PUBLIC z procesu (os.name podmienione tylko na czas
    wywołania: na Macu pathlib nie zniesie `nt` dłużej)."""
    monkeypatch.setattr(transcribe, "hub_cache", lambda: POLISH_CACHE)
    monkeypatch.setenv("PUBLIC", "D:\\Wspolne")
    with monkeypatch.context() as patched:
        patched.setattr(os, "name", "nt")
        on_windows = transcribe.model_root()
    assert on_windows == "D:\\Wspolne\\trial-reels-model"
    if os.name != "nt":                                                               # poza blokiem system jest prawdziwy
        assert transcribe.model_root() is None


@pytest.mark.parametrize("environ", [{}, {"PUBLIC": ""}])
def test_model_root_falls_back_to_the_default_public_folder_without_the_public_variable(monkeypatch, environ):
    as_windows(monkeypatch, **environ)
    assert transcribe.model_root() == "C:\\Users\\Public\\trial-reels-model"


def test_model_root_stays_empty_when_nothing_needs_changing(monkeypatch):
    as_windows(monkeypatch, cache=ASCII_CACHE, PUBLIC="C:\\Users\\Public")          # Windows, ale ścieżka jest w ASCII
    assert transcribe.model_root() is None
    monkeypatch.setattr(transcribe, "os", SimpleNamespace(name="posix", environ={"PUBLIC": "C:\\Users\\Public"}))
    monkeypatch.setattr(transcribe, "hub_cache", lambda: "/Users/Łukasz Ząb/.cache/huggingface/hub")
    assert transcribe.model_root() is None                                                # Mac i tak czyta takie ścieżki


def test_the_hub_cache_is_the_folder_huggingface_hub_uses():
    from huggingface_hub import constants

    assert transcribe.hub_cache() == str(constants.HF_HUB_CACHE)


def test_transcribe_downloads_and_reads_the_model_from_the_ascii_folder_on_windows(tmp_path, monkeypatch, fake_model):
    as_windows(monkeypatch, PUBLIC="C:\\Users\\Public")
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(8, dtype=np.float32))
    transcribe.transcribe("film.mp4", tmp_path / "T1.json")
    model = fake_model.instances[0]
    assert model.args == ("large-v3-turbo",)
    assert model.kwargs == {"device": "cpu", "compute_type": "int8", "download_root": "C:\\Users\\Public\\trial-reels-model"}
    assert (tmp_path / "T1.json").is_file()


def test_transcribe_keeps_the_default_model_folder_everywhere_else(tmp_path, monkeypatch, fake_model):
    monkeypatch.setattr(transcribe, "os", SimpleNamespace(name="posix", environ={}))
    monkeypatch.setattr(transcribe, "hub_cache", lambda: "/Users/Łukasz Ząb/.cache/huggingface/hub")
    monkeypatch.setattr(transcribe, "decode_audio", lambda src: np.ones(8, dtype=np.float32))
    transcribe.transcribe("film.mp4", tmp_path / "T1.json")
    assert fake_model.instances[0].kwargs == {"device": "cpu", "compute_type": "int8"}


def test_model_cached_looks_in_the_same_folder_the_model_is_downloaded_to(monkeypatch, tmp_path):
    """Gdyby pytał o domyślną pamięć podręczną, przy każdej transkrypcji ostrzegałby o pobieraniu, które już się odbyło."""
    asked = []
    (tmp_path / "model.bin").write_bytes(b"x")

    def where(name, local_files_only=False, **kwargs):
        asked.append((name, local_files_only, kwargs))
        return str(tmp_path)

    monkeypatch.setattr(faster_whisper, "download_model", where)
    assert transcribe.model_cached() is True and asked == [("large-v3-turbo", True, {})]
    as_windows(monkeypatch, PUBLIC="C:\\Users\\Public")
    asked.clear()
    assert transcribe.model_cached("small") is True
    assert asked == [("small", True, {"cache_dir": "C:\\Users\\Public\\trial-reels-model"})]

