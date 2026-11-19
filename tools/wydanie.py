"""Wydanie: zip z kodem dla klienta i lista plików PLIKI.txt.

Uruchomienie z dowolnego folderu (korzeniem jest folder nad `tools/`):

    python tools/wydanie.py OUT.zip [--repo WŁAŚCICIEL/NAZWA]

Zip powstaje z `git archive --format=zip HEAD` (bez prefiksu), więc zawiera tylko zatwierdzone pliki, bez tych z
`export-ignore` w `.gitattributes` (testy, narzędzia, CI). Do zipa trafia `PLIKI.txt`: posortowana lista dokładnie tych
plików, które są w archiwum (bez samego PLIKI.txt). Aktualizacja u klienta czyta ją, żeby usunąć pliki, które nowe
wydanie porzuciło.

Adres repozytorium: program pyta o aktualizacje repozytorium z `REPO_SLUG` w `trial_reels/config.py`, a README każe z
niego instalować. Wydanie powstaje tylko wtedy, gdy oba miejsca wskazują to samo prawdziwe repozytorium na GitHubie:
- z `--repo` (w CI: `$GITHUB_REPOSITORY`) adres musi być dokładnie tym repozytorium, z którego idzie wydanie;
- bez `--repo` adres nie może być zastępczy (nazwą, której GitHub nie dopuszcza). Wyjątek dla lokalnego testu
  instalacji: zmienna TRIAL_REELS_WYDANIE_TEST=1.

Kod wyjścia: 0 gdy wydanie gotowe, 1 przy błędzie. Narzędzie używa tylko biblioteki standardowej i gita.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST_NAME = "PLIKI.txt"
CONFIG_FILE = "trial_reels/config.py"
README = "README.md"
TEST_ENV = "TRIAL_REELS_WYDANIE_TEST"     # =1: lokalny test instalacji, wolno zbudować wydanie z adresem zastępczym

# Te same reguły nazw co w trial_reels/config.py (`repo_problem`): konto albo organizacja to do 39 liter i cyfr
# z pojedynczymi „-” w środku, a repozytorium to litery, cyfry, „.”, „-” i „_”.
_OWNER = re.compile(r"[A-Za-z0-9](?:-?[A-Za-z0-9])*")
_NAME = re.compile(r"[A-Za-z0-9._-]+")
_LINK = re.compile(r"https://github\.com/([^/\s`'\"()<>]+)/([^/\s`'\"()<>?#]+)")


def _git(root: Path, *args: str) -> None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, stdin=subprocess.DEVNULL,
                              encoding="utf-8", errors="replace")
    except OSError:
        raise RuntimeError("nie mogę uruchomić gita (czy jest zainstalowany?)") from None
    if done.returncode != 0:
        lines = (done.stderr or "").strip().splitlines()
        raise RuntimeError("git %s zakończył się błędem%s" % (args[0], ": " + lines[0] if lines else ""))


def _add_list(out: Path) -> None:
    """Dopisuje do archiwum PLIKI.txt z listą plików (bez folderów i bez samej listy), posortowaną."""
    with zipfile.ZipFile(out, "a") as archive:
        infos = archive.infolist()
        names = sorted(info.filename for info in infos if not info.filename.endswith("/"))
        if LIST_NAME in names:
            raise ValueError("w repo jest już plik %s, a wydanie tworzy go samo. Usuń go z repo." % LIST_NAME)
        entry = zipfile.ZipInfo(LIST_NAME, date_time=infos[0].date_time if infos else (1980, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o644 << 16
        archive.writestr(entry, "".join(name + "\n" for name in names))


def _real(slug: str) -> bool:
    """Czy `slug` (właściciel/nazwa) może być repozytorium na GitHubie."""
    owner, _, name = slug.partition("/")
    return len(owner) <= 39 and bool(_OWNER.fullmatch(owner)) and bool(_NAME.fullmatch(name)) and name not in (".", "..")


def _config_slug(text: str) -> str | None:
    """Wartość `REPO_SLUG = "…"` z tekstu config.py (bez uruchamiania kodu) albo None, gdy jej nie ma."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        raise ValueError("%s ma błąd składni, więc nie odczytam z niego adresu repozytorium" % CONFIG_FILE) from None
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        value = getattr(node, "value", None)
        if any(isinstance(t, ast.Name) and t.id == "REPO_SLUG" for t in targets) and \
                isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def check_repo(out: Path, repo: str | None) -> None:
    """Sprawdza adres repozytorium w zbudowanym zipie (config.py i README.md). Zły adres to `ValueError`."""
    with zipfile.ZipFile(out) as archive:
        names = set(archive.namelist())
        slug = _config_slug(archive.read(CONFIG_FILE).decode("utf-8")) if CONFIG_FILE in names else None
        readme = archive.read(README).decode("utf-8") if README in names else ""
    if CONFIG_FILE in names and slug is None:
        raise ValueError("w %s nie ma REPO_SLUG z adresem repozytorium" % CONFIG_FILE)
    links = ["%s/%s" % match for match in _LINK.findall(readme)]
    if repo is not None:
        if slug is None:
            raise ValueError("w wydaniu nie ma %s z REPO_SLUG, więc nie sprawdzę, skąd program pobierze aktualizacje"
                             % CONFIG_FILE)
        if slug.casefold() != repo.casefold():
            raise ValueError("REPO_SLUG w %s („%s”) różni się od repozytorium, z którego idzie wydanie („%s”). Wpisz "
                             "adres tego repozytorium w %s i %s." % (CONFIG_FILE, slug, repo, CONFIG_FILE, README))
    expected = repo if repo is not None else slug
    for link in links:
        if expected is not None and link.casefold() != expected.casefold():
            raise ValueError("%s wskazuje repozytorium „%s”, a program „%s”. Popraw adresy w %s, żeby były takie same."
                             % (README, link, expected, README))
    if repo is None and os.environ.get(TEST_ENV) != "1":
        for where, value in [(CONFIG_FILE, slug)] + [(README, link) for link in links]:
            if value is not None and not _real(value):
                raise ValueError("adres repozytorium w %s („%s”) jest zastępczy: GitHub nie dopuszcza takiej nazwy. "
                                 "Wpisz prawdziwą organizację w %s i %s (do lokalnego testu instalacji ustaw %s=1)."
                                 % (where, value, CONFIG_FILE, README, TEST_ENV))


def build(root: Path, out: Path, repo: str | None = None) -> Path:
    """Buduje wydanie z zatwierdzonego stanu repo w `root` (HEAD) i zapisuje je jako zip `out`. Zwraca ścieżkę zipa.

    `repo` (właściciel/nazwa) to repozytorium, z którego idzie wydanie: adres w programie musi być właśnie nim.
    """
    root = Path(root)
    out = Path(os.path.abspath(out))             # git pracuje w `root`, więc ścieżka względna wskazałaby tam
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        _git(root, "archive", "--format=zip", "-o", str(out), "HEAD")
        check_repo(out, repo)
        _add_list(out)
    except BaseException:
        try:
            out.unlink()
        except OSError:
            pass
        raise
    return out


def main(argv: list[str] | None = None, root: str | os.PathLike | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wydanie", description="Buduje zip wydania z kodem dla klienta.",
                                     epilog="Kody wyjścia: 0 gotowe, 1 błąd.")
    parser.add_argument("out", metavar="OUT.zip", help="plik zipa do utworzenia")
    parser.add_argument("--repo", metavar="WŁAŚCICIEL/NAZWA",
                        help="repozytorium, z którego idzie wydanie (w CI: $GITHUB_REPOSITORY); adres w programie musi "
                             "być tym repozytorium")
    args = parser.parse_args(argv)
    try:
        out = build(Path(root) if root is not None else ROOT, Path(args.out), repo=args.repo)
        with zipfile.ZipFile(out) as archive:
            files = sum(1 for name in archive.namelist() if not name.endswith("/"))
    except (RuntimeError, ValueError, OSError, zipfile.BadZipFile) as err:
        print("Wydanie: %s" % " ".join(str(err).split()), file=sys.stderr)
        return 1
    print("Wydanie gotowe: %s (plików: %d)." % (out, files))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
