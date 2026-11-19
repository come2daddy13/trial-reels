"""Podgląd wersji w przeglądarce: jedna strona HTML z filmami, hookami, podpisami, terminami i statusami.

Strona leży w `dane/podglad.html`, a filmy w `dane/wersje/`, więc ścieżki filmów są względne do `dane/`
(`wersje/TR-001.mp4`) i działają także po przeniesieniu folderu. Wszystkie teksty z danych klienta (hook, podpis,
nazwa rolki, uwagi) przechodzą przez `html.escape`, więc nic z nich nie wykona się na stronie.

Moduł nie ładuje PIL ani PyAV, więc startuje od razu.
"""
from __future__ import annotations

import html
import webbrowser
from pathlib import Path

from . import config

STYLE = """
:root {
  color-scheme: light dark;
  --bg: #f6f5f1; --card: #ffffff; --text: #1d1d1b; --muted: #6b6a64; --line: #e3e1d9;
  --accent: #1f6f5c; --warn: #b3541e; --bad: #a42727;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #17181a; --card: #222427; --text: #f1f0ec; --muted: #a3a29a; --line: #34363a;
          --accent: #55c2a5; --warn: #f0a070; --bad: #f08a8a; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--text);
       font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header, main { max-width: 1180px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 8px; }
.lead { color: var(--muted); margin: 0 0 24px; max-width: 70ch; }
.grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
        display: flex; flex-direction: column; }
video { display: block; width: 100%; aspect-ratio: 9 / 16; max-height: 62vh; background: #000; object-fit: contain; }
.info { padding: 14px 16px 18px; }
h2 { font-size: 1.1rem; margin: 0 0 4px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.reel { color: var(--muted); margin: 0 0 10px; }
.badge { font-size: .75rem; font-weight: 600; padding: 2px 8px; border-radius: 99px; border: 1px solid var(--line); }
.status-do_akceptacji { color: var(--warn); } .status-zaakceptowana, .status-zaplanowana,
.status-opublikowana { color: var(--accent); } .status-odrzucona, .status-blad { color: var(--bad); }
dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; }
dt { color: var(--muted); } dd { margin: 0; overflow-wrap: anywhere; }
pre { margin: 0; white-space: pre-wrap; font: inherit; }
.empty { color: var(--muted); }
"""

# Przeglądarka pokazuje przed odtworzeniem pierwszą klatkę, a hook pojawia się dopiero po ułamku sekundy.
# Ten skrypt przewija każdy film do klatki z hookiem, więc miniatura pokazuje to, co zobaczy widz. Nie ma w nim
# żadnych danych klienta.
SCRIPT = """
document.querySelectorAll("video").forEach(function (video) {
  video.addEventListener("loadedmetadata", function () {
    if (video.duration > 1) { video.currentTime = Math.min(0.8, video.duration / 3); }
  }, { once: true });
});
"""


def _e(value) -> str:
    """Tekst bezpieczny w HTML (także w atrybucie)."""
    return html.escape("" if value is None else str(value), quote=True)


def _reels(pool) -> dict:
    """Rolki jako słownik {kod: rolka}, z listy albo ze słownika."""
    if isinstance(pool, dict):
        return pool
    return {r["code"]: r for r in pool or [] if isinstance(r, dict) and r.get("code")}


def _term(slot) -> str:
    """Termin „2026-11-22 09:00” z zapisu „2026-11-22T09:00:00” (czas z ustawień klienta)."""
    return str(slot)[:16].replace("T", " ") if slot else "bez terminu"


def _card(v: dict, reels: dict) -> str:
    vid = str(v.get("id", "?"))
    reel = reels.get(v.get("code")) or {}
    name = reel.get("name") or v.get("code") or "?"
    status = v.get("status", "")
    hook = " ".join(part for part in (v.get("hook"), v.get("emoji")) if part)
    rows = [("Hook", _e(hook) or "-"),
            ("Poziom zmian", _e(config.LEVEL_LABEL.get(v.get("level"), v.get("level")) or "-")),
            ("Co się zmieniło", _e(v.get("changes")) or "-"),
            ("Termin", _e(_term(v.get("slot"))))]
    if v.get("note"):
        rows.append(("Uwagi", _e(v["note"])))
    rows.append(("Podpis", "<pre>%s</pre>" % _e(v.get("caption"))))
    facts = "\n".join("      <dt>%s</dt><dd>%s</dd>" % (label, value) for label, value in rows)
    return """  <article class="card" id="%(id)s">
    <video controls preload="metadata" src="wersje/%(id)s.mp4"></video>
    <div class="info">
      <h2>%(id)s <span class="badge status-%(status)s">%(label)s</span></h2>
      <p class="reel">Rolka: %(name)s</p>
      <dl>
%(facts)s
      </dl>
    </div>
  </article>""" % {"id": _e(vid), "status": _e(status), "label": _e(config.STATUS_LABEL.get(status, status)),
                   "name": _e(name), "facts": facts}


def build(versions, pool, out) -> Path:
    """Zapisuje stronę z podglądem wersji w pliku `out` (UTF-8) i zwraca jego ścieżkę.

    `versions` to lista wersji albo słownik {id: wersja} (pokazujemy je od najwcześniejszego terminu), a `pool`
    to rolki z puli (słownik {kod: rolka} albo lista). Film każdej wersji leży w `wersje/<ID>.mp4` obok strony.
    """
    out = Path(out)
    items = list(versions.values() if isinstance(versions, dict) else versions or [])
    items.sort(key=lambda v: (v.get("slot") or "", str(v.get("id", ""))))
    reels = _reels(pool)
    if items:
        body = '<div class="grid">\n%s\n</div>' % "\n".join(_card(v, reels) for v in items)
        lead = ("Obejrzyj wersje i powiedz Claude'owi, które odrzucasz (na przykład „odrzuć TR-003”). "
                "Resztę zaakceptujesz jednym zdaniem.")
    else:
        body = '<p class="empty">Brak wersji do pokazania.</p>'
        lead = "Nie ma jeszcze żadnych wersji do obejrzenia."
    page = """<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trial reels: podgląd wersji</title>
<style>%(style)s</style>
</head>
<body>
<header>
  <h1>Trial reels: podgląd wersji</h1>
  <p class="lead">%(lead)s Wersji na stronie: %(count)d.</p>
</header>
<main>
%(body)s
</main>
<script>%(script)s</script>
</body>
</html>
""" % {"style": STYLE, "lead": _e(lead), "count": len(items), "body": body, "script": SCRIPT}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    return out


def open_in_browser(path) -> bool:
    """Otwiera stronę w domyślnej przeglądarce. Zwraca False, gdy system nie ma jak jej otworzyć."""
    return bool(webbrowser.open(Path(path).resolve().as_uri()))
