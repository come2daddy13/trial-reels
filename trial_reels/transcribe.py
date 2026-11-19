"""Transkrypcja mowy do pliku JSON ze słowami i ich czasami (faster-whisper, model liczy na procesorze).

Dźwięk dekodujemy sami, przez ffmpeg z paczki imageio-ffmpeg, a nie przez `faster_whisper.decode_audio`: ta funkcja
korzysta z PyAV i przestaje działać z PyAV 19. Ścieżki idą do ffmpeg jako elementy listy, bez powłoki, więc polskie
litery i spacje w nich nie szkodzą.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path, PureWindowsPath

import numpy as np

from . import config

SAMPLE_RATE = 16000  # Whisper przyjmuje dźwięk mono 16 kHz
DEFAULT_MODEL = "large-v3-turbo"  # ok. 1,6 GB, pobiera się przy pierwszej transkrypcji
MODEL_FOLDER = "trial-reels-model"  # folder na model w ASCII-owej ścieżce (patrz `model_root`)

# Modele załadowane w tym procesie (po nazwie). Ładowanie trwa kilkanaście sekund, więc transkrypcja kolejnych
# rolek w jednym uruchomieniu korzysta z tego samego modelu.
_MODEL_CACHE: dict = {}


def decode_audio(src) -> np.ndarray:
    """Dźwięk z pliku (wideo albo samo audio) jako tablica float32: mono, 16 kHz, próbki od -1 do 1.

    Plik bez dźwięku, uszkodzony albo nieistniejący zgłasza błąd z nazwą pliku i powodem.
    """
    path = Path(src)
    if not path.is_file():
        raise FileNotFoundError("Brak pliku do transkrypcji: %s" % path)
    # Wyjście ffmpeg to surowe bajty PCM, więc stdout czytamy binarnie, a komunikat błędu dekodujemy sami.
    proc = subprocess.run(
        [config.ffmpeg_exe(), "-nostdin", "-hide_banner", "-v", "error", "-i", str(path), "-vn",
         "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        if "does not contain any stream" in detail:
            raise RuntimeError("W pliku %s nie ma dźwięku, więc nie da się zrobić transkrypcji." % path)
        raise RuntimeError("ffmpeg nie odczytał dźwięku z pliku %s: %s" % (path, detail[-400:]))
    raw = proc.stdout[: len(proc.stdout) // 2 * 2]  # pełne próbki po 2 bajty
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    audio /= 32768.0
    return audio


def to_words_json(segments) -> dict:
    """Segmenty z faster-whisper (z `word_timestamps=True`) jako słownik do zapisu w JSON.

    Postać: {"segments": [{"start", "end", "text", "words": [{"w", "s", "e"}]}]}. Liczby są zaokrąglone do
    3 miejsc, a tekst słów zostaje taki, jak go zwrócił Whisper (ze spacją na początku).
    """
    out = []
    for seg in segments:
        words = [{"w": w.word, "s": round(float(w.start), 3), "e": round(float(w.end), 3)}
                 for w in (getattr(seg, "words", None) or [])]
        out.append({"start": round(float(seg.start), 3), "end": round(float(seg.end), 3),
                    "text": seg.text, "words": words})
    return {"segments": out}


def hub_cache() -> str:
    """Domyślny folder pamięci podręcznej Hugging Face, w którym faster-whisper trzyma model (`~/.cache/huggingface/hub`,
    albo folder z `HF_HOME` czy `HF_HUB_CACHE`)."""
    from huggingface_hub import constants

    return str(constants.HF_HUB_CACHE)


def model_root() -> str | None:
    """Folder, do którego pobieramy model i z którego go czytamy, gdy domyślny nie nadaje się. Zwykle None (domyślny).

    Na Windowsie model czyta natywna biblioteka (CTranslate2), która potrafi nie otworzyć pliku ze ścieżki z polskimi
    literami, np. C:\\Users\\Łukasz Ząb\\.cache\\huggingface. Gdy domyślny folder ma w ścieżce znaki spoza ASCII,
    model leży więc w `%PUBLIC%\\trial-reels-model` (a gdy nie ma zmiennej PUBLIC, w
    `C:\\Users\\Public\\trial-reels-model`). Na Macu i przy ścieżce w ASCII zostaje domyślny folder.
    """
    if os.name != "nt" or hub_cache().isascii():
        return None
    return str(PureWindowsPath(os.environ.get("PUBLIC") or "C:\\Users\\Public", MODEL_FOLDER))


def model_cached(model: str = DEFAULT_MODEL) -> bool:
    """Czy model leży już na dysku (w pamięci podręcznej Hugging Face), więc nic nie trzeba pobierać z internetu.

    Pyta tylko dysk, w tym samym folderze, do którego model jest pobierany (`model_root`). Model, którego brakuje albo
    który jest pobrany niepełnie (bez pliku `model.bin`), daje False.
    """
    try:
        from faster_whisper import download_model

        root = model_root()
        folder = download_model(model, local_files_only=True, **({"cache_dir": root} if root else {}))
    except Exception:  # nie ma go w pamięci podręcznej albo nazwa jest zła
        return False
    return (Path(folder) / "model.bin").is_file()


def _model(name: str):
    """Model Whispera o danej nazwie, załadowany raz na proces. Błąd ładowania niczego nie zapamiętuje."""
    if name not in _MODEL_CACHE:
        from faster_whisper import WhisperModel  # ciężki import dopiero tu, żeby inne komendy startowały szybko

        root = model_root()
        _MODEL_CACHE[name] = WhisperModel(name, device="cpu", compute_type="int8",
                                          **({"download_root": root} if root else {}))
    return _MODEL_CACHE[name]


def transcribe(src, out, model: str = DEFAULT_MODEL, language: str = "pl") -> Path:
    """Robi transkrypcję pliku `src` i zapisuje ją w `out` (UTF-8, atomowo). Zwraca ścieżkę zapisanego pliku.

    Najpierw czyta dźwięk, więc brak pliku albo dźwięku wychodzi, zanim wczyta się duży model. Przy pierwszym
    użyciu modelu faster-whisper pobiera go z internetu (ponad 1 GB), potem bierze z dysku. Model ładuje się
    raz na proces, więc kolejne wywołania z tą samą nazwą modelu są szybkie.

    Włączony filtr aktywności głosu (`vad_filter`) odcina muzykę i ciszę, więc Whisper nie wymyśla zdań tam, gdzie
    nikt nie mówi. Rolka bez mowy dostaje transkrypcję bez żadnego słowa (`{"segments": []}`).
    """
    audio = decode_audio(src)
    if audio.size == 0:
        data = {"segments": []}  # pusty dźwięk: nie ma czego transkrybować
    else:
        segments, _info = _model(model).transcribe(audio, language=language, word_timestamps=True, vad_filter=True)
        data = to_words_json(segments)
    out = Path(out)
    config.write_json(out, data)
    return out
