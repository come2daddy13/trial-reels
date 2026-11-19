"""Testy notatek wydania: sekcje ZMIANY.md od poprzedniego wydania do bieżącego.

`aktualizuj` pokazuje klientowi notatki jednego wydania (najnowszego). Klient, który pominął wydanie, nie zobaczyłby jego
zmian, więc notatki każdego wydania zawierają też sekcje wydań, które klient mógł pominąć.
"""
import subprocess
import sys
from pathlib import Path

import pytest

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE / "tools"))

import notatki  # noqa: E402

CHANGELOG = """# Zmiany

Każde wydanie ma osobną sekcję z numerem wersji.

## 0.3.0

Trzecie wydanie.

- Nowość C.

## 0.2.0

Drugie wydanie.

- Nowość B.

## 0.1.0

Pierwsze wydanie.

- Nowość A.
"""


def headings(text):
    return [line for line in text.splitlines() if line.startswith("## ")]


def test_sections_are_found_by_their_version_in_file_order():
    found = notatki.sections(CHANGELOG)
    assert [version for version, _ in found] == [(0, 3, 0), (0, 2, 0), (0, 1, 0)]
    assert found[1][1].startswith("## 0.2.0\n") and "Nowość B." in found[1][1] and "Nowość C." not in found[1][1]


def test_the_first_release_has_only_its_own_section():
    text = notatki.notes(CHANGELOG, "0.1.0", [])
    assert headings(text) == ["## 0.1.0"] and "Nowość A." in text and "Nowość B." not in text


def test_a_release_includes_every_section_since_the_previous_tag():
    """Klient z wersją 0.1.0, który pominął 0.2.0, widzi przy aktualizacji do 0.3.0 zmiany obu wydań."""
    text = notatki.notes(CHANGELOG, "0.3.0", ["v0.1.0", "v0.2.0"])
    assert headings(text) == ["## 0.3.0"] and "Nowość B." not in text                     # poprzedni tag to 0.2.0
    text = notatki.notes(CHANGELOG, "0.3.0", ["v0.1.0"])
    assert headings(text) == ["## 0.3.0", "## 0.2.0"] and "Nowość C." in text and "Nowość B." in text
    assert "Nowość A." not in text                                                          # 0.1.0 klient już ma
    text = notatki.notes(CHANGELOG, "0.3.0", [])
    assert headings(text) == ["## 0.3.0"]                                                   # bez tagów: tylko bieżące


def test_previous_is_the_greatest_older_tag_by_numbers_and_unreadable_tags_are_ignored():
    tags = ["v0.9.0", "v0.10.0", "v1.0.0-beta", "latest", "v0.2.0", "v0.10.1"]
    assert notatki.previous((0, 10, 1), tags) == (0, 10, 0)                  # 0.10.0 jest nowsze niż 0.9.0
    assert notatki.previous((0, 10, 0), tags) == (0, 9, 0)
    assert notatki.previous((0, 2, 0), tags) is None
    assert notatki.previous((0, 2, 0), ["v0.2.0"]) is None                    # sam bieżący tag nie jest poprzednim
    assert notatki.previous((1, 0, 0), ["v1.0.0-beta"]) is None               # wydania próbne się nie liczą


def test_numbers_of_ten_are_compared_as_numbers_not_as_text():
    text = "## 0.10.0\n\nDziesiąte.\n\n- Tak.\n\n## 0.9.0\n\nDziewiąte.\n\n- Tak.\n\n## 0.2.0\n\nDrugie.\n\n- Tak.\n"
    assert headings(notatki.notes(text, "0.10.0", ["v0.2.0"])) == ["## 0.10.0", "## 0.9.0"]


def test_the_current_release_must_have_a_section_with_a_description():
    with pytest.raises(ValueError, match="ZMIANY.md nie ma sekcji ## 0.4.0"):
        notatki.notes(CHANGELOG, "0.4.0", ["v0.3.0"])
    with pytest.raises(ValueError, match="ZMIANY.md nie ma sekcji ## 0.2.0 z opisem"):
        notatki.notes("## 0.2.0\n\n## 0.1.0\n\nOpis.\n\n- A.\n", "0.2.0", [])
    with pytest.raises(ValueError, match="numer wersji"):
        notatki.notes(CHANGELOG, "trzecia", [])


def test_windows_line_ends_in_the_changelog_do_not_matter():
    text = notatki.notes(CHANGELOG.replace("\n", "\r\n"), "0.3.0", ["v0.1.0"])
    assert "\r" not in text and headings(text) == ["## 0.3.0", "## 0.2.0"]


def test_command_line_prints_the_notes_and_fails_with_a_message(tmp_path, capsys):
    path = tmp_path / "ZMIANY.md"
    path.write_text(CHANGELOG, encoding="utf-8")
    assert notatki.main(["0.3.0", "--tagi", "v0.1.0 v0.2.0", "--plik", str(path)]) == 0
    out = capsys.readouterr().out
    assert headings(out) == ["## 0.3.0"] and out.endswith("\n") and not out.endswith("\n\n")
    assert notatki.main(["0.3.0", "--tagi", "v0.1.0\nv0.2.0\n", "--plik", str(path)]) == 0      # tagi z `git tag --list`
    assert notatki.main(["0.9.0", "--plik", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out.count("## ") == 1 and "Notatki: ZMIANY.md nie ma sekcji ## 0.9.0" in captured.err
    assert notatki.main(["0.3.0", "--plik", str(tmp_path / "nie-ma.md")]) == 1
    assert "Notatki:" in capsys.readouterr().err


def test_the_tool_runs_as_a_script_on_the_real_changelog():
    version = (CODE / "VERSION").read_text(encoding="utf-8").strip()
    done = subprocess.run([sys.executable, str(CODE / "tools" / "notatki.py"), version], cwd=CODE, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("## %s\n" % version)


def test_the_release_workflow_builds_its_notes_with_the_tool_from_all_tags():
    text = (CODE / ".github" / "workflows" / "wydanie.yml").read_text(encoding="utf-8")
    step = text.split("- name: Notatki z ZMIANY.md", 1)[1].split("- uses:", 1)[0]
    assert "tools/notatki.py" in step and "git tag --list" in step and "awk" not in step
    assert "> dist/notatki.md" in step                       # notatki jadą z zipem w artefakcie do joba wydania
    assert "--notes-file dist/notatki.md" in text
