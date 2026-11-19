"""Testy wydania: zip z kodem dla klienta (bez testów i narzędzi deweloperskich) oraz lista PLIKI.txt.

Wydanie powstaje z `git archive HEAD`, a reguły `export-ignore` czyta git z zatwierdzonego `.gitattributes`. Dlatego testy
budują własne, tymczasowe repo z prawdziwym `.gitattributes` tego repo, a nie sprawdzają bieżącego HEAD.
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE / "tools"))

import wydanie  # noqa: E402

from trial_reels import update  # noqa: E402

FILES = {
    "VERSION": "0.1.0\n",
    "requirements.txt": "pakiet==1\n",
    "requirements-dev.txt": "pytest==1\n",
    "trial.sh": "#!/usr/bin/env bash\necho hi\n",
    "trial.cmd": "@echo off\necho hi\n",
    "trial_reels/__init__.py": "# kod\n",
    "trial_reels/__main__.py": "# wejście\n",
    "assets/fonts/Poppins-Bold.ttf": b"\x00\x01font",
    "assets/emoji/1f525.png": b"\x89PNG-obraz",
    ".claude/skills/trial-reels/SKILL.md": "# skill\n",
    "CLAUDE.md": "# zasady\n",
    "tests/test_a.py": "def test_a():\n    pass\n",
    "tools/wydanie.py": "# narzędzie\n",
    ".github/workflows/testy.yml": "name: testy\n",
}
DEV_ONLY = ("tests/", "tools/", ".github/", "requirements-dev.txt")


def git(repo, *args) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def write(repo, name, content) -> None:
    path = Path(repo) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


@pytest.fixture
def isolated_git(tmp_path, monkeypatch):
    """Git odcięty od globalnej konfiguracji (podpisy, hooki, autocrlf) i od repo nad folderem testu."""
    empty = tmp_path / "pusta-konfiguracja-gita"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))


def new_repo(tmp_path, name="repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Trial Reels")
    git(repo, "config", "user.email", "trial-reels@users.noreply.github.com")
    return repo


def commit_all(repo, message="zmiana") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", message)


@pytest.fixture
def release_repo(tmp_path, isolated_git):
    """Repo z plikami klienta i deweloperskimi oraz z prawdziwym `.gitattributes`, jedno zatwierdzenie."""
    repo = new_repo(tmp_path)
    shutil.copy(CODE / ".gitattributes", repo / ".gitattributes")
    for name, content in FILES.items():
        write(repo, name, content)
    commit_all(repo, "pierwsze")
    return repo


def names_of(zip_path) -> list:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.namelist()


def file_names(zip_path) -> list:
    return [n for n in names_of(zip_path) if not n.endswith("/")]


# --- .gitattributes -------------------------------------------------------------

def test_gitattributes_keeps_the_launcher_rules_and_ignores_developer_files():
    lines = [line.strip() for line in (CODE / ".gitattributes").read_text(encoding="utf-8").splitlines()]
    for needed in ("*.sh text eol=lf", "*.cmd text eol=crlf", "*.png binary", "*.ttf binary",
                   "tests/ export-ignore", "tools/ export-ignore", ".github/ export-ignore",
                   "requirements-dev.txt export-ignore"):
        assert needed in lines, needed


# --- zawartość zipa -------------------------------------------------------------

def test_release_zip_has_no_developer_files(tmp_path, release_repo):
    out = wydanie.build(release_repo, tmp_path / "wydanie" / "trial-reels.zip")
    names = names_of(out)
    assert not [n for n in names if n.startswith(DEV_ONLY) or n == "requirements-dev.txt"], names
    assert "tests/" not in names and "tools/" not in names and ".github/" not in names


def test_release_zip_has_the_client_files_without_a_prefix(tmp_path, release_repo):
    names = set(file_names(wydanie.build(release_repo, tmp_path / "trial-reels.zip")))
    assert names == {".gitattributes", "VERSION", "requirements.txt", "trial.sh", "trial.cmd", "CLAUDE.md",
                     "trial_reels/__init__.py", "trial_reels/__main__.py", "assets/fonts/Poppins-Bold.ttf",
                     "assets/emoji/1f525.png", ".claude/skills/trial-reels/SKILL.md", "PLIKI.txt"}


def test_list_file_matches_the_archive_exactly(tmp_path, release_repo):
    out = wydanie.build(release_repo, tmp_path / "trial-reels.zip")
    with zipfile.ZipFile(out) as zf:
        listed_text = zf.read("PLIKI.txt").decode("utf-8")
    listed = listed_text.splitlines()
    assert listed == sorted(n for n in file_names(out) if n != "PLIKI.txt")
    assert "PLIKI.txt" not in listed
    assert listed_text.endswith("\n") and "\r" not in listed_text and "" not in listed
    assert len(file_names(out)) == len(listed) + 1                    # wszystko poza samą listą


def test_the_zip_is_valid_and_has_unique_names(tmp_path, release_repo):
    out = wydanie.build(release_repo, tmp_path / "trial-reels.zip")
    names = names_of(out)
    assert len(names) == len(set(names))
    with zipfile.ZipFile(out) as zf:
        assert zf.testzip() is None


def test_release_uses_only_committed_files(tmp_path, release_repo):
    write(release_repo, "VERSION", "9.9.9\n")                          # zmiana niezatwierdzona
    write(release_repo, "nowy-plik.py", "# niezatwierdzony\n")
    out = wydanie.build(release_repo, tmp_path / "trial-reels.zip")
    with zipfile.ZipFile(out) as zf:
        assert zf.read("VERSION") == b"0.1.0\n"
    assert "nowy-plik.py" not in names_of(out)


def test_launchers_keep_their_line_endings_in_the_zip(tmp_path, release_repo):
    out = wydanie.build(release_repo, tmp_path / "trial-reels.zip")
    with zipfile.ZipFile(out) as zf:
        sh, cmd = zf.read("trial.sh"), zf.read("trial.cmd")
    assert b"\r" not in sh                                             # bash nie zniesie CRLF
    assert cmd.count(b"\n") > 0 and cmd.count(b"\n") == cmd.count(b"\r\n")   # cmd.exe lubi tylko CRLF


def test_build_creates_missing_folders_and_overwrites_an_old_zip(tmp_path, release_repo):
    out = tmp_path / "gleboko" / "w" / "trial-reels.zip"
    wydanie.build(release_repo, out)
    first = file_names(out)
    write(release_repo, "dodatkowy.py", "# nowy\n")
    commit_all(release_repo, "dodatkowy")
    assert wydanie.build(release_repo, out) == out
    assert set(file_names(out)) == set(first) | {"dodatkowy.py"}
    assert len(names_of(out)) == len(set(names_of(out)))               # bez dopisywania do starego pliku


def test_build_accepts_a_relative_output_path(tmp_path, release_repo, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = wydanie.build(release_repo, Path("wynik") / "trial-reels.zip")
    assert out.is_file() and out.parent.name == "wynik" and (tmp_path / "wynik" / "trial-reels.zip").is_file()


def test_build_refuses_a_repo_that_already_tracks_a_list_file(tmp_path, release_repo):
    write(release_repo, "PLIKI.txt", "reczna lista\n")
    commit_all(release_repo, "lista")
    out = tmp_path / "trial-reels.zip"
    with pytest.raises(ValueError, match="PLIKI.txt"):
        wydanie.build(release_repo, out)
    assert not out.exists()


def test_build_outside_a_repository_is_a_plain_error_and_leaves_no_zip(tmp_path, isolated_git):
    folder = tmp_path / "nie-repo"
    folder.mkdir()
    out = tmp_path / "trial-reels.zip"
    with pytest.raises(RuntimeError, match="git"):
        wydanie.build(folder, out)
    assert not out.exists()


def test_build_without_any_commit_is_a_plain_error(tmp_path, isolated_git):
    repo = new_repo(tmp_path, "pusty")
    with pytest.raises(RuntimeError, match="git"):
        wydanie.build(repo, tmp_path / "trial-reels.zip")
    assert not (tmp_path / "trial-reels.zip").exists()


# --- adres repozytorium w programie (K1) -----------------------------------------

EXAMPLE_REPO = "przyklad-org/trial-reels"
PLACEHOLDER_REPO = "__PRZYKLAD__/trial-reels"       # podkreśleń nie ma w nazwach kont na GitHubie


def repo_with_address(tmp_path, slug, readme_slug=None, name="repo-adres") -> Path:
    """Repo z config.py (REPO_SLUG) i README.md z adresem instalacji, jedno zatwierdzenie."""
    repo = new_repo(tmp_path, name)
    shutil.copy(CODE / ".gitattributes", repo / ".gitattributes")
    write(repo, "VERSION", "0.1.0\n")
    write(repo, "trial_reels/__init__.py", "# kod\n")
    write(repo, "trial_reels/config.py", 'ZERNIO_BASE = "https://api.example.com/v1"\nREPO_SLUG = "%s"\n' % slug)
    write(repo, "README.md", "Zainstaluj trial reels z https://github.com/%s i poprowadź mnie\n\n"
                             "curl -fL -o trial-reels.zip https://github.com/%s/releases/latest/download/trial-reels.zip\n"
          % ((readme_slug or slug,) * 2))
    commit_all(repo, "adres")
    return repo


def test_release_with_a_real_repo_address_is_built(tmp_path, isolated_git):
    repo = repo_with_address(tmp_path, EXAMPLE_REPO)
    assert wydanie.build(repo, tmp_path / "trial-reels.zip").is_file()


def test_release_with_the_placeholder_address_is_refused_and_leaves_no_zip(tmp_path, isolated_git, monkeypatch):
    monkeypatch.delenv(wydanie.TEST_ENV, raising=False)
    repo = repo_with_address(tmp_path, PLACEHOLDER_REPO)
    out = tmp_path / "trial-reels.zip"
    with pytest.raises(ValueError, match="config.py") as caught:
        wydanie.build(repo, out)
    assert PLACEHOLDER_REPO in str(caught.value) and wydanie.TEST_ENV in str(caught.value)
    assert not out.exists()


def test_release_with_the_placeholder_only_in_the_readme_is_refused(tmp_path, isolated_git):
    repo = repo_with_address(tmp_path, EXAMPLE_REPO, readme_slug=PLACEHOLDER_REPO)
    with pytest.raises(ValueError, match="README.md"):
        wydanie.build(repo, tmp_path / "trial-reels.zip")
    assert not (tmp_path / "trial-reels.zip").exists()


def test_release_whose_readme_points_to_another_repo_is_refused(tmp_path, isolated_git):
    repo = repo_with_address(tmp_path, EXAMPLE_REPO, readme_slug="inna-org/trial-reels")
    with pytest.raises(ValueError, match="README.md"):
        wydanie.build(repo, tmp_path / "trial-reels.zip")


def test_local_installation_test_may_build_with_the_placeholder(tmp_path, isolated_git, monkeypatch):
    monkeypatch.setenv(wydanie.TEST_ENV, "1")
    repo = repo_with_address(tmp_path, PLACEHOLDER_REPO)
    assert wydanie.build(repo, tmp_path / "trial-reels.zip").is_file()


def test_release_from_github_needs_the_address_of_the_repository_it_comes_from(tmp_path, isolated_git, monkeypatch):
    """W CI `--repo` to $GITHUB_REPOSITORY: wydanie z innym REPO_SLUG kierowałoby aktualizacje gdzie indziej."""
    repo = repo_with_address(tmp_path, EXAMPLE_REPO)
    assert wydanie.build(repo, tmp_path / "a.zip", repo=EXAMPLE_REPO).is_file()
    assert wydanie.build(repo, tmp_path / "b.zip", repo="Przyklad-Org/Trial-Reels").is_file()   # GitHub nie patrzy na wielkość liter
    out = tmp_path / "c.zip"
    with pytest.raises(ValueError, match="różni się") as caught:
        wydanie.build(repo, out, repo="inna-org/trial-reels")
    assert "inna-org/trial-reels" in str(caught.value) and not out.exists()
    monkeypatch.setenv(wydanie.TEST_ENV, "1")                    # zmienna testowa nie zwalnia z tego sprawdzenia
    placeholder = repo_with_address(tmp_path, PLACEHOLDER_REPO, name="repo-zastepczy")
    with pytest.raises(ValueError, match="różni się"):
        wydanie.build(placeholder, tmp_path / "d.zip", repo=EXAMPLE_REPO)


def test_release_from_github_without_the_config_file_is_refused(tmp_path, release_repo):
    with pytest.raises(ValueError, match="config.py"):
        wydanie.build(release_repo, tmp_path / "trial-reels.zip", repo=EXAMPLE_REPO)


def test_cli_passes_the_repository_and_reports_a_mismatch_in_one_line(tmp_path, isolated_git, capsys):
    repo = repo_with_address(tmp_path, EXAMPLE_REPO)
    out = tmp_path / "trial-reels.zip"
    assert wydanie.main([str(out), "--repo", "inna-org/trial-reels"], root=repo) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len([line for line in captured.err.splitlines() if line.strip()]) == 1
    assert not out.exists()
    assert wydanie.main([str(out), "--repo", EXAMPLE_REPO], root=repo) == 0 and out.is_file()


# --- wiersz poleceń -------------------------------------------------------------

def test_cli_builds_the_zip_and_reports_it(tmp_path, release_repo, capsys):
    out = tmp_path / "trial-reels.zip"
    assert wydanie.main([str(out)], root=release_repo) == 0
    printed = capsys.readouterr().out
    assert str(out) in printed and out.is_file()


def test_cli_failure_is_one_plain_line_with_code_1(tmp_path, isolated_git, capsys):
    folder = tmp_path / "nie-repo"
    folder.mkdir()
    assert wydanie.main([str(tmp_path / "trial-reels.zip")], root=folder) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "Traceback" not in captured.err
    assert len([line for line in captured.err.splitlines() if line.strip()]) == 1


def test_script_run_from_the_tools_folder_uses_the_folder_above_it(tmp_path, release_repo):
    """Tak woła je CI: `python tools/wydanie.py OUT.zip`, a korzeniem jest folder nad `tools/`."""
    shutil.copy(CODE / "tools" / "wydanie.py", release_repo / "tools" / "wydanie.py")
    out = tmp_path / "z-ci" / "trial-reels.zip"
    done = subprocess.run([sys.executable, str(release_repo / "tools" / "wydanie.py"), str(out)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert done.returncode == 0, done.stderr
    assert out.is_file() and "tools/wydanie.py" not in names_of(out)   # w wydaniu narzędzi nie ma


# --- wydanie i aktualizacja grają razem -----------------------------------------

def test_update_applies_a_built_release_and_drops_what_the_release_dropped(tmp_path, release_repo):
    client = tmp_path / "klient"
    first = wydanie.build(release_repo, tmp_path / "v1.zip")
    update.apply(first, client)
    write(client, "dane/pula.json", "[1]")
    write(client, "wlasny-plik.txt", "klienta")
    assert (client / "trial_reels" / "__main__.py").is_file()

    git(release_repo, "rm", "-q", "trial_reels/__main__.py")
    write(release_repo, "VERSION", "0.2.0\n")
    write(release_repo, "trial_reels/nowy.py", "# nowy\n")
    commit_all(release_repo, "drugie")
    result = update.apply(wydanie.build(release_repo, tmp_path / "v2.zip"), client)

    assert result["usuniete"] == ["trial_reels/__main__.py"] and result["wymagania"] is False
    assert not (client / "trial_reels" / "__main__.py").exists()
    assert (client / "trial_reels" / "nowy.py").is_file() and (client / "VERSION").read_text(encoding="utf-8") == "0.2.0\n"
    assert (client / "dane" / "pula.json").read_text(encoding="utf-8") == "[1]"
    assert (client / "wlasny-plik.txt").read_text(encoding="utf-8") == "klienta"
    listed = (client / "PLIKI.txt").read_text(encoding="utf-8").splitlines()
    assert "trial_reels/nowy.py" in listed and "trial_reels/__main__.py" not in listed
