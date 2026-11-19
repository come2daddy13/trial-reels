"""Testy tekstów dla klienta: CLAUDE.md, skill, kroki kreatora, README, ZMIANY.md i zgody w .claude/settings.json.

Teksty czyta Claude klienta, który prowadzi osobę nietechniczną, więc te testy pilnują rzeczy, które psują prowadzenie
po cichu: brakujących nagłówków kroków, komend, których program nie zna, przykładów, których sam program by nie przyjął,
i zgód w settings.json, które nie pasują do komend z tekstów.
"""
import argparse
import inspect
import json
import re
import shlex
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

from trial_reels import __main__ as cli
from trial_reels import candidates, captions, config, doctor, render, versions, wizard

ROOT = Path(__file__).resolve().parents[1]
START_HOOKS = 5     # tyle hooków na rolkę piszemy na start (program wymaga co najmniej candidates.MIN_HOOKS)
SKILL = ROOT / ".claude" / "skills" / "trial-reels"
CLIENT_TEXTS = [
    ROOT / "CLAUDE.md", ROOT / "README.md", ROOT / "ZMIANY.md",
    SKILL / "SKILL.md", SKILL / "DLACZEGO.md", SKILL / "PULAPKI.md",
    *sorted((SKILL / "kroki").glob("*.md")),
]
HEADINGS = ("## Co robimy", "## Po co", "## Co robisz Ty", "## Co robię ja", "## Jak sprawdzamy", "## Gdy nie wychodzi")
BASH, POWERSHELL = "bash trial.sh", ".\\trial.cmd"
COMMAND = re.compile(r"(?P<shell>bash trial\.sh|\.\\trial\.cmd)(?: (?P<rest>[^`\n]*))?")
PLACEHOLDER = re.compile(r"[<>\[\]|…]")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def step_file(i: int, step_id: str) -> Path:
    return SKILL / "kroki" / ("%02d-%s.md" % (i, step_id))


def fenced_blocks(text: str) -> list:
    """Bloki kodu z tekstu jako lista (język, treść)."""
    blocks, buf, lang, inside = [], [], "", False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if inside:
                blocks.append((lang, "\n".join(buf)))
                buf, inside = [], False
            else:
                lang, inside = stripped[3:].strip(), True
            continue
        if inside:
            buf.append(line)
    return blocks


def outside_fences(text: str) -> list:
    """Linie tekstu poza blokami kodu."""
    lines, inside = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return lines


def headings(text: str) -> list:
    return [line for line in outside_fences(text) if re.match(r"#{1,6} ", line)]


def frontmatter(text: str) -> tuple:
    lines = text.splitlines()
    assert lines and lines[0] == "---", "SKILL.md musi zaczynać się od ---"
    end = lines.index("---", 1)
    data = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        assert sep, "linia frontmattera bez dwukropka: %r" % line
        data[key.strip()] = value.strip()
    return data, "\n".join(lines[end + 1:])


def commands_in(text: str) -> list:
    """Wszystkie wywołania `bash trial.sh …` i `.\\trial.cmd …` w tekście jako lista (powłoka, reszta komendy)."""
    return [(m.group("shell"), (m.group("rest") or "").strip()) for m in COMMAND.finditer(text)]


def subcommands() -> set:
    for action in cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("parser nie ma podkomend")


# --- kroki kreatora -------------------------------------------------------------

def test_every_wizard_step_has_a_step_file_with_six_headings():
    for i, (sid, _) in enumerate(wizard.STEPS):
        txt = read(step_file(i, sid))
        assert all(h in txt for h in HEADINGS), sid


def test_step_files_have_exactly_the_six_headings_in_order():
    for i, (sid, _) in enumerate(wizard.STEPS):
        assert headings(read(step_file(i, sid))) == list(HEADINGS), sid


def test_step_files_are_exactly_the_wizard_steps():
    expected = sorted("%02d-%s.md" % (i, sid) for i, (sid, _) in enumerate(wizard.STEPS))
    assert sorted(p.name for p in (SKILL / "kroki").iterdir()) == expected


def test_every_section_of_a_step_has_content():
    for i, (sid, _) in enumerate(wizard.STEPS):
        text = read(step_file(i, sid))
        for heading, body in zip(HEADINGS, re.split(r"^## .*$", text, flags=re.M)[1:]):
            assert len(body.split()) >= 8, "%s: pusta sekcja %s" % (sid, heading)


def test_step_file_starts_with_its_own_number_and_title():
    for i, (sid, title) in enumerate(wizard.STEPS):
        first = next(line for line in read(step_file(i, sid)).splitlines() if line.strip())
        assert first == "**Krok %d: %s**" % (i, title), sid


def test_entry_steps_are_marked_in_their_step_files():
    for i, (sid, _) in enumerate(wizard.STEPS):
        text = read(step_file(i, sid))
        if sid in wizard.ENTRY_STEPS:
            assert "krok --gotowe %s" % sid in text, sid
        else:
            assert "krok --gotowe %s" % sid not in text, "krok liczony z plików nie ma zapisu: %s" % sid
    measure = read(step_file(9, "pomiar"))
    assert "--wartosc chrome" in measure and "--wartosc reczny" in measure


def test_step_files_explain_installation_and_key_flow():
    programs = read(step_file(1, "programy"))
    assert "uv --version" in programs
    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" in programs
    assert 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"' in programs
    assert "uv venv --python 3.12 .venv" in programs
    assert "uv pip install --python .venv -r requirements.txt" in programs
    zernio = read(step_file(2, "zernio"))
    assert "ZERNIO_API_KEY=" in zernio
    assert "bash trial.sh klucz" in zernio and ".\\trial.cmd klucz" in zernio
    assert "nigdy" in zernio.lower() and "czat" in zernio.lower()


def test_weekly_prompt_has_the_agreed_order_and_rules():
    text = read(step_file(10, "tydzien"))
    prompts = [body for _, body in fenced_blocks(text) if "Kroki:" in body]
    assert len(prompts) == 1, "10-tydzien.md ma mieć jeden gotowy prompt (blok z linią „Kroki:”)"
    prompt = prompts[0]
    markers = ["`sprawdz`", "`aktualizuj --sprawdz`", "`do-odczytu --probka`", "`js-odczyt`", "`zapisz-wynik",
               "`paczka --dni 7`", "`raport`"]
    positions = [prompt.find(m) for m in markers]
    assert all(p >= 0 for p in positions), dict(zip(markers, positions))
    assert positions == sorted(positions)
    for rule in ("nie loguj", "dane/.env", "okna publikacji", "nie aktualizuj"):
        assert rule in prompt.lower(), rule
    assert "niedziel" in text and "18:00" in text and "zawsze zezwalaj" in text


# --- komendy w tekstach ---------------------------------------------------------

def test_texts_never_send_client_to_terminal():
    for p in CLIENT_TEXTS:
        assert not re.search(r"wpisz w terminal|otwórz terminal", read(p), re.I), p.name


def test_commands_in_texts_come_in_both_shells():
    for p in CLIENT_TEXTS:
        found = commands_in(read(p))
        bash = {rest for shell, rest in found if shell == BASH}
        power = {rest for shell, rest in found if shell == POWERSHELL}
        assert bash == power, "%s: komendy bez pary w drugiej powłoce: %s" % (p.name, sorted(bash ^ power))


def test_commands_in_texts_are_accepted_by_the_real_parser():
    checked = 0
    for p in CLIENT_TEXTS:
        for shell, rest in commands_in(read(p)):
            if not rest or PLACEHOLDER.search(rest):
                continue
            try:
                cli.build_parser().parse_args(shlex.split(rest))
            except SystemExit:
                pytest.fail("%s: program nie przyjmie komendy „%s %s”" % (p.name, shell, rest))
            checked += 1
    assert checked > 40, "za mało komend w tekstach do sprawdzenia: %d" % checked


def test_skill_command_map_lists_exactly_the_commands_of_the_program():
    section = read(SKILL / "SKILL.md").split("## Mapa komend", 1)[1].split("\n## ", 1)[0]
    listed = {m.group(1) for m in (re.match(r"\| `([^`]+)` \|", row) for row in section.splitlines()) if m}
    assert listed == subcommands(), "mapa komend w SKILL.md różni się od programu: %s" % sorted(listed ^ subcommands())


def test_krok_gotowe_in_texts_only_for_known_steps():
    for p in CLIENT_TEXTS:
        for _, rest in commands_in(read(p)):
            found = re.match(r"krok --gotowe (\w+)", rest)
            if found:
                assert found.group(1) in wizard.ENTRY_STEPS, "%s: %s" % (p.name, rest)


def test_every_referenced_skill_file_exists():
    pattern = re.compile(r"(?:\.claude/skills/trial-reels/)?(kroki/\d\d-[a-z]+\.md|DLACZEGO\.md|PULAPKI\.md|SKILL\.md)")
    seen = 0
    for p in CLIENT_TEXTS:
        for match in pattern.finditer(read(p)):
            assert (SKILL / match.group(1)).is_file(), "%s: brak pliku %s" % (p.name, match.group(1))
            seen += 1
    assert seen >= 10


# --- README, SKILL, ustawienia --------------------------------------------------

def test_readme_has_both_bootstrap_variants():
    t = read(ROOT / "README.md")
    assert "unzip -o trial-reels.zip" in t and "tar -xf trial-reels.zip" in t


def test_readme_structure():
    t = read(ROOT / "README.md")
    url = "https://github.com/%s" % config.REPO_SLUG
    sentence = "Zainstaluj trial reels z %s i poprowadź mnie krok po kroku" % url
    assert sentence in t
    assert t.index(sentence) < t.index("## Część dla Claude"), "3 kroki dla klienta mają być przed częścią dla Claude"
    assert "curl -fL -o trial-reels.zip %s/releases/latest/download/trial-reels.zip" % url in t
    assert "curl.exe -fL -o trial-reels.zip %s/releases/latest/download/trial-reels.zip" % url in t
    assert t.rstrip().splitlines()[-1] == "Wszelkie prawa zastrzeżone."


def test_github_links_use_the_repo_slug_and_never_ssh():
    ssh_host = "git" + chr(64) + "github.com"   # złożone z części, żeby strażnik nie wziął samego testu za adres e-mail
    for p in CLIENT_TEXTS:
        text = read(p)
        assert ssh_host not in text, p.name
        for link in re.findall(r"https://github\.com/[^\s`)\"']+", text):
            assert link.startswith("https://github.com/%s" % config.REPO_SLUG), "%s: %s" % (p.name, link)


def test_skill_frontmatter():
    data, body = frontmatter(read(SKILL / "SKILL.md"))
    assert set(data) == {"name", "description"}
    assert data["name"] == "trial-reels" == SKILL.name
    description = data["description"]
    assert ": " not in description and " #" not in description, "dwukropek ze spacją psuje frontmatter (YAML)"
    assert description[0] not in "\"'[{&*!|>%@`", description
    for word in ("trial reels", "próbne rolki", "konfiguracja", "paczka", "wyniki", "aktualizacja"):
        assert word in description.lower(), word
    assert body.strip().startswith("# ")


def test_settings_json_valid():
    path = ROOT / ".claude" / "settings.json"
    data = json.loads(read(path))
    assert set(data) == {"permissions"}
    permissions = data["permissions"]
    assert set(permissions) <= {"allow", "ask", "deny"}
    allow, ask = permissions["allow"], permissions.get("ask", [])
    assert "Bash(bash trial.sh *)" in allow
    assert "PowerShell(.\\trial.cmd *)" in allow
    for rule in allow + ask:
        assert re.fullmatch(r"(Bash|PowerShell)\(.+ \*\)", rule), rule
    for rule in allow:    # zgoda obejmuje tylko wejścia do programu, nic szerszego
        assert rule.startswith(("Bash(bash trial.sh ", "PowerShell(.\\trial.cmd ")), rule
    # aktualizacja zawsze pyta (reguła ask wygrywa z allow), bo zgodę klienta ma dać on, a nie samo „zezwól na komendę”
    assert "Bash(bash trial.sh aktualizuj --tak *)" in ask
    assert "PowerShell(.\\trial.cmd aktualizuj --tak *)" in ask
    assert (ROOT / "trial.sh").is_file() and (ROOT / "trial.cmd").is_file()
    # W3: narzędzia do plików nie dostaną klucza (wzorzec „/…” liczy się od folderu projektu, czyli folderu klienta)
    assert permissions["deny"] == ["Read(/dane/.env*)", "Edit(/dane/.env*)"]


def _anchored(pattern: str, path: str) -> bool:
    """Ścieżka względem folderu projektu pasuje do wzorca „/…” z reguły Read albo Edit (gitignore: `*` w segmencie)."""
    assert pattern.startswith("/") and "**" not in pattern
    return re.fullmatch("".join("[^/]*" if ch == "*" else re.escape(ch) for ch in pattern[1:]), path) is not None


def test_deny_rules_block_only_the_key_file_and_leave_the_program_commands_alone():
    """Zakaz obejmuje dane/.env i dane/.env.txt (Notatnik), ale ani programu, ani innych danych, ani komendy klucz."""
    import fnmatch

    permissions = json.loads(read(ROOT / ".claude" / "settings.json"))["permissions"]
    patterns = [re.fullmatch(r"(?:Read|Edit)\((/.+)\)", rule).group(1) for rule in permissions["deny"]]
    for path in ("dane/.env", "dane/.env.txt"):
        assert all(_anchored(pattern, path) for pattern in patterns), path
    for path in ("trial.sh", "trial.cmd", "CLAUDE.md", "dane/config.json", "dane/pula.json", "dane/hooki.json",
                 "dane/stan.json", "dane/kreator.json", "dane/wersje/kadr_Cabc123XYZ_.jpg", "dane/podglad.html"):
        assert not any(_anchored(pattern, path) for pattern in patterns), path

    def matches(rule, command):
        inner = re.fullmatch(r"(?:Bash|PowerShell)\((.+)\)", rule)
        return bool(inner) and fnmatch.fnmatchcase(command, inner.group(1))

    for command in ("bash trial.sh klucz", ".\\trial.cmd klucz"):
        assert any(matches(rule, command) for rule in permissions["allow"]), command
        assert not any(matches(rule, command) for rule in permissions["ask"] + permissions["deny"]), command


def test_safety_rules_are_in_both_claude_md_and_skill():
    required = (r"7:15.{1,4}22:00", r"MANUAL", r"pierwsz\w+ 9 wersji", r"dane/\.env", r"nie loguj się za klienta",
                r"nie (proś|prosisz) o hasł", r"klucz\w* (nie|nigdy)", r"obietnic")
    for path in (ROOT / "CLAUDE.md", SKILL / "SKILL.md"):
        text = read(path)
        for pattern in required:
            assert re.search(pattern, text, re.I), "%s: brak zasady %s" % (path.name, pattern)


def test_claude_md_allows_aktualizuj_tak_only_after_consent_given_in_this_conversation():
    """D1: reguła ask w settings.json to nie twarda granica (inny zapis komendy może jej nie dopasować), więc zgodą
    na aktualizację jest wyraźne „tak” klienta w rozmowie, a nie samo okno zgody aplikacji."""
    rule = next(line for line in read(ROOT / "CLAUDE.md").splitlines() if line.startswith("7. "))
    assert "`aktualizuj --tak`" in rule and "tylko po wyraźnej zgodzie klienta w tej rozmowie" in rule


def test_texts_keep_cmd_special_characters_out_of_powershell_arguments():
    """D2: w PowerShellu argumenty `.\\trial.cmd` czyta jeszcze raz cmd.exe, więc teksty z & | ^ < > % idą przez pliki."""
    for path in (ROOT / "CLAUDE.md", SKILL / "SKILL.md"):
        text = read(path)
        assert "cmd.exe" in text and "& | ^ < > %" in text and "`--hook-id`" in text and "sam kod" in text, path.name
    row = next(line for line in read(SKILL / "SKILL.md").splitlines() if line.startswith("| `kadr` |"))
    assert "--hook-id ID" in row
    assert "--hook-id h01" in read(step_file(6, "ustawienia"))
    assert cli.build_parser().parse_args(["kadr", "Cabc123XYZ_", "--hook-id", "h01"]).hook_id == "h01"


def test_trial_cmd_runs_python_and_leaves_in_the_same_line():
    """D7: cmd.exe czyta plik wsadowy linia po linii, od zapamiętanego miejsca. Aktualizacja, która podmieni trial.cmd
    w trakcie działania, nie może dać mu do wykonania reszty nowego pliku, więc wyjście stoi w linii z Pythonem."""
    lines = (ROOT / "trial.cmd").read_bytes().decode("ascii").splitlines()
    assert [line for line in lines if "-m trial_reels" in line] == ['".venv\\Scripts\\python.exe" -m trial_reels %* & exit /b']
    assert not any("ERRORLEVEL" in line for line in lines)        # %ERRORLEVEL% w tej linii rozwinąłby się za wcześnie


def test_pitfalls_say_how_to_recover_from_an_update_cut_off_midway():
    pitfalls = read(SKILL / "PULAPKI.md")
    section = pitfalls.split("## Aktualizacja przerwana w połowie", 1)[1].split("\n## ", 1)[0]
    for needed in ("zip", "README.md", "`dane/`", "`.venv`", "`doktor`", "zgod"):
        assert needed in section, needed
    update = read(SKILL / "SKILL.md").split("## Aktualizacja", 1)[1].split("\n## ", 1)[0]
    assert "PULAPKI.md" in update


def test_claude_md_rule_first_krok_and_missing_venv():
    text = read(ROOT / "CLAUDE.md")
    assert "najpierw `krok`" in text.lower()
    assert ".venv" in text and "00-powitanie.md" in text
    assert BASH in text and POWERSHELL in text


# --- zgodność tekstów z programem -----------------------------------------------

def test_limits_in_texts_match_the_code():
    skill = read(SKILL / "SKILL.md")
    assert re.search(r"%d znaków" % candidates.HOOK_MAX, skill)
    assert str(candidates.CAPTION_MAX) in skill
    assert re.search(r"co najmniej %d hooki" % candidates.MIN_HOOKS, skill)
    assert re.search(r"co najmniej %d dopiski" % candidates.MIN_EXTRAS, skill)
    why = read(SKILL / "DLACZEGO.md")
    assert "50/30/20" in why and config.LEVEL_MIX == {"subtelna": 0.5, "srednia": 0.3, "mocna": 0.2}
    assert "1000 wyświetleń" in why
    assert "%d%%" % round(config.BRAKE_DROP * 100) in why
    assert "14 dni" in why
    assert "%d wersji" % cli.FIRST_BATCH in why
    start, end = (h.lstrip("0") for h in config.DEFAULTS["day_window"])
    assert start in why and end in why


def test_emoji_list_in_skill_matches_the_bundle():
    skill = read(SKILL / "SKILL.md")
    listed = re.search(r"Dostępne emotki.*?:\s*(.+)", skill)
    assert listed, "SKILL.md ma wymieniać dostępne emotki (linia „Dostępne emotki …: …”)"
    assert set(listed.group(1).split()) == set(render.emoji_set())


def test_texts_have_no_variation_selector_or_em_dash():
    for p in CLIENT_TEXTS:
        text = read(p)
        assert "️" not in text, "%s: niewidoczny znak U+FE0F skopiowany do hooka zepsułby sprawdzanie puli" % p.name
        assert "—" not in text, "%s: długi myślnik (dopiski i warianty CTA nie mogą go mieć)" % p.name


def test_texts_are_plain_utf8_with_unix_line_ends():
    for p in CLIENT_TEXTS:
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), p.name
        assert b"\r" not in raw, p.name
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), p.name


def test_texts_hold_no_local_paths_or_promises():
    promises = (r"zwiększy (twój )?zasięg", r"przyniesie (ci )?obserwujących", r"na pewno (zadziała|zwiększ)",
                r"gwarantowan")
    for p in CLIENT_TEXTS:
        text = read(p)
        assert "/Users/" not in text and "/home/" not in text, p.name
        for pattern in promises:
            assert not re.search(pattern, text, re.I), "%s: obietnica wyniku (%s)" % (p.name, pattern)


def test_zmiany_has_a_section_for_the_current_version_on_top():
    """Aktualizacja pokazuje klientowi sekcję `## X.Y.Z` z tego pliku, więc musi być dla każdego wydania i być na górze."""
    version = read(ROOT / "VERSION").strip()
    text = read(ROOT / "ZMIANY.md")
    sections = re.findall(r"^## (\S+)$", text, re.M)
    assert sections[0] == version, "najnowsza wersja ma być pierwsza w ZMIANY.md"
    assert "0.1.0" in sections
    first_release = re.split(r"^## ", text, flags=re.M)[sections.index("0.1.0") + 1]
    assert len(first_release.split()) > 40


# --- przykłady w tekstach przechodzą przez prawdziwy walidator ------------------

def json_blocks(path: Path) -> list:
    return [json.loads(body) for lang, body in fenced_blocks(read(path)) if lang == "json"]


def test_every_json_example_is_valid_json():
    count = 0
    for p in CLIENT_TEXTS:
        count += len(json_blocks(p))
    assert count >= 3


def test_documented_pool_and_hook_examples_pass_the_real_validator(put_reel_files):
    blocks = json_blocks(SKILL / "SKILL.md")
    pool = next(b for b in blocks if isinstance(b, dict) and "cta" in b)
    hooks = next(b for b in blocks if isinstance(b, dict) and pool["code"] in b)
    put_reel_files(pool["code"])
    assert candidates.validate([pool], hooks) == []
    assert candidates.valid_code(pool["code"])
    assert len(hooks[pool["code"]]) == START_HOOKS, "przykład ma pokazywać bank na start: %d hooków" % START_HOOKS
    for blur in pool["blur"]:
        assert blur["t"][0] < blur["t"][1] and len(blur["box"]) == 4 and all(0 <= v <= 1 for v in blur["box"])
    assert 0 <= pool["mask"]["y"] <= 1 and 0 <= pool["hook_y"] <= 1


def test_documented_config_example_matches_the_defaults():
    blocks = json_blocks(SKILL / "SKILL.md")
    example = next(b for b in blocks if isinstance(b, dict) and "timezone" in b)
    assert example == {key: config.DEFAULTS[key] for key in example}
    assert set(example) == {"timezone", "day_window", "hours", "daily_max", "brake_slot"}


# --- ustalenia z testu instalacji: jedna reguła w każdym miejscu ------------------

ENV_RULE_TEXTS = (ROOT / "CLAUDE.md", SKILL / "SKILL.md", SKILL / "kroki" / "02-zernio.md",
                  SKILL / "kroki" / "10-tydzien.md")


def test_env_rule_is_the_same_everywhere():
    """Claude nigdy nie czyta ani nie wypisuje dane/.env: plik tworzy i otwiera klientowi w edytorze komenda klucz,
    a to, czy klucz jest, Claude sprawdza wyłącznie komendą krok."""
    for path in ENV_RULE_TEXTS:
        text = read(path)
        assert "nie otwieraj" not in text.lower(), "%s: „nie otwieraj” kłóci się z otwieraniem pliku klientowi" % path.name
        assert re.search(r"\bcat\b[^.]*\btype\b[^.]*\bGet-Content\b", text), "%s: reguła nie nazywa zakazanych komend" % path.name
    for path in ENV_RULE_TEXTS[:2]:
        text = read(path)
        assert "narzędzia do czytania plików" in text and "wyłącznie komendą `krok`" in text, path.name
        assert "komenda `klucz`" in text and "`.claude/settings.json`" in text, path.name
    steps = read(step_file(2, "zernio"))
    assert "wyłącznie komendą `krok`" in steps and "Nie czytam treści pliku" in steps
    assert "nie czytaj i nie wypisuj" not in read(step_file(10, "tydzien")).lower().replace("nigdy nie czytaj ani nie wypisuj", "")


def test_texts_never_create_open_move_or_delete_the_key_file_by_hand():
    """W3: plik z kluczem tworzy, otwiera i (po Notatniku) przenosi tylko komenda klucz, a Claude go nie dotyka."""
    by_hand = ("open -e dane/.env", "notepad dane\\.env", 'notepad "dane\\.env"', "rm dane/.env", "Remove-Item dane\\.env",
               "mv dane/.env.txt", "Move-Item dane\\.env.txt", "ls -a dane", "Get-ChildItem -Force dane")
    for path in CLIENT_TEXTS:
        text = read(path)
        for command in by_hand:
            assert command not in text, "%s: %s" % (path.name, command)
    rules = read(ROOT / "CLAUDE.md")
    rule = next(line for line in rules.splitlines() if line.startswith("9. "))
    assert "bez zgody klienta" in rule and "wyjątek" not in rule.lower() and "komenda `klucz`" in rule
    step = read(step_file(2, "zernio"))
    assert ".env.txt" in step and "Uruchom `klucz` jeszcze raz" in step
    row = next(line for line in read(SKILL / "SKILL.md").splitlines() if line.startswith("| `klucz` |"))
    assert ".env.txt" in row and "600" in row and "nigdy nie pokazuje" in row


def test_consent_wording_for_accepting_and_scheduling_is_the_same_everywhere():
    for path in (ROOT / "CLAUDE.md", SKILL / "SKILL.md", step_file(8, "pierwsze")):
        text = read(path)
        assert "„akceptuję”" in text, path.name
        assert "wyraźnie powiedział" not in text, "%s: stare sformułowanie zgody" % path.name
    for path in (ROOT / "CLAUDE.md", SKILL / "SKILL.md"):
        text = read(path)
        assert "wyraźnie napisał „akceptuję”" in text and "osobnym „tak”" in text, path.name
        assert "`zaplanuj`" in text.split("osobnym „tak”")[0][-120:], path.name


def test_the_sentence_after_akceptuj_is_quoted_and_declared_not_to_be_consent(capsys):
    """Zdanie z komendy akceptuj czyta Claude klienta, więc teksty cytują je i mówią wprost, że to nie zgoda na planowanie."""
    config.write_json(config.STATE, {"seq": 1, "brake": {"on": False}, "versions": {
        "TR-001": {"id": "TR-001", "code": "Cabc123XYZ_", "status": "do_akceptacji", "slot": "2026-11-22T09:00:00"}}})
    assert cli.main(["akceptuj", "TR-001"]) == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("Zaakceptowane: TR-001. ")
    quote = line.split(". ", 1)[1].split(" (")[0]
    assert quote == "Następny krok to zaplanuj, ale dopiero po wyraźnej zgodzie klienta na pokazane terminy"
    for path in (ROOT / "CLAUDE.md", SKILL / "SKILL.md", step_file(8, "pierwsze")):
        text = read(path)
        assert quote in text, path.name
        assert "nie zgoda" in text or "niczego nie zastępuje" in text, path.name
    for path in CLIENT_TEXTS:
        assert "Teraz uruchom zaplanuj" not in read(path), path.name


def test_free_space_threshold_in_texts_is_the_one_the_doctor_checks():
    assert doctor.MIN_FREE_BYTES == 5 * 10**9
    for path in (ROOT / "README.md", step_file(0, "powitanie"), step_file(1, "programy")):
        assert "co najmniej 5 GB" in read(path), path.name
    for path in CLIENT_TEXTS:
        assert not re.search(r"(?<![\d,.])3 GB\b", read(path)), "%s: stary próg wolnego miejsca" % path.name
    assert "5 GB wolnego miejsca" in read(SKILL / "SKILL.md")


def test_doctor_description_in_texts_does_not_hard_code_the_number_of_checks(monkeypatch):
    """Liczba kontroli doktora rośnie z wersjami programu, więc teksty jej nie wpisują: każda kontrola to jedna linia."""
    names = []
    monkeypatch.setattr(doctor, "_run", lambda name, check: names.append(name) or {"nazwa": name, "ok": True, "info": ""})
    doctor.checks()
    programs, skill = read(step_file(1, "programy")), read(SKILL / "SKILL.md")
    assert "po jednej linii z ✓ na każdą kontrolę" in programs and "(kontroli doktora: N)" in programs
    assert "po jednej linii na każdą kontrolę" in skill
    assert not re.search(r"\b\d+ (linii z ✓|kontroli komputera)|kontroli doktora: \d", programs + skill)
    assert names[-1] == "Strefa czasowa" and "Strefa czasowa" in programs and "strefa czasowa" in skill


def test_exit_codes_in_skill_are_the_ones_the_program_and_the_scripts_use():
    line = next(l for l in read(SKILL / "SKILL.md").splitlines() if l.startswith("- Kody wyjścia:"))
    for code in ("0", "1", "2", "3", "130"):
        assert re.search(r"\b%s\b" % code, line), "brak kodu %s w opisie kodów wyjścia" % code
    assert "brak środowiska `.venv`" in line and "krok 1" in line and "błąd w nazwie albo opcji" in line
    assert "exit 3" in read(ROOT / "trial.sh") and "exit /b 3" in read(ROOT / "trial.cmd")
    with pytest.raises(SystemExit) as caught:
        cli.build_parser().parse_args(["nieistnieje"])
    assert caught.value.code == 2                                         # błąd składni to kod 2, nie tylko zła strefa


def test_texts_name_the_commands_that_work_with_damaged_settings_and_the_doctors_settings_row():
    free = {"wersja", "doktor", "krok", "aktualizuj"}
    assert cli.SETTINGS_FREE_COMMANDS == free
    skill, pitfalls, programs = read(SKILL / "SKILL.md"), read(SKILL / "PULAPKI.md"), read(step_file(1, "programy"))
    line = next(l for l in skill.splitlines() if l.startswith("- Kody wyjścia:"))
    zone = pitfalls.split("## Strefa czasowa i okno publikacji", 1)[1].split("\n## ", 1)[0]
    for name in free:
        assert "`%s`" % name in line and "`%s`" % name in zone and "`%s`" % name in programs, name
    row = "Ustawienia (dane/config.json)"
    assert row in [r["nazwa"] for r in doctor.checks()]
    for path in (SKILL / "SKILL.md", step_file(1, "programy"), SKILL / "PULAPKI.md"):
        assert row in read(path), path.name
    assert "Po każdej edycji `config.json` uruchom `doktor`" in skill


def test_damaged_settings_message_in_texts_is_the_programs_own():
    config.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    pitfalls = read(SKILL / "PULAPKI.md")
    for text, expected_start in (('{\n "a": 1\n "b": 2\n}', "Plik dane/config.json jest uszkodzony"),
                                 ("[]", "Plik dane/config.json ma zły układ")):
        config.SETTINGS.write_text(text, encoding="utf-8")
        with pytest.raises(config.UserError) as caught:
            config.settings()
        message = str(caught.value)
        assert message.startswith(expected_start)
        template = re.sub(r"linia \d+, kolumna \d+", "linia N, kolumna N", message)
        assert template in pitfalls, template
    assert "Otwórz go w edytorze i popraw albo usuń" in pitfalls and config.SETTINGS_FIX in pitfalls


def test_missing_time_zone_database_message_in_texts_is_the_programs_own(monkeypatch):
    def missing(key):
        raise ZoneInfoNotFoundError("No time zone found with key %s" % key)

    monkeypatch.setattr(config, "ZoneInfo", missing)
    message = config.zone_problem("Europe/Warsaw")
    zone = read(SKILL / "PULAPKI.md").split("## Strefa czasowa i okno publikacji", 1)[1].split("\n## ", 1)[0]
    assert "„%s”" % message in zone and "tzdata" in message and "nie edytuj `dane/config.json`" in zone
    assert "Nieznana strefa" not in message                       # to nie ustawienie klienta


def test_texts_say_where_the_speech_model_lives_on_windows_with_polish_letters_in_the_user_name():
    """R26: model leży w ASCII-owym folderze, więc krok 1 (co ląduje poza folderem i jak to usunąć) i pułapki o tym mówią."""
    from trial_reels import transcribe

    assert transcribe.MODEL_FOLDER == "trial-reels-model"
    programs, pitfalls = read(step_file(1, "programy")), read(SKILL / "PULAPKI.md")
    for path, text in (("01-programy.md", programs), ("PULAPKI.md", pitfalls)):
        assert "C:\\Users\\Public\\trial-reels-model" in text and "polskimi literami" in text, path
    assert "%PUBLIC%\\trial-reels-model" in pitfalls and "natywna biblioteka" in pitfalls
    assert programs.count("C:\\Users\\Public\\trial-reels-model") == 2        # przy instalacji i przy usuwaniu


def test_texts_say_when_the_brake_cannot_be_computed_with_the_numbers_of_the_program():
    from trial_reels import planner

    why = read(SKILL / "DLACZEGO.md").split("## Hamulec", 1)[1].split("\n## ", 1)[0]
    assert "co najmniej %d zwykłych rolek z 28 dni" % planner.BRAKE_MIN_BASE in why
    assert "co najmniej %d z ostatnich dwóch tygodni" % planner.BRAKE_MIN_RECENT in why and "za mało danych" in why
    assert "%d wyświetleń" % planner.MIN_VIEWS in why and "zostaje, dopóki dane nie pokażą" in why
    weekly = read(step_file(10, "tydzien")).split("## Gdy nie wychodzi", 1)[1]
    assert "co najmniej %d z 28 dni" % planner.BRAKE_MIN_BASE in weekly and "%d z ostatnich dwóch tygodni" % planner.BRAKE_MIN_RECENT in weekly
    assert "nieaktywny, bo za mało zwykłych rolek" in weekly and "zostaje taki, jaki był" in weekly
    quoted = versions.brake_line({"on": False, "ratio": None})
    assert quoted == "Hamulec: wyłączony (nieaktywny: za mało zwykłych rolek, żeby go policzyć)."


def test_system_requirements_say_the_same_thing_everywhere_the_client_or_claude_reads_them():
    """Minimalny macOS i architektura Windowsa wynikają z pakietów (patrz requirements.txt), więc teksty je podają."""
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "macOS 12" in requirements                                            # skąd bierze się „macOS 12”
    for path in (ROOT / "README.md", step_file(0, "powitanie"), SKILL / "PULAPKI.md"):
        text = read(path)
        assert "macOS 12 lub nowszy" in text and "procesorze x64" in text and "ARM nie jest obsługiwany" in text, path.name
    assert "(64-bit)" not in read(ROOT / "README.md") and "(64-bit)" not in read(SKILL / "PULAPKI.md")


def test_readme_gives_git_bash_a_way_to_unpack_that_does_not_need_unzip():
    readme = read(ROOT / "README.md")
    blocks = [body for lang, body in fenced_blocks(readme) if lang == "bash"]
    mac, git_bash = (next(b for b in blocks if marker in b).strip() for marker in ("unzip -o", "Expand-Archive"))
    assert "unzip" not in git_bash and "Expand-Archive -Force trial-reels.zip ." in git_bash
    assert git_bash.startswith("curl -fL -o trial-reels.zip ") and git_bash.endswith("&& rm trial-reels.zip")
    assert "Narzędzie Bash na Macu" in readme and "Git Bash na Windowsie zwykle nie ma `unzip`" in readme
    assert "Narzędzie Bash (Mac, Git Bash)" not in readme


def test_texts_say_that_status_shows_only_the_last_days_unless_asked_for_everything():
    skill = read(SKILL / "SKILL.md")
    row = next(line for line in skill.splitlines() if line.startswith("| `status` |"))
    assert "ostatnich %d dni" % cli.PREVIEW_DAYS in row and "`--wszystkie`: wszystkie wersje" in row and "z błędem" in row
    assert "`status --wszystkie`" in skill.split("**Tryb ręczny:**", 1)[1].split("\n\n", 1)[0]
    assert "`status --wszystkie`" in read(step_file(11, "codziennie")) and "tylko ostatnie 14 dni" in read(step_file(11, "codziennie"))
    assert cli.build_parser().parse_args(["status", "--wszystkie"]).wszystkie is True


def test_the_refusal_of_paczka_while_versions_wait_for_a_decision_is_quoted_from_the_program(capsys):
    waiting = [{"id": "TR-003"}, {"id": "TR-004"}]
    with pytest.raises(config.UserError) as caught:
        cli._before_the_decision(waiting, dry=False)
    message = str(caught.value)
    assert message.startswith("Paczka czeka na decyzję o pierwszych wersjach: 2 wersje czekają na akceptację klienta (TR-003, TR-004).")
    start = "Paczka czeka na decyzję o pierwszych wersjach: N wersji czeka na akceptację klienta (TR-…)"
    for path in (step_file(8, "pierwsze"), step_file(10, "tydzien")):
        assert start in read(path), path.name
    skill = read(SKILL / "SKILL.md")
    assert "Paczka czeka na decyzję o pierwszych wersjach: N wersji czeka na akceptację klienta (…)" in skill
    assert "także dopóki któraś z pierwszych wersji czeka na decyzję klienta" in skill
    assert "„akceptuję”" in message and "odrzuc ID" in message                       # i nie każe akceptować za klienta
    cli._before_the_decision(waiting, dry=True)
    assert capsys.readouterr().out.startswith("Uwaga: to tylko podgląd planu. Prawdziwa paczka ruszy dopiero")
    assert [versions.versions_wait(n) for n in (1, 2, 4, 5, 12, 22)] == [
        "1 wersja czeka", "2 wersje czekają", "4 wersje czekają", "5 wersji czeka", "12 wersji czeka", "22 wersje czekają"]


# --- drobne poprawki po drugim teście instalacji ----------------------------------

def test_programs_step_looks_for_uv_by_its_full_path_before_it_installs_it_again():
    """Po poprzedniej instalacji `uv` leży w ~/.local/bin, ale nowa rozmowa nie ma go na ścieżce powłoki (kod 127)."""
    step = read(step_file(1, "programy"))
    do_it = step.split("## Co robię ja", 1)[1].split("## Jak sprawdzamy", 1)[0]
    mac, windows = "~/.local/bin/uv --version", "%USERPROFILE%\\.local\\bin\\uv.exe --version"
    assert mac in do_it and windows in do_it and "kod 127" in do_it and "command not found" in do_it
    assert do_it.index(mac) < do_it.index("curl -LsSf https://astral.sh/uv/install.sh | sh")
    assert "w tej samej postaci, która zadziałała" in do_it
    assert "uv venv --python 3.12 .venv" in do_it and "uv pip install --python .venv -r requirements.txt" in do_it
    assert "pełną ścieżką" in read(SKILL / "SKILL.md").split("## Aktualizacja", 1)[1].split("\n## ", 1)[0]


def test_texts_remind_to_move_the_brake_slot_together_with_the_hours():
    """Domyślne brake_slot to 13:00, czyli pełna godzina: kto publikuje o pełnych godzinach, trafi w nią przy hamulcu."""
    assert config.DEFAULTS["brake_slot"] == "13:00"
    bullet = next(line for line in read(SKILL / "SKILL.md").splitlines() if line.startswith("- `brake_slot`:"))
    assert "pełna godzina" in bullet and "przesuń też `brake_slot`" in bullet and "13:05" in bullet
    for path in (step_file(8, "pierwsze"), SKILL / "PULAPKI.md", step_file(10, "tydzien")):
        text = read(path)
        assert "brake_slot" in text, path.name
    for path in (step_file(8, "pierwsze"), SKILL / "PULAPKI.md"):
        assert "13:05" in read(path), path.name


def test_step_4_says_how_many_reels_to_read_in_each_mode_without_contradicting_itself():
    point = next(line for line in read(step_file(4, "zwyciezcy")).splitlines() if line.startswith("3. Odczytuję obserwujących"))
    assert "W trybie Chrome odczytuję wszystkie rolki, które zostały na liście" in point
    assert "W trybie ręcznym odczytuję 15 rolek" in point and "według wyświetleń (punkt 4)" in point
    assert "Dla każdej rolki, która została na liście" not in point and "Nie muszą być odczytane wszystkie" not in point
    assert 'bash trial.sh wynik-kandydata Cabc123XYZ_ --wyswietlenia "12,3 tys." --obserwujacy 9' in point


def test_readme_says_what_the_doctor_does_not_check_and_how_much_disk_the_versions_need():
    """README obiecywał co najmniej 8 GB RAM, którego doktor nie sprawdza, i 5 GB miejsca, które wystarcza na start, a nie
    na stały rytm (pliki wersji zostają 14 dni po publikacji)."""
    readme = read(ROOT / "README.md")
    assert "najlepiej z 8 GB pamięci RAM" in readme and "program go nie sprawdza" in readme
    assert "co najmniej 8 GB pamięci RAM" not in readme
    assert not any("RAM" in row["nazwa"] or "amięć" in row["nazwa"] for row in doctor.checks())
    assert versions.KEEP_DAYS == 14
    for path in (ROOT / "README.md", step_file(0, "powitanie"), step_file(1, "programy")):
        text = read(path)
        assert "co najmniej 5 GB" in text and "kilka GB" in text and "14 dni po publikacji" in text, path.name


def test_weekly_prompt_says_which_id_goes_to_zapisz_wynik(monkeypatch, capsys):
    prompt = next(body for _, body in fenced_blocks(read(step_file(10, "tydzien"))) if "Kroki:" in body)
    reading = next(body for number, body in re.findall(r"^\s*(\d+)\. (.*)$", prompt.split("Kroki:", 1)[1], flags=re.M)
                   if "`do-odczytu --probka`" in body)
    assert "„TR-001  adres”" in reading and "`zapisz-wynik TR-001 " in reading
    assert "numer wersji TR-… bierz z początku tej samej linii, a nie z adresu" in reading
    slot = (cli.versions.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:00")
    config.write_json(config.STATE, {"seq": 1, "brake": {"on": False}, "versions": {"TR-001": {
        "id": "TR-001", "code": "Cabc123XYZ_", "status": "opublikowana", "slot": slot, "ig_media_id": "111"}}})
    assert cli.main(["do-odczytu", "--probka"]) == 0
    assert capsys.readouterr().out.splitlines() == ["TR-001  https://www.instagram.com/insights/media/111/?hl=en"]


def test_the_weekly_reading_is_the_sample_with_one_address_per_reel_in_every_text():
    """Odczyt stoi w zadaniu tygodniowym przed `paczka`. Pełna lista rośnie do ponad 300 adresów, więc zadanie czyta próbkę."""
    prompt = next(body for _, body in fenced_blocks(read(step_file(10, "tydzien"))) if "Kroki:" in body)
    numbered = re.findall(r"^\s*(\d+)\. (.*)$", prompt.split("Kroki:", 1)[1], flags=re.M)
    reading = next(body for number, body in numbered if "`js-odczyt`" in body)
    assert "`do-odczytu --probka`" in reading and "`do-odczytu`" not in reading
    assert "najwyżej jedną linię na rolkę" in reading and "trzy odczyty z rzędu" in reading
    skill = read(SKILL / "SKILL.md")
    cycle = skill.split("## Cykl tygodniowy", 1)[1].split("\n## ", 1)[0]
    four = next(body for number, body in re.findall(r"^(\d+)\. (.*)$", cycle, flags=re.M) if number == "4")
    assert "`do-odczytu --probka`" in four and "`do-odczytu`" not in four
    assert "Adresów bywa kilkadziesiąt" not in skill and "ponad 300 triali" in skill
    row = next(line for line in skill.splitlines() if line.startswith("| `do-odczytu` |"))
    assert "najwyżej %d adresów" % cli.DUE_LIMIT in row and "Pominięte: N." in row and "najwyżej jeden adres na rolkę" in row
    for path in CLIENT_TEXTS:                      # nigdzie nie każemy czytać pełnej listy w trybie Chrome
        assert not re.search(r"uruchom `do-odczytu`[:.,]", read(path)), path.name


def test_fresh_install_text_does_not_claim_that_krok_fails_to_run():
    for path in (ROOT / "README.md", ROOT / "CLAUDE.md"):
        text = read(path)
        assert "się nie uruchomi" not in text and "kodem wyjścia 3" in text, path.name


# --- rolki bez mowy, wspólne cta, bank hooków, kandydaci ---------------------------

def test_messages_about_a_skipped_reel_in_texts_are_the_programs_own(monkeypatch, capsys):
    """Rolka bez hooków jest pomijana z ostrzeżeniem, a `krok` pokazuje alert: teksty cytują oba zdania programu."""
    reels = {"Reel013": {"code": "Reel013", "name": "NAZWA"}}
    versions._report_blocked(reels, {"Reel013": versions.NO_HOOKS}, [{"code": "Reel001", "active": True}])
    warning = capsys.readouterr().out.strip().replace("NAZWA (Reel013)", "NAZWA (KOD)")
    assert warning.startswith("Uwaga: pomijam rolkę NAZWA (KOD): nie ma hooków w dane/hooki.json (dopisz co najmniej 3).")
    with pytest.raises(config.UserError, match="Nie ma rolki, z której da się zrobić wersje."):
        versions._report_blocked(reels, {"Reel013": versions.NO_HOOKS}, [])
    monkeypatch.setattr(versions, "started", lambda st: True)
    monkeypatch.setattr(versions, "reels_without_hooks", lambda: ["NAZWA (KOD)"])
    alert = wizard._hooks_alert({})
    pitfalls, skill, daily = read(SKILL / "PULAPKI.md"), read(SKILL / "SKILL.md"), read(step_file(11, "codziennie"))
    assert warning in pitfalls and "Nie ma rolki, z której da się zrobić wersje." in pitfalls
    assert "Rolka NAZWA (KOD) nie ma hooków w dane/hooki.json, więc paczka ją pomija." in pitfalls
    assert alert in skill and "Uwaga: pomijam rolkę" in skill and "Uwaga: pomijam rolkę" in daily
    assert "Uwaga: pomijam rolkę" in read(step_file(10, "tydzien")) and "rolka bez hooków" in daily


def test_speechless_reels_are_covered_wherever_the_client_meets_them():
    for path in (step_file(5, "pliki"), step_file(6, "ustawienia"), step_file(7, "hooki"), SKILL / "PULAPKI.md",
                 SKILL / "SKILL.md"):
        text = read(path)
        assert "bez mowy" in text and "strong" in text, path.name
    for path in (step_file(5, "pliki"), SKILL / "PULAPKI.md"):
        assert '"active": false' in read(path), path.name              # rolkę wolno też wyłączyć
    for path in (step_file(7, "hooki"), SKILL / "SKILL.md"):
        assert "podpisu" in read(path) and "obrazu" in read(path), path.name   # hooki z podpisu i obrazu
    assert "Rolka bez mowy" in read(SKILL / "PULAPKI.md") and "Zmyślona transkrypcja" in read(SKILL / "PULAPKI.md")


def test_speechless_reel_messages_in_texts_are_the_programs_own(make_reel, make_hooks, put_reel_files, capsys):
    code = "Cabc123XYZ_"
    put_reel_files(code, transcript=False)
    config.write_json(config.TRANSCRIPTS / ("%s.json" % code), {"segments": []})      # nikt nie mówi
    quiet = make_reel(code)
    del quiet["strong"], quiet["cuts"]
    notes = []
    assert candidates.validate([quiet], {code: make_hooks()}, notes) == [] and len(notes) == 1
    label = "Rolka Przykładowa rolka (%s)" % code
    assert notes[0].startswith(label + ": ")
    note = "Rolka NAZWA (KOD)" + notes[0][len(label):]
    for path in (step_file(5, "pliki"), SKILL / "PULAPKI.md"):
        assert "Informacja: " + note in read(path), "%s: cytat „Informacja:” różni się od programu" % path.name
    candidates.save_pool([quiet])                                           # i tak ją drukuje komenda sprawdz-pule
    config.write_json(config.HOOKS, {code: make_hooks()})
    assert cli.main(["sprawdz-pule"]) == 0
    assert "Informacja: " + notes[0] in capsys.readouterr().out.splitlines()
    problems = candidates.validate([make_reel(code)], {code: make_hooks()})       # ta ma jeszcze strong i cuts
    assert len(problems) == 1 and problems[0].startswith(label + ": ")
    assert "Rolka NAZWA (KOD)" + problems[0][len(label):] in read(SKILL / "PULAPKI.md")
    assert problems[0][len(label) + 2:] in read(step_file(7, "hooki"))


def test_cta_is_optional_in_the_texts_and_in_the_real_validator(put_reel_files):
    blocks = json_blocks(SKILL / "SKILL.md")
    pool = next(b for b in blocks if isinstance(b, dict) and "cta" in b)
    hooks = next(b for b in blocks if isinstance(b, dict) and pool["code"] in b)
    put_reel_files(pool["code"])
    without_cta = {key: value for key, value in pool.items() if key not in ("cta", "cta_variants")}
    assert candidates.validate([without_cta], hooks) == []                  # program nie żąda zaproszenia w podpisie
    assert "`cta` jest opcjonalne" in read(SKILL / "SKILL.md")
    assert "opcjonalne" in read(step_file(7, "hooki")) and "oba teksty muszą być identyczne" not in read(SKILL / "SKILL.md")


def test_hook_bank_on_start_is_the_same_number_everywhere():
    assert candidates.MIN_HOOKS < START_HOOKS
    assert "piszesz %d hooków" % START_HOOKS in read(SKILL / "SKILL.md")
    assert "bank %d hooków" % START_HOOKS in read(step_file(7, "hooki"))
    assert "po %d hooków" % START_HOOKS in read(step_file(7, "hooki"))
    for path in CLIENT_TEXTS:
        assert not re.search(r"\bbank 10\b|\bpo 10 hooków|\b10 hooków na rolkę|pełny bank", read(path)), path.name


def test_breaks_are_proposed_after_steps_5_and_7_and_hooks_can_be_split_across_sittings():
    rules = read(ROOT / "CLAUDE.md")
    assert "koniec kroku 5" in rules and "koniec kroku 7" in rules and "kilka posiedzeń" in rules
    assert "przerwę" in read(step_file(5, "pliki")) and "przerwę" in read(step_file(7, "hooki"))
    assert "kilka posiedzeń" in read(step_file(7, "hooki"))


def test_texts_never_tell_claude_to_edit_or_load_the_candidates_file():
    for path in CLIENT_TEXTS:
        assert not re.search(r"(?<!nie )[Uu]suwam z `dane/kandydaci\.json`|usunięcie rolek wykreślonych", read(path)), path.name
    step = read(step_file(4, "zwyciezcy"))
    assert "pula KOD1 KOD2" in step and "nie usuwam z `dane/kandydaci.json`" in step
    assert "Nie edytujesz go" in read(SKILL / "SKILL.md") and "kandydaci.json" in read(ROOT / "CLAUDE.md")
    assert "bez żadnych nowych komend" not in step


# --- komunikaty programu cytowane w tekstach ---------------------------------------

def test_clash_messages_in_texts_are_the_programs_own():
    skipped = "masz już inny post na Instagramie. Pomijam tę wersję."
    assert skipped in inspect.getsource(versions)
    hint = versions.clash_hint(["TR-001"])
    summary = "Na sucho: zaplanowałbym %d z %d. Nic nie wysłałem i nic nie zmieniłem."
    done = "Zaplanowane w Zernio: %d z %d."
    assert summary in inspect.getsource(cli) and done in inspect.getsource(cli)
    for path in (step_file(8, "pierwsze"), SKILL / "PULAPKI.md"):
        text = read(path)
        assert skipped in text and hint in text, path.name
        assert summary % (0, 9) in text and done % (0, 9) in text, path.name
    assert hint.split(",")[0] in read(step_file(10, "tydzien"))
    assert "przesunięcie godzin nie wystarczy" in read(step_file(8, "pierwsze")).replace("Samo przesunięcie", "przesunięcie")


def test_dry_run_texts_describe_what_the_program_prints():
    """Plan na sucho (paczka i zaplanuj) pyta Zernio o zajęte terminy, ale niczego nie wysyła. Teksty cytują jego zdania."""
    source = inspect.getsource(cli)
    plan_skip = "na ten termin masz już inny post na Instagramie. Pomijam ten termin."
    summary = "Na sucho: zaplanowałbym"
    refusal = "następny krok to zaplanuj, po zgodzie klienta na pokazane terminy"
    assert plan_skip in source and summary in source and refusal in source
    assert "Dokończyłbym" in source and "Uwaga: to tylko podgląd planu." in source
    plan_hint = versions.clash_hint([])
    assert plan_hint.endswith("i uruchom plan na sucho jeszcze raz.") and "odrzuc" not in plan_hint
    for path in (SKILL / "PULAPKI.md", step_file(10, "tydzien")):
        text = read(path)
        assert plan_skip in text and summary in text, path.name
    assert plan_hint in read(SKILL / "PULAPKI.md")
    skill = read(SKILL / "SKILL.md")
    rows = {m.group(1): m.group(0) for m in (re.match(r"\| `([^`]+)` \|.*", row) for row in skill.splitlines()) if m}
    for name in ("zaplanuj", "paczka"):
        assert "pyta Zernio o zajęte terminy" in rows[name] and "tylko odczyt" in rows[name], name
    assert refusal in rows["paczka"] and "pominie" in rows["paczka"]
    assert "Dokończyłbym zaakceptowane wersje" in read(SKILL / "PULAPKI.md")


def test_the_hook_bank_message_is_described_for_the_plan_and_for_the_real_run():
    skill = read(SKILL / "SKILL.md")
    bullet = next(line for line in skill.splitlines() if "Bank hooków prawie pusty" in line)
    assert "po prawdziwej `paczka` i w planie na sucho" in bullet and "emotkę z banku" in bullet
    assert "w planie na sucho" in read(step_file(11, "codziennie"))


def test_kadr_messages_in_texts_are_the_programs_own(monkeypatch, tmp_path):
    past_end = "Film ma tylko X s, więc nie ma w nim klatki z Y s. Podaj mniejszy czas w opcji --t."
    near_end = ("Film ma X s, a tuż przed jego końcem nie ma już klatki do wyciągnięcia, więc nie ma jej w Y s. "
                "Podaj w opcji --t czas mniejszy niż Z s.")
    damaged = "Nie udało się wyciągnąć klatki z Y s: plik jest uszkodzony albo ffmpeg go nie odczytał."
    monkeypatch.setattr(render, "probe", lambda path: 2.0)
    assert render._grab_problem(tmp_path / "film.mp4", 8.0) == past_end.replace("X", "2").replace("Y", "8")
    assert render._grab_problem(tmp_path / "film.mp4", 1.9) == near_end.replace("X", "2").replace("Y", "1,9").replace("Z", "1,75")

    def unreadable(path):
        raise RuntimeError("PyAV nie czyta tego pliku")

    monkeypatch.setattr(render, "probe", unreadable)
    assert render._grab_problem(tmp_path / "film.mp4", 1.0) == damaged.replace("Y", "1")
    step, pitfalls = read(step_file(6, "ustawienia")), read(SKILL / "PULAPKI.md")
    assert past_end in step and near_end in step and damaged in step
    assert past_end in pitfalls and near_end in pitfalls


def test_a_failed_kadr_keeps_the_previous_frame_says_every_text_that_mentions_overwriting():
    for path in (step_file(6, "ustawienia"), SKILL / "PULAPKI.md", SKILL / "SKILL.md"):
        text = read(path)
        assert "nadpisuje ten sam plik" in text and "poprzednią klatkę" in text, path.name


def test_step_6_explains_how_the_frame_is_seen_shown_and_overwritten():
    step = read(step_file(6, "ustawienia"))
    assert "narzędziem do czytania plików" in step and "ono widzi obrazy" in step
    assert "open dane/wersje/kadr_KOD.jpg" in step and "Start-Process dane\\wersje\\kadr_KOD.jpg" in step
    assert 'explorer "dane\\wersje\\kadr_KOD.jpg"' in step
    assert "nadpisuje ten sam plik" in step and "po kolei" in step


def test_krok_gotowe_message_in_skill_is_the_programs_own(capsys):
    assert cli.main(["krok", "--gotowe", "pliki"]) == 0
    message = capsys.readouterr().err.strip()
    template = message.replace("„Pliki i transkrypcje”", "„…”")
    assert "„…”" in template and template.startswith("Nic nie zapisałem: krok ")
    assert template in read(SKILL / "SKILL.md")


def test_programs_step_tells_the_truth_about_what_lands_outside_the_folder():
    step = read(step_file(1, "programy"))
    for needle in ("~/.local/bin", "~/.cache/huggingface", "~/.zshrc", "~/.profile", "uv python dir", "uv cache dir",
                   "1,6–1,8 GB"):
        assert needle in step, needle
    assert "tylko w folderze" not in step and "najwyżej kilkuset MB" not in step and "bez śmiecenia" not in step
    assert "zanim cokolwiek zainstaluję" in step.lower()


def test_weekly_prompt_waits_for_paczka_limits_retries_and_matches_the_cycle_in_skill():
    prompt = next(body for _, body in fenced_blocks(read(step_file(10, "tydzien"))) if "Kroki:" in body)
    numbered = re.findall(r"^\s*(\d+)\. (.*)$", prompt.split("Kroki:", 1)[1], flags=re.M)
    assert [int(number) for number, _ in numbered] == list(range(1, len(numbered) + 1)), "kroki promptu liczymy od 1"
    paczka = next(body for _, body in numbered if "`paczka --dni 7`" in body)
    assert "jako polecenie w tle" in paczka and "run_in_background" in paczka and "limit 10 minut" in paczka
    assert "powiadomienie o jej końcu" in paczka and "w pętli" in paczka          # czeka na powiadomienie, nie sprawdza co chwilę
    assert "kod wyjścia inny niż 0" in paczka and "najwyżej 3 razy" in paczka and "pomija terminy" in paczka
    assert "a nie w tle" not in paczka and "zwykłą komendą" not in paczka
    assert "Nie przechodź do kroku 6, dopóki paczka się nie skończy" in paczka
    assert "przepisz tę podpowiedź do podsumowania i jej nie wykonuj" in prompt
    cycle = read(SKILL / "SKILL.md").split("## Cykl tygodniowy", 1)[1].split("\n## ", 1)[0]
    cycle_steps = re.findall(r"^(\d+)\. (.*)$", cycle, flags=re.M)

    def first_command(body):
        return re.search(r"`([^`]+)`", body).group(1)

    assert [first_command(body) for _, body in cycle_steps] == [first_command(body) for _, body in numbered]
    assert "najwyżej 3 razy" in cycle and "w tle" in cycle and "powiadomienie o jej końcu" in cycle
    assert "nie uruchamiasz jej w tle" not in cycle and "dopiero po jej końcu" in cycle


def test_long_commands_run_in_the_background_everywhere_including_the_weekly_task():
    """Narzędzie do komend ma limit 10 minut, a paczka na tydzień trwa dłużej: zawsze w tle, z czekaniem na powiadomienie
    o końcu, bez sprawdzania wyniku w pętli. Dawny wyjątek „w zadaniu tygodniowym zwykłą komendą” nie obowiązuje."""
    for path in (ROOT / "CLAUDE.md", SKILL / "SKILL.md", step_file(10, "tydzien")):
        text = read(path)
        assert "zwykłą komendą, a nie w tle" not in text and "nie uruchamiasz jej w tle" not in text, path.name
        assert "powiadomienie o" in text and "w tle" in text, path.name
    rules = read(ROOT / "CLAUDE.md")
    assert "Tak samo w zadaniu tygodniowym" in rules and "Wyjątek: w zadaniu tygodniowym" not in rules
    skill = read(SKILL / "SKILL.md")
    assert "run_in_background" in skill and "nie sprawdzaj ich wyniku w pętli" in skill
    assert "Dotyczy to też zadania tygodniowego" in skill and "Wyjątek: w zadaniu tygodniowym" not in skill
    steps = read(step_file(10, "tydzien"))
    do_it = steps.split("## Co robię ja", 1)[1].split("## Jak sprawdzamy", 1)[0]
    assert "Czekam na powiadomienie o jej końcu" in do_it and "nie sprawdzam jej w pętli" in do_it


def test_ask_rules_also_catch_the_bare_update_command():
    """Dokumentacja uprawnień Claude Code: `*` na końcu reguły, po spacji, pasuje też do samej komendy (`Bash(ls *)`
    pasuje do `ls`), o ile jest jedyną gwiazdką w regule, a reguła ask wygrywa z allow. Reguły ask łapią więc `aktualizuj
    --tak` także bez dalszych argumentów, w obu powłokach."""
    permissions = json.loads(read(ROOT / ".claude" / "settings.json"))["permissions"]
    kinds = set()
    for rule in permissions["ask"]:
        inner = rule[rule.index("(") + 1:-1]
        assert inner.endswith(" *") and inner.count("*") == 1, rule
        command = inner[:-2]
        assert command.endswith(" aktualizuj --tak"), rule
        launcher = "trial.sh " if "trial.sh" in command else "trial.cmd "
        args = cli.build_parser().parse_args(shlex.split(command.split(launcher, 1)[1]))
        assert args.komenda == "aktualizuj" and args.tak is True
        launcher_prefix = command.split(" aktualizuj")[0] + " "          # np. „bash trial.sh ”
        assert any(allowed[allowed.index("(") + 1:-1].startswith(launcher_prefix) for allowed in permissions["allow"]), rule
        kinds.add(rule.split("(", 1)[0])
    assert kinds == {"Bash", "PowerShell"}
