"""Render wersji: hook tekstowy nad głową z emotką, mikrozmiany obrazu, przybliżenie, tempo, cięcie pauz
i zimne otwarcie najmocniejszym zdaniem. Wyjście 1080x1920, H.264 + AAC.

Działa tak samo na Macu i na Windowsie. Font Poppins i emotki PNG leżą w assets/, ffmpeg przychodzi z paczki
imageio-ffmpeg, a długość i rozmiar filmu czyta PyAV (bez ffprobe). Ścieżki idą do ffmpeg jako elementy listy,
bez powłoki, więc polskie litery i spacje w nich nie szkodzą.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import av
from PIL import Image, ImageDraw, ImageFont

from . import config

W, H = 1080, 1920
ALT_EMOJI = ["🔥", "👀", "🤯", "⚡", "✅", "🎯", "💡", "🚀"]


def fmt(x: float) -> str:
    return ("%g" % round(x, 2)).replace(".", ",")


# --- font i emotki z paczki --------------------------------------------------

def font_path() -> str:
    """Ścieżka do fontu Poppins Bold z paczki (assets/fonts). Fontów z systemu nie używamy, więc hook wygląda wszędzie tak samo."""
    path = config.ASSETS / "fonts" / "Poppins-Bold.ttf"
    if not path.is_file():
        raise FileNotFoundError("Brak fontu Poppins Bold w paczce: %s. Pobierz paczkę ponownie." % path)
    return str(path)


def _font(size: int) -> ImageFont.FreeTypeFont:
    """Poppins Bold w danym rozmiarze, zawsze z prostym silnikiem układu tekstu (BASIC).

    Domyślnie Pillow wybiera RAQM, o ile jest zainstalowany, a na Windowsie zwykle go nie ma. Szerokości linii
    różnią się wtedy o kilka pikseli i ten sam hook zawijałby się w innych miejscach. BASIC jest w każdej
    instalacji, więc zawijanie i rozmiar dymku są wszędzie takie same.
    """
    return ImageFont.truetype(font_path(), size, layout_engine=ImageFont.Layout.BASIC)


def emoji_key(e: str) -> str:
    """Nazwa pliku emotki bez rozszerzenia: kody szesnastkowe znaków złączone „_”, bez U+FE0F (❤️ daje 2764)."""
    return "_".join("%x" % ord(ch) for ch in e if ch != "️")


def emoji_png(e: str | None) -> Path | None:
    """Plik PNG emotki z assets/emoji albo None, gdy emotki nie ma w paczce (albo nie podano żadnej)."""
    key = emoji_key(e) if e else ""
    if not key:
        return None
    path = config.ASSETS / "emoji" / ("%s.png" % key)
    return path if path.is_file() else None


def emoji_set() -> tuple[str, ...]:
    """Emotki dostępne do hooków: po jednej na każdy plik PNG z assets/emoji, w kolejności nazw plików."""
    found = []
    for path in sorted((config.ASSETS / "emoji").glob("*.png")):
        try:
            e = "".join(chr(int(part, 16)) for part in path.stem.split("_"))
        except (ValueError, OverflowError):
            continue  # plik o nazwie, która nie jest kodem emotki
        if emoji_key(e) == path.stem:
            found.append(e)
    return tuple(found)


# --- nakładka z hookiem ------------------------------------------------------

def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if not cur or draw.textlength(cand, font=font) <= max_w:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _emoji_img(emoji: str, size: int):
    """Naklejka z emotki: PNG przycięty do widocznej części, o szerokości `size` px i obrócony o -8 stopni."""
    path = emoji_png(emoji)
    if path is None:
        return None
    with Image.open(path) as src:
        im = src.convert("RGBA")
    box = im.getbbox()
    if not box:
        return None
    im = im.crop(box)
    im = im.resize((size, max(1, int(size * im.height / im.width))), Image.LANCZOS)
    return im.rotate(-8, resample=Image.BICUBIC, expand=True)


def make_overlay(text: str, emoji: str | None, out: Path, y: float = 0.17,
                 min_w: float = 0.0, min_h: float = 0.0) -> dict:
    """Biały dymek z czarnym tekstem (styl napisu z IG) i emotka jak naklejka w rogu.

    Zapisuje przezroczysty PNG 1080x1920 w `out`. Emotki, której nie ma w assets/emoji, nie rysuje.
    """
    out = Path(out)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 64
    while True:
        font = _font(size)
        lines = _wrap(d, text, font, 820)
        if len(lines) <= 3 or size <= 44:
            break
        size -= 4
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.02)
    tw = max(d.textlength(line, font=font) for line in lines)
    bw = max(int(tw + 80), int(min_w * W))
    bh = max(len(lines) * lh + 44, int(min_h * H))
    top = int(y * H) - bh // 2
    top = max(int(0.085 * H), min(top, int(0.78 * H) - bh))
    left = (W - bw) // 2
    d.rounded_rectangle([left, top, left + bw, top + bh], radius=30, fill=(255, 255, 255, 255))
    ty = top + (bh - len(lines) * lh) // 2 + 4
    for i, line in enumerate(lines):
        d.text(((W - d.textlength(line, font=font)) / 2, ty + i * lh), line, font=font, fill=(17, 17, 17, 255))
    if emoji:
        e = _emoji_img(emoji, 116)
        if e:
            ex = min(W - e.width - 6, left + bw - int(e.width * 0.35))
            ey = max(0, top - int(e.height * 0.65))
            img.alpha_composite(e, (ex, ey))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return {"box": [left, top, bw, bh], "font": size, "lines": lines}


# --- ffmpeg z paczki i PyAV --------------------------------------------------

def _ffmpeg(args, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """Uruchamia ffmpeg z paczki imageio-ffmpeg. Ścieżki w `args` mogą być Path: idą jako elementy listy, bez powłoki.

    Błąd ffmpeg to `CalledProcessError`, a jego komunikat (przy `capture=False`) widać w terminalu.
    """
    return subprocess.run([config.ffmpeg_exe(), "-nostdin", "-hide_banner", *map(str, args)],
                          check=check, capture_output=capture, encoding="utf-8", errors="replace")


def probe(path: Path) -> float:
    """Długość filmu w sekundach (liczba zmiennoprzecinkowa)."""
    with av.open(str(path)) as container:
        if container.duration is not None:
            return container.duration / av.time_base
        spans = [float(s.duration * s.time_base) for s in container.streams if s.duration and s.time_base]
    if not spans:
        raise ValueError("Nie mogę odczytać długości pliku: %s" % path)
    return max(spans)


def dims(path: Path) -> tuple:
    """(szerokość, wysokość) pierwszego strumienia wideo."""
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError("Plik nie ma obrazu (strumienia wideo): %s" % path)
        stream = container.streams.video[0]
        return int(stream.width), int(stream.height)


def _numbers(value, count: int):
    """Lista `count` skończonych liczb (int albo float, bez True i False) albo None."""
    if not isinstance(value, list) or len(value) != count:
        return None
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value):
        return None
    return [float(x) for x in value]


def blur_problem(entry) -> str | None:
    """Co jest nie tak z wpisem pola `blur` (po polsku, bez kropki na końcu) albo None, gdy wpis jest dobry.

    `t` to dwie liczby sekund [od, do] (od 0, „od” mniejsze niż „do”), a `box` to cztery ułamki kadru
    [x, y, szerokość, wysokość], które mieszczą się w kadrze. Tylko liczby: `t` trafia do grafu filtrów ffmpeg, więc
    tekst w nim mógłby dopisać do grafu inny filtr (np. obraz z dysku na publikowanej rolce).
    """
    if not isinstance(entry, dict):
        return "wpis ma być obiektem {\"t\": [od, do], \"box\": [x, y, szerokość, wysokość]}"
    times, box = _numbers(entry.get("t"), 2), _numbers(entry.get("box"), 4)
    if times is None or not 0 <= times[0] < times[1]:
        return "t to dwie liczby sekund [od, do], od 0 wzwyż i „od” mniejsze niż „do”"
    if box is None or min(box) < 0 or box[2] <= 0 or box[3] <= 0 or \
            box[0] + box[2] > 1 + 1e-9 or box[1] + box[3] > 1 + 1e-9:
        return "box to cztery liczby od 0 do 1 [x, y, szerokość, wysokość], a pasek mieści się w kadrze"
    return None


def blur_filter(blur: list, w: int, h: int) -> tuple:
    """Rozmycie fragmentów kadru w czasie źródła. blur: [{"t": [od, do], "box": [x, y, szer, wys]}] w ułamkach kadru.

    Zły wpis (patrz `blur_problem`) to ValueError z polskim opisem, zanim cokolwiek trafi do ffmpeg.
    """
    f, last = [], "0:v"
    for i, b in enumerate(blur):
        problem = blur_problem(b)
        if problem:
            raise ValueError("Pole blur w dane/pula.json, wpis nr %d: %s." % (i + 1, problem))
        x, y, bw, bh = (int(round(v * d)) // 2 * 2 for v, d in zip(b["box"], (w, h, w, h)))
        # Chroma ma połowę rozdzielczości, a boxblur odrzuca promień od ćwiartki mniejszego boku wzwyż.
        # Szeroki pasek dostaje 40, cienki mniej, zamiast błędu ffmpeg.
        r = max(2, min(40, min(bw, bh) // 4 - 1))
        start, end = ("%g" % float(v) for v in b["t"])
        f.append("[%s]split=2[m%d][c%d]" % (last, i, i))
        f.append("[c%d]crop=%d:%d:%d:%d,boxblur=luma_radius=%d:luma_power=3[r%d]" % (i, bw, bh, x, y, r, i))
        f.append("[m%d][r%d]overlay=%d:%d:enable='between(t,%s,%s)'[b%d]" % (i, i, x, y, start, end, i))
        last = "b%d" % i
    return ";".join(f), last


def _inside(path: Path, folder: Path) -> Path:
    """`path`, gdy po rozwinięciu leży w `folder`. Inaczej `UserError`: plik wskazuje poza folder z danymi."""
    if not config.within(path, folder):
        raise config.UserError("Plik %s wskazuje poza swój folder w dane (dowiązanie albo „..”), więc go nie używam."
                               % path.name)
    return path


def source(reel: dict) -> Path:
    """Plik źródłowy rolki; przy `blur` w puli raz renderuję kopię z rozmytymi fragmentami (np. cudze maile)."""
    code = config.checked_code(reel.get("code"))
    src = _inside(config.SRC / ("%s.mp4" % code), config.SRC)
    if not reel.get("blur"):
        return src
    tag = hashlib.sha1(json.dumps(reel["blur"], sort_keys=True).encode()).hexdigest()[:8]
    out = _inside(config.SRC / ("%s.blur-%s.mp4" % (code, tag)), config.SRC)
    if not out.exists():
        graph, last = blur_filter(reel["blur"], *dims(src))
        tmp = out.with_suffix(".tmp.mp4")
        _ffmpeg(["-v", "error", "-y", "-i", src, "-filter_complex", graph, "-map", "[%s]" % last, "-map", "0:a?",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "copy",
                 "-movflags", "+faststart", tmp])
        config._replace(tmp, out)      # z ponowieniami, jak każdy zapis pliku (Windows: plik bywa chwilowo zajęty)
    return out


def silences(path: Path, noise: str = "-32dB", min_d: float = 0.45):
    """Pauzy w dźwięku jako lista (początek, koniec) w sekundach."""
    p = _ffmpeg(["-nostats", "-i", path, "-af", "silencedetect=noise=%s:d=%s" % (noise, min_d), "-f", "null", "-"],
                capture=True, check=False)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    return list(zip(starts, ends))


# --- transkrypcja, parametry i cięcia ----------------------------------------

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)


def find_phrase(code: str, phrase: str):
    """(start, end) frazy w transkrypcji Whispera (słowa ze znacznikami czasu).
    Porównuję sklejone litery, a nie słowa, bo Whisper tnie np. „e-mail” na „e” i „-mail”."""
    path = config.TRANSCRIPTS / ("%s.json" % config.checked_code(code))
    tr = config.read_json(path)
    if tr is None:
        raise FileNotFoundError("Brak transkrypcji rolki %s (szukałem pliku %s)." % (code, path))
    words = [w for s in tr["segments"] for w in s.get("words", [])]
    toks = [_norm(w["w"]) for w in words]
    target = _norm(phrase)
    for i in range(len(toks) if target else 0):
        if not toks[i]:
            continue
        acc = ""
        for j in range(i, len(toks)):
            acc += toks[j]
            if acc == target:
                return words[i]["s"], words[j]["e"]
            if not target.startswith(acc):
                break
    raise ValueError("nie ma frazy w %s: %r" % (code, phrase))


def params_for(vid: str, level: str, reel: dict) -> dict:
    """Parametry losowane deterministycznie z ID wersji (ten sam ID = ten sam render)."""
    rnd = random.Random(vid)
    p = {
        "trim": round(rnd.uniform(0.08, 0.35), 2),
        "sat": round(rnd.uniform(1.0, 1.06), 3),
        "bright": round(rnd.uniform(-0.012, 0.018), 3),
        "contrast": round(rnd.uniform(1.0, 1.04), 3),
        "zoom": 1.0, "tempo": 1.0, "pauses": False, "cold": None,
        "hook_end": round(rnd.uniform(2.6, 3.2), 2),
        "thumb_ms": rnd.randrange(600, 1600, 100),
    }
    if level == "srednia":
        p.update(zoom=round(rnd.uniform(1.05, 1.10), 3), tempo=round(rnd.uniform(1.03, 1.06), 3), pauses=True)
    elif level == "mocna":
        strong = reel.get("strong")
        # Rolka bez mowy nie ma zdania strong (brak, None, puste): nie ma wtedy zimnego otwarcia, a reszta zostaje.
        p.update(zoom=round(rnd.uniform(1.0, 1.06), 3), tempo=round(rnd.uniform(1.0, 1.03), 3),
                 cold=strong if isinstance(strong, str) and strong.strip() else None)
    return p


def keep_segments(start: float, end: float, remove) -> list:
    segs = [(start, end)]
    for a, b in sorted(remove):
        nxt = []
        for s, e in segs:
            if b <= s or a >= e:
                nxt.append((s, e))
                continue
            if a > s:
                nxt.append((s, a))
            if b < e:
                nxt.append((b, e))
        segs = nxt
    return [(round(s, 3), round(e, 3)) for s, e in segs if e - s > 0.2]


def reel_cuts(reel: dict) -> list:
    """Stałe cięcia rolki, np. CTA ze słowem-kluczem: [{"from": fraza, "to": fraza|null}]."""
    out = []
    for c in reel.get("cuts", []):
        a, _ = find_phrase(reel["code"], c["from"])
        b = find_phrase(reel["code"], c["to"])[1] if c.get("to") else 10 ** 6
        out.append((max(0.0, a - 0.05), b + 0.1))
    return out


# --- montaż ------------------------------------------------------------------

def filtergraph(segs, p: dict, full_overlay: bool, fps: int = 30) -> str:
    f = []
    for i, (a, b) in enumerate(segs):
        f.append("[0:v]trim=start=%s:end=%s,setpts=PTS-STARTPTS[v%d]" % (a, b, i))
        f.append("[0:a]atrim=start=%s:end=%s,asetpts=PTS-STARTPTS,afade=t=in:d=0.015,"
                 "afade=t=out:st=%.3f:d=0.03[a%d]" % (a, b, max(0.0, b - a - 0.03), i))
    f.append("%sconcat=n=%d:v=1:a=1[vc][ac]" % ("".join("[v%d][a%d]" % (i, i) for i in range(len(segs))), len(segs)))
    z = p["zoom"]
    zw, zh = int(W * z) // 2 * 2, int(H * z) // 2 * 2
    v = "[vc]setpts=PTS/%s,fps=%d,scale=%d:%d:flags=lanczos" % (p["tempo"], fps, zw, zh)
    if z > 1.0:
        v += ",crop=%d:%d:(iw-%d)/2:(ih-%d)/2" % (W, H, W, H)
    v += ",eq=saturation=%s:brightness=%s:contrast=%s,setsar=1[vs]" % (p["sat"], p["bright"], p["contrast"])
    f.append(v)
    if full_overlay:
        f.append("[1:v]format=rgba[ov]")
        f.append("[vs][ov]overlay=0:0:shortest=1[vo]")
    else:
        f.append("[1:v]format=rgba,fade=t=in:st=0:d=0.12:alpha=1,fade=t=out:st=%.2f:d=0.25:alpha=1[ov]"
                 % (p["hook_end"] - 0.25))
        f.append("[vs][ov]overlay=0:0:eof_action=pass[vo]")
    f.append("[ac]%s,aresample=44100[ao]" % ("atempo=%s" % p["tempo"] if p["tempo"] != 1.0 else "anull"))
    return ";".join(f)


def describe(v: dict, reel: dict) -> str:
    p = v["params"]
    out = ["hook tekstowy przez całą rolkę, zasłania stary napis" if reel.get("mask")
           else "hook tekstowy 0–%s s" % fmt(p["hook_end"])]
    if v.get("emoji"):
        out.append("emotka " + v["emoji"])
    if p.get("cold"):
        out.append("zimne otwarcie zdaniem „%s”" % p["cold"])
    out.append("start od %s s" % fmt(p["trim"]))
    out.append("kolor: nasycenie ×%s, kontrast ×%s" % (fmt(p["sat"]), fmt(p["contrast"])))
    if p["zoom"] > 1:
        out.append("przybliżenie %d%%" % round((p["zoom"] - 1) * 100))
    if p["tempo"] != 1:
        out.append("tempo ×%s" % fmt(p["tempo"]))
    if v.get("pauses_cut"):
        out.append("wycięte pauzy: %d" % v["pauses_cut"])
    if reel.get("cuts"):
        out.append("wycięte CTA ze słowem-kluczem")
    out.append("okładka: kadr z %s s" % fmt(p["thumb_ms"] / 1000))
    return "; ".join(out)


def _overlay_args(reel: dict) -> dict:
    """Położenie i minimalny rozmiar dymka rolki (`mask` zasłania stary napis, `hook_y` przesuwa dymek)."""
    mask = reel.get("mask") or {}
    return {"y": mask.get("y", reel.get("hook_y", 0.17)),
            "min_w": mask.get("min_w", 0.0), "min_h": mask.get("min_h", 0.0)}


def render(v: dict, reel: dict) -> Path:
    """Renderuje wersję `v` rolki `reel` do dane/wersje/<id>.mp4 i uzupełnia `v` (file, duration, segments, changes…).

    Numer wersji trafia do nazw plików, więc zły numer (nie TR-001) to `UserError`, zanim cokolwiek powstanie.
    """
    vid = config.checked_version_id(v.get("id"))
    src = source(reel)
    dur = probe(src)
    p = v["params"]
    remove = reel_cuts(reel)
    pauses = []
    if p.get("pauses"):
        for s, e in silences(src):
            if e - s >= 0.45 and s > p["trim"] + 0.5 and e < dur - 0.3:
                pauses.append((s + 0.12, e - 0.12))
    segs = keep_segments(p["trim"], dur, remove + pauses)
    if p.get("cold"):
        cs, ce = find_phrase(reel["code"], p["cold"])
        segs = [(round(max(0.0, cs - 0.08), 3), round(min(dur, ce + 0.15), 3))] + segs
    mask = reel.get("mask") or {}
    config.OUT.mkdir(parents=True, exist_ok=True)
    ov = _inside(config.OUT / ("%s_hook.png" % vid), config.OUT)
    out = _inside(config.OUT / ("%s.mp4" % vid), config.OUT)
    make_overlay(v["hook"], v.get("emoji"), ov, **_overlay_args(reel))
    loop = ["-loop", "1", "-framerate", "30"] + ([] if mask else ["-t", "%.2f" % p["hook_end"]]) + ["-i", ov]
    _ffmpeg(["-v", "error", "-y", "-i", src] + loop + [
        "-filter_complex", filtergraph(segs, p, bool(mask)), "-map", "[vo]", "-map", "[ao]",
        "-map_metadata", "-1", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out])
    v["file"] = str(out)
    v["pauses_cut"] = len(pauses)
    v["segments"] = segs
    v["duration"] = round(probe(out), 2)
    v["changes"] = describe(v, reel)
    return out


# --- klatki ------------------------------------------------------------------

END_MARGIN = 0.25  # s: tak blisko końca filmu klatki zwykle już nie ma, bo ostatnia klatka kończy się przed końcem pliku


def _grab_problem(src, t: float) -> str:
    """Jedna linia po polsku o tym, czemu nie ma klatki: czas za końcem filmu (z długością filmu), sam koniec filmu
    (tam klatki często już nie ma, choć czas mieści się w filmie) albo zepsuty plik."""
    try:
        length = probe(Path(src))
    except Exception:  # PyAV nie czyta pliku, więc to nie czas jest za duży, tylko film jest uszkodzony
        length = None
    if length is not None and t >= length:
        return ("Film ma tylko %s s, więc nie ma w nim klatki z %s s. Podaj mniejszy czas w opcji --t."
                % (fmt(length), fmt(t)))
    if length is not None and t >= length - END_MARGIN:
        return ("Film ma %s s, a tuż przed jego końcem nie ma już klatki do wyciągnięcia, więc nie ma jej w %s s. "
                "Podaj w opcji --t czas mniejszy niż %s s." % (fmt(length), fmt(t), fmt(max(0.0, length - END_MARGIN))))
    return "Nie udało się wyciągnąć klatki z %s s: plik jest uszkodzony albo ffmpeg go nie odczytał." % fmt(t)


def _grab(args: list, out: Path, t: float, src) -> Path:
    """Uruchamia ffmpeg, który ma zapisać jedną klatkę, i dopiero po sukcesie podmienia nią `out`.

    `args` to argumenty ffmpeg bez pliku wyjściowego. Klatka powstaje najpierw obok `out` (z tym samym rozszerzeniem,
    żeby ffmpeg wybrał ten sam format), więc nieudane wywołanie nie kasuje klatki z poprzedniego, a ewentualny stary
    plik nie udaje sukcesu.

    Wyjście ffmpeg jest przechwycone (po angielsku, kilkanaście linii), więc klient widzi tylko jedną linię po polsku:
    czas za końcem filmu `src` kończy się RuntimeError z długością filmu, uszkodzony plik też RuntimeError.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("%s.tmp%s" % (out.stem, out.suffix))
    tmp.unlink(missing_ok=True)
    try:
        try:
            _ffmpeg([*args, tmp], capture=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(_grab_problem(src, t)) from e
        if not tmp.is_file():
            raise RuntimeError(_grab_problem(src, t))
        config._replace(str(tmp), out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


def hook_frame(reel: dict, text: str, emoji: str | None, t: float, out: Path) -> Path:
    """Podgląd hooka: klatka źródła rolki z czasu `t` (s) w 1080x1920, z dymkiem i emotką tak jak w renderze."""
    src = source(reel)
    out = Path(out)
    with tempfile.TemporaryDirectory() as tmp:
        ov = Path(tmp) / "hook.png"
        make_overlay(text, emoji, ov, **_overlay_args(reel))
        graph = "[0:v]scale=%d:%d:flags=lanczos,setsar=1[bg];[1:v]format=rgba[ov];[bg][ov]overlay=0:0[vo]" % (W, H)
        return _grab(["-v", "error", "-y", "-ss", str(t), "-i", src, "-i", ov, "-filter_complex", graph,
                      "-map", "[vo]", "-frames:v", "1", "-q:v", "3"], out, t, src)
