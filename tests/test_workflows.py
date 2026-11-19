"""Testy plików GitHub Actions: pilnują tego, czego nie widać bez uruchomienia ich na GitHubie."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ("testy.yml", "wydanie.yml")
PINNED = re.compile(r"^\s*(?:- )?uses: ([\w.-]+/[\w.-]+)@([0-9a-f]{40}) # v\d+\.\d+\.\d+\s*$")


def read(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def jobs(text: str) -> dict:
    """Joby workflow jako {nazwa: treść} (joby stoją pod `jobs:` z wcięciem 2 spacji)."""
    found, name = {}, None
    for line in text.split("\njobs:\n", 1)[1].splitlines():
        head = re.match(r"^  ([\w-]+):\s*$", line)
        if head:
            name = head.group(1)
            found[name] = ""
        elif name is not None:
            found[name] += line + "\n"
    return found


def step_script(text: str, name_start: str) -> str:
    """Skrypt z `run: |` kroku, którego nazwa zaczyna się od `name_start` (bez wcięcia)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith("- name: " + name_start))
    run = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run + 1]) - len(lines[run + 1].lstrip())
    body = []
    for line in lines[run + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body).strip() + "\n"


def test_tests_can_be_started_by_hand_and_then_macos_runs_even_on_a_private_repo():
    """Na prywatnym repo job macOS przy pushu się pomija (minuty liczą się razy 10), ale ręczne uruchomienie go liczy."""
    text = read("testy.yml")
    triggers = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert re.search(r"^  workflow_dispatch:\s*$", triggers, re.M) and re.search(r"^  workflow_call:\s*$", triggers, re.M)
    macos = text.split("\n  macos:\n", 1)[1]
    assert re.search(r"^    if: github\.event\.repository\.private == false \|\| github\.event_name == 'workflow_dispatch'\s*$",
                     macos, re.M)
    windows = text.split("\n  windows:\n", 1)[1].split("\n  # Na prywatnym", 1)[0]
    assert "\n    if:" not in windows                                        # Windows liczy się zawsze


def test_the_release_workflow_still_gets_the_same_tests_from_a_tag():
    release = read("wydanie.yml")
    assert "uses: ./.github/workflows/testy.yml" in release and "needs: testy" in release


def test_the_release_zip_is_built_for_the_repository_it_is_published_from():
    """K1: wydanie przerywa się, gdy REPO_SLUG w programie różni się od repozytorium, z którego idzie wydanie."""
    release = read("wydanie.yml")
    assert re.search(r'tools/wydanie\.py dist/trial-reels\.zip --repo "\$GITHUB_REPOSITORY"', release)


# --- W1, W2, W4: akcje przypięte skrótem, zapis tylko z akcjami GitHuba, tag z main ------------------------------

def test_every_action_is_pinned_to_a_full_commit_hash_with_its_version_in_a_comment():
    """Tag w cudzym repo akcji da się przestawić na inny kod, a pełnego skrótu commita nie."""
    checked = 0
    for name in WORKFLOWS:
        for line in read(name).splitlines():
            if "uses:" in line and "./.github/workflows/" not in line:
                assert PINNED.match(line), "%s: %s" % (name, line.strip())
                checked += 1
    assert checked >= 6


def test_jobs_that_can_write_use_only_github_actions_and_run_no_code_from_the_repo():
    writers = 0
    for name in WORKFLOWS:
        for job, body in jobs(read(name)).items():
            if "contents: write" not in body:
                continue
            writers += 1
            actions = re.findall(r"uses: ([^@\s]+)@", body)
            assert actions and all(action.startswith("actions/") for action in actions), (name, job, actions)
            assert "actions/checkout" not in actions, (name, job)               # kodu z repo w tym jobie nie ma
            assert "python" not in body and "tools/" not in body and "uv " not in body, (name, job)
    assert writers == 1


def test_the_release_is_built_in_a_read_only_job_and_handed_over_as_an_artifact():
    text = read("wydanie.yml")
    assert re.search(r"^permissions:\n  contents: read$", text.split("\njobs:", 1)[0], re.M)
    found = jobs(text)
    assert set(found) == {"testy", "paczka", "wydanie"}
    pack, publish = found["paczka"], found["wydanie"]
    assert "needs: testy" in pack and "contents: read" in pack and "contents: write" not in pack
    for needed in ("actions/checkout@", "tools/straznik.py --historia", "tools/wydanie.py", "tools/notatki.py",
                   "actions/upload-artifact@", "if-no-files-found: error"):
        assert needed in pack, needed
    assert "needs: paczka" in publish and "actions/download-artifact@" in publish and "gh release create" in publish
    assert "--verify-tag" in publish and "secrets.GITHUB_TOKEN" in publish
    assert "secrets." not in pack


def test_workflows_never_print_who_pushed_or_made_the_commit():
    """W4: konto, które wypycha zmiany, i tak widać w zakładce Actions; workflowy nie dopisują go nigdzie więcej."""
    personal = re.compile(r"github\.(?:triggering_)?actor|GITHUB_(?:TRIGGERING_)?ACTOR|event\.(?:sender|pusher|head_commit)"
                          r"|\.(?:author|committer)\b", re.I)
    for name in WORKFLOWS:
        assert not personal.search(read(name)), name


def git_in(repo, *args):
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="krok workflow to skrypt basha")
def test_release_runs_only_for_a_tag_that_is_v_plus_version_on_a_commit_from_main(tmp_path, monkeypatch):
    """R29: wydanie rusza tylko, gdy tag to „v” + VERSION, a commit tagu jest na main (jak po checkout z fetch-depth 0)."""
    empty = tmp_path / "pusta-konfiguracja-gita"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    git_in(repo, "init", "-q", "-b", "main")
    git_in(repo, "config", "user.name", "Trial Reels")
    git_in(repo, "config", "user.email", "trial-reels@users.noreply.github.com")

    def version_commit(number):
        (repo / "VERSION").write_text(number + "\n", encoding="utf-8")
        git_in(repo, "add", "VERSION")
        git_in(repo, "commit", "-q", "--no-verify", "-m", "wersja " + number)
        return git_in(repo, "rev-parse", "HEAD")

    first = version_commit("0.1.0")
    second = version_commit("0.2.0")
    git_in(repo, "checkout", "-q", "-b", "boczna", first)
    side = version_commit("0.3.0")
    git_in(repo, "update-ref", "refs/remotes/origin/main", second)    # tak checkout z fetch-depth 0 zapisuje main
    git_in(repo, "tag", "v0.1.0", first)
    git_in(repo, "tag", "-a", "v0.2.0", "-m", "wydanie", second)       # tag z opisem też wskazuje commit
    git_in(repo, "tag", "v0.3.0", side)
    git_in(repo, "tag", "v9.9.9", second)
    git_in(repo, "tag", "v0.2", second)
    script = tmp_path / "krok.sh"
    script.write_text(step_script(read("wydanie.yml"), "Tag"), encoding="utf-8")

    def run(tag):
        git_in(repo, "checkout", "-q", "--detach", tag)
        env = {**os.environ, "GITHUB_REF_NAME": tag, "GITHUB_REF": "refs/tags/" + tag}
        done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)], cwd=repo, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        return done.returncode, done.stderr

    assert run("v0.2.0") == (0, "")
    assert run("v0.1.0") == (0, "")                                     # starszy commit z main też jest na main
    code, err = run("v0.3.0")
    assert code == 1 and "main" in err
    code, err = run("v9.9.9")
    assert code == 1 and "VERSION" in err
    code, err = run("v0.2")
    assert code == 1 and "vX.Y.Z" in err


def test_every_push_checks_the_whole_history_with_the_guard():
    """D10: autorzy, committerzy i strefy dat całej historii są sprawdzane przy każdym pushu, nie dopiero przy wydaniu."""
    found = jobs(read("testy.yml"))
    history = found["historia"]
    assert re.search(r"^    if: github\.event_name == 'push'\s*$", history, re.M)
    assert "fetch-depth: 0" in history and "python3 tools/straznik.py --historia" in history
    assert "tools/straznik.py --historia" not in found["windows"] + found["macos"]


def test_windows_checks_that_trial_cmd_passes_on_the_exit_code_of_the_program():
    """D7: Python i `exit /b` stoją w jednej linii trial.cmd; na Windowsie sprawdzamy, że kod wyjścia programu przechodzi."""
    windows = jobs(read("testy.yml"))["windows"]
    step = windows.split("- name: trial.cmd przekazuje kod wyjścia programu", 1)[1].split("\n      - name:", 1)[0]
    assert ".\\trial.cmd nieistniejaca-komenda" in step and "$LASTEXITCODE -ne 2" in step and "exit 0" in step
