"""Testy podglądu wersji: strona HTML z filmami, hookami, podpisami i terminami.

Strona leży w dane/podglad.html, a filmy w dane/wersje/, więc ścieżki filmów są względne do dane/. Wszystkie teksty
(hook, podpis, nazwa rolki) przechodzą przez escapowanie HTML. Przeglądarka jest atrapą.
"""
import html
import re
import webbrowser
from pathlib import Path

from trial_reels import config, preview


def version(vid="TR-001", **extra):
    v = {"id": vid, "code": "Cabc123XYZ_", "level": "srednia", "status": "do_akceptacji",
         "hook": "Krótki hook", "emoji": "🔥", "slot": "2026-11-22T09:00:00",
         "caption": "Pierwsza linia podpisu.\n\nDruga linia.", "changes": "hook tekstowy 0–3 s; emotka 🔥"}
    v.update(extra)
    return v


POOL = {"Cabc123XYZ_": {"code": "Cabc123XYZ_", "name": "Przykładowa rolka"}}


def page(versions, pool=POOL):
    out = config.DATA / "podglad.html"
    path = preview.build(versions, pool, out)
    assert path == out and out.is_file()
    return out.read_text(encoding="utf-8")


def test_preview_escapes_text_and_uses_relative_video_paths():
    hook = '<b>Hej</b> & „cudzysłów”'
    text = page([version(hook=hook, caption="Podpis <script>alert(1)</script> & \"cytat\"",
                         changes="zmiana <i>x</i>")], pool={"Cabc123XYZ_": {"name": "Rolka <u>podkreślona</u>"}})
    assert 'src="wersje/TR-001.mp4"' in text
    assert html.escape(hook) in text and hook not in text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert text.count("<script>") == 1                         # tylko własny skrypt strony (miniatury), nic od klienta
    assert "<b>Hej</b>" not in text and "<u>" not in text and "<i>x</i>" not in text
    assert 'controls' in text and 'preload="metadata"' in text


def test_preview_video_tag_has_the_attributes_the_browser_needs():
    text = page([version()])
    assert re.search(r'<video controls preload="metadata" src="wersje/TR-001\.mp4"', text)


def test_preview_shows_hook_level_changes_caption_term_and_status():
    text = page([version()])
    for expected in ("TR-001", "Krótki hook", "🔥", "Średnia", "hook tekstowy 0–3 s", "Pierwsza linia podpisu.",
                     "Druga linia.", "2026-11-22 09:00", "Do akceptacji", "Przykładowa rolka"):
        assert expected in text, expected


def test_preview_is_utf8_with_charset_and_polish_language():
    out = config.DATA / "podglad.html"
    preview.build([version()], POOL, out)
    raw = out.read_bytes()
    assert raw.decode("utf-8")                                   # poprawne UTF-8
    head = raw.decode("utf-8")[:400].lower()
    assert "<!doctype html>" in head and 'charset="utf-8"' in head and 'lang="pl"' in head


def test_the_page_script_holds_no_client_data():
    text = page([version(hook="Hook z <i>tagiem</i>", caption="Podpis z \"cudzysłowem\"")])
    script = text[text.index("<script>"):text.index("</script>")]
    assert "Hook z" not in script and "Podpis" not in script and "TR-001" not in script
    assert "currentTime" in script                             # przewija film do klatki z hookiem


def test_preview_has_one_card_and_video_per_version_in_term_order():
    vs = [version("TR-003", slot="2026-11-23T09:00:00"), version("TR-001", slot="2026-11-21T13:00:00"),
          version("TR-002", slot="2026-11-22T09:00:00")]
    text = page(vs)
    assert text.count("<video") == 3
    positions = [text.index('src="wersje/TR-00%d.mp4"' % n) for n in (1, 2, 3)]
    assert positions == sorted(positions)


def test_preview_accepts_a_dict_of_versions_and_a_list_of_reels():
    vs = {"TR-001": version("TR-001"), "TR-002": version("TR-002")}
    text = page(vs, pool=list(POOL.values()))
    assert text.count("<video") == 2 and "Przykładowa rolka" in text


def test_preview_survives_versions_with_missing_fields():
    bare = {"id": "TR-009", "code": "Nieznany123"}
    text = page([bare])
    assert 'src="wersje/TR-009.mp4"' in text and "TR-009" in text
    assert "Nieznany123" in text                                 # bez rolki w puli pokazujemy sam kod


def test_preview_with_no_versions_says_so():
    text = page([])
    assert "<video" not in text and "Brak wersji" in text


def test_preview_shows_status_labels_and_notes_for_rejected_and_failed():
    text = page([version("TR-004", status="odrzucona", note="Hook za długi <b>"),
                 version("TR-005", status="blad", note="Brak transkrypcji")])
    assert "Odrzucona" in text and "Błąd" in text
    assert "Hook za długi &lt;b&gt;" in text and "Brak transkrypcji" in text


def test_preview_creates_missing_folders_and_overwrites_an_older_page(tmp_path):
    out = tmp_path / "nowy" / "folder" / "podglad.html"
    preview.build([version("TR-001")], POOL, out)
    first = out.read_text(encoding="utf-8")
    preview.build([version("TR-002")], POOL, out)
    second = out.read_text(encoding="utf-8")
    assert "TR-001" in first and "TR-002" not in first
    assert "TR-002" in second and "TR-001.mp4" not in second


def test_preview_works_in_a_folder_with_polish_letters_and_spaces(tmp_path):
    out = tmp_path / "Łukasz Ząb" / "Łódź ąę" / "dane" / "podglad.html"
    preview.build([version()], POOL, out)
    assert 'src="wersje/TR-001.mp4"' in out.read_text(encoding="utf-8")


def test_open_in_browser_opens_the_file_uri(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url) or True)
    path = tmp_path / "Łódź ąę" / "podglad.html"
    path.parent.mkdir()
    path.write_text("<html></html>", encoding="utf-8")
    assert preview.open_in_browser(path) is True
    assert opened == [path.resolve().as_uri()]
    assert opened[0].startswith("file:///") and " " not in opened[0]


def test_open_in_browser_reports_when_there_is_no_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: False)
    path = tmp_path / "podglad.html"
    path.write_text("x", encoding="utf-8")
    assert preview.open_in_browser(path) is False


def test_build_returns_a_path_object(tmp_path):
    assert isinstance(preview.build([], {}, tmp_path / "p.html"), Path)
