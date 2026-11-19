"""Testy strażnika danych: klucze, adresy e-mail, obcy autorzy i frazy z prywatnej listy.

Fałszywe klucze i adresy składamy w locie ("sk_" + "A" * 24), żeby sam plik testów nie był
trafieniem, gdy strażnik sprawdza całe repo.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE / "tools"))

import straznik  # noqa: E402

NEUTRAL = "Trial Reels <trial-reels@users.noreply.github.com>"
FOREIGN = "Jan Kowalski <jan@example.com>"
FOREIGN_AUTHOR = "autor spoza dozwolonej tożsamości"
FOREIGN_COMMITTER = "committer spoza dozwolonej tożsamości"
AUTHOR_ZONE = "data autora w strefie innej niż +0000"
COMMITTER_ZONE = "data committera w strefie innej niż +0000"
UTC_DATE = "2026-01-01T12:00:00+0000"
ZOLTA_FIRMA = straznik.digest("zolta firma")


def addr(local: str, domain: str) -> str:
    """Adres e-mail składany w locie, żeby w kodzie testów nie stał jako gotowy ciąg."""
    return local + "@" + domain


# Po jednym fałszywym przykładzie na każdy wzorzec; kluczem jest nazwa wzorca (powód w wyniku).
SAMPLES = {
    "klucz sk_": "sk_" + "A" * 24,
    "klucz sk-ant-": "sk-ant-" + "b" * 12,
    "token ntn_": "ntn_" + "C" * 24,
    "token secret_": "secret_" + "D" * 24,
    "token GitHub (gh?_)": "ghp_" + "e" * 24,
    "token GitHub github_pat_": "github_pat_" + "F" * 24,
    "klucz AWS AKIA": "AKIA" + "G" * 16,
    "klucz prywatny (BEGIN PRIVATE KEY)": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "token Slack xox": "xoxb-" + "1234567890",
    "adres e-mail": addr("jan", "example.org"),
}


def git(repo, *args, env=None) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, **(env or {})},
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture
def tmp_git(tmp_path, monkeypatch):
    """Repo w tmp_path z neutralną tożsamością, odcięte od globalnej konfiguracji gita (podpisy, hooki, autocrlf).

    Daty commitów są jawnie w UTC (+0000), bo strażnik zgłasza każdą inną strefę, a strefa komputera, na którym idą
    testy, bywa dowolna.
    """
    empty = tmp_path / "pusta-konfiguracja-gita"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_DATE", UTC_DATE)
    monkeypatch.setenv("GIT_COMMITTER_DATE", UTC_DATE)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Trial Reels")
    git(repo, "config", "user.email", "trial-reels@users.noreply.github.com")
    return repo


def write(repo, name, text) -> Path:
    """Zapisuje plik (UTF-8, bez zamiany końców linii) i dodaje go do indeksu, bo strażnik czyta pliki z `git ls-files`."""
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    git(repo, "add", "--", name)
    return path


def commit(repo, message="zmiana", author=None, committer=None) -> str:
    """Commit z tego, co jest w indeksie (może być pusty); zwraca pełny skrót."""
    env = {}
    if committer:
        name, email = committer.rstrip(">").split(" <")
        env = {"GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    args = ["commit", "-q", "--allow-empty", "--no-verify", "-m", message]
    if author:
        args.append(f"--author={author}")
    git(repo, *args, env=env)
    return git(repo, "rev-parse", "HEAD")


# --- skróty i tokeny ---------------------------------------------------------

def test_digest_is_sha256_hex_of_utf8():
    assert straznik.digest("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert straznik.digest("zażółć") != straznik.digest("zazolc")


def test_tokens_words_parts_and_ngrams():
    assert straznik.tokens("Ala-Ola ma_kota") == {
        "ala-ola", "ma_kota",                   # słowa w całości
        "ala", "ola", "ma", "kota",             # ich części
        "ala ola", "ola ma", "ma kota",         # bigramy części
        "ala ola ma", "ola ma kota",            # trigramy części
    }
    assert straznik.tokens("kot pies") == {"kot", "pies", "kot pies"}
    assert straznik.tokens("") == set() and straznik.tokens("... --- ???") == set()


def test_tokens_split_domains_and_keep_digits():
    found = straznik.tokens("zob. www.przyklad.pl/a 42")
    assert {"www.przyklad.pl", "www", "przyklad", "pl", "przyklad pl", "www przyklad pl", "42"} <= found


def test_tokens_fold_polish_letters():
    assert straznik.digest("lukasz zab") in {straznik.digest(t) for t in straznik.tokens("Łukasz Ząb")}
    assert {"zdzblo", "zolw", "cma", "lodz"} <= straznik.tokens("Źdźbło ŻÓŁW Ćma ŁÓDŹ")


# --- skan plików -------------------------------------------------------------

def test_finds_fake_key_without_printing_it(tmp_git):
    write(tmp_git, "a.md", "klucz: sk_" + "A" * 24)
    out = straznik.scan_files(tmp_git, set())
    assert out and ("sk_" + "A" * 24) not in "".join(out)
    assert out == ["a.md:1: klucz sk_"]


def test_finds_banned_phrase_by_hash_despite_diacritics(tmp_git):
    write(tmp_git, "b.md", "Pozdrawia Żółta Firma")
    out = straznik.scan_files(tmp_git, {straznik.digest("zolta firma")})
    assert out == ["b.md:1: słowo z listy"]
    assert "Firma" not in "".join(out) and "Żółta" not in "".join(out)


def test_clean_repo_passes(tmp_git):
    write(tmp_git, "c.md", "Trial to próbna rolka, hook w 0–3 s.")
    assert straznik.scan_files(tmp_git, {straznik.digest("zolta firma")}) == []


def test_every_secret_pattern_has_a_sample():
    assert list(SAMPLES) == list(straznik.SECRET_PATTERNS)


@pytest.mark.parametrize("name", list(SAMPLES))
def test_each_secret_pattern_is_reported_by_its_name(tmp_git, name):
    sample = SAMPLES[name]
    write(tmp_git, "x.txt", f"przed {sample} po\n")
    out = straznik.scan_files(tmp_git, set())
    assert out == [f"x.txt:1: {name}"]
    assert sample not in "".join(out)


PREFIXED_KEYS = [name for name in SAMPLES if name not in ("adres e-mail", "klucz prywatny (BEGIN PRIVATE KEY)")]


@pytest.mark.parametrize("name", PREFIXED_KEYS)
def test_key_is_found_after_any_separator_but_not_inside_a_longer_word(tmp_git, name):
    """Klucz stoi po separatorze. Gdy przed prefiksem jest litera albo cyfra (jak w `mask_…`), to nie klucz."""
    sample = SAMPLES[name]
    separators = ["", " ", "=", ":", '"', "'", "(", "/", "_", "-", ">"]
    inside_words = ["a", "Z", "7"]
    write(tmp_git, "x.txt", "\n".join([s + sample for s in separators] + [w + sample for w in inside_words]) + "\n")
    flagged = [int(x.split(":")[1]) for x in straznik.scan_files(tmp_git, set())]
    assert flagged == list(range(1, len(separators) + 1))


def test_identifiers_that_contain_a_key_prefix_are_not_keys(tmp_git):
    write(tmp_git, "kod.py", "mask_output_token_str = 1\ntask_scheduler_configuration()\ndisk_usage_report_total\n")
    assert straznik.scan_files(tmp_git, set()) == []


def test_scan_files_reports_path_and_line_number(tmp_git):
    write(tmp_git, "docs/notatki.md", "pierwsza\ndruga\nklucz: sk_" + "A" * 24 + "\nczwarta\n")
    write(tmp_git, "a.md", "nic\n")
    assert straznik.scan_files(tmp_git, set()) == ["docs/notatki.md:3: klucz sk_"]


def test_each_reason_is_reported_once_per_line_in_pattern_order(tmp_git):
    key = SAMPLES["klucz sk_"]
    mail = SAMPLES["adres e-mail"]
    write(tmp_git, "l.md", f"{mail} {key} {key} {mail}\nczysta linia\n{key}\n")
    assert straznik.scan_files(tmp_git, set()) == [
        "l.md:1: klucz sk_", "l.md:1: adres e-mail", "l.md:3: klucz sk_",
    ]


ALLOWED_EMAILS = [
    "noreply@anthropic.com",
    "NoReply@Anthropic.com",
    "12345+jan@users.noreply.github.com",
    "jan.k@example.com",
    "jan@EXAMPLE.COM",
    "Napisz na jan@example.com.",
    "<jan@example.com>",
]
FOREIGN_EMAILS = [
    addr("jan", "example.org"),
    addr("jan", "example.com.pl"),
    addr("jan", "example.community"),
    addr("jan", "example.com-test"),
    addr("jan", "sub.example.com"),
    addr("jan", "notexample.com"),
    addr("noreply", "anthropic.com.pl"),
    addr("jan", "anthropic.com"),
    addr("jan", "gmail.com"),
    addr("jan", "users.noreply.github.com.pl"),
    addr("jan", "sub.users.noreply.github.com"),
    "Napisz na " + addr("jan", "firma.pl") + ".",
]


def test_only_listed_email_addresses_are_allowed(tmp_git):
    lines = ALLOWED_EMAILS + FOREIGN_EMAILS
    write(tmp_git, "mail.md", "\n".join(f"kontakt: {x}" for x in lines) + "\n")
    out = straznik.scan_files(tmp_git, set())
    flagged = [int(x.split(":")[1]) for x in out]
    assert flagged == list(range(len(ALLOWED_EMAILS) + 1, len(lines) + 1))
    assert all(x.endswith(": adres e-mail") for x in out)
    assert "firma.pl" not in "".join(out)


def test_at_signs_in_code_are_not_emails(tmp_git):
    write(tmp_git, "kod.py", "@pytest.fixture\n@property\npaczka @types/node\nuzytkownik @ serwer\nmacierz = a@b\n")
    assert straznik.scan_files(tmp_git, set()) == []


def test_diff_like_text_is_not_mistaken_for_an_email_but_real_addresses_in_it_are_found(tmp_git):
    """`+@pytest.fixture` to dekorator ze znacznikiem diffu, a nie adres. Adres tuż po `+`, `-` albo `_` to adres."""
    mail = SAMPLES["adres e-mail"]
    lines = ["+@pytest.fixture", "-@pytest.mark.skipif", " @pytest.mark.parametrize", ".@pytest.fixture",
             "+" + mail, "-" + mail, "_" + mail]
    write(tmp_git, "zmiana.patch", "\n".join(lines) + "\n")
    out = straznik.scan_files(tmp_git, set())
    assert out == [f"zmiana.patch:{n}: adres e-mail" for n in (5, 6, 7)]


def test_escaped_line_break_before_a_handle_is_not_an_email(tmp_git):
    """W kodzie i w JSON-ie podpis z nickiem po łamaniu linii to `…\\n@nick.konto`: litera „n” po backslashu nie jest adresem."""
    handle = "@przyklad.konto"
    lines = [
        'podpis = "Obserwuj\\n' + handle + '"',
        '{"podpis": "Tekst\\n\\n' + handle + '"}',
        '"\\t' + handle + '", "\\r' + handle + '"',
    ]
    write(tmp_git, "podpisy.py", "\n".join(lines) + "\n")
    assert straznik.scan_files(tmp_git, set()) == []
    write(tmp_git, "prawdziwy.py", 'adres = "Napisz\\n' + addr("anna", "przyklad.pl") + '"\n')   # po `\n` stoi prawdziwy adres
    assert straznik.scan_files(tmp_git, set()) == ["prawdziwy.py:1: adres e-mail"]


def test_skips_binary_extensions_but_not_other_files(tmp_git):
    key = "klucz: " + SAMPLES["klucz sk_"]
    for name in ("a.png", "b.TTF", "c.zip", "d.ico", "e.mp4", "folder/f.PNG"):
        write(tmp_git, name, key)
    write(tmp_git, "g.txt", key)
    assert straznik.scan_files(tmp_git, set()) == ["g.txt:1: klucz sk_"]


def test_checks_only_tracked_files_and_survives_deleted_ones(tmp_git):
    key = SAMPLES["klucz sk_"]
    (tmp_git / "nieśledzony.md").write_text(key, encoding="utf-8")   # nie dodany do indeksu
    gone = write(tmp_git, "usuniety.md", key)
    gone.unlink()                                                    # w indeksie jest, na dysku nie ma
    write(tmp_git, "zwykly.md", "nic\n")
    assert straznik.scan_files(tmp_git, set()) == []


def test_handles_polish_letters_and_spaces_in_file_names(tmp_git):
    write(tmp_git, "Łódź ąę/zażółć gęślą.md", "klucz: " + SAMPLES["klucz sk_"])
    assert straznik.scan_files(tmp_git, set()) == ["Łódź ąę/zażółć gęślą.md:1: klucz sk_"]


def test_banned_phrase_is_found_across_a_line_break(tmp_git):
    write(tmp_git, "c.md", "Pozdrawia Żółta\nFirma i reszta\n")
    assert straznik.scan_files(tmp_git, {ZOLTA_FIRMA}) == ["c.md:1: słowo z listy"]


def test_banned_word_is_found_inside_compound_names_and_addresses(tmp_git):
    write(tmp_git, "d.md", "nic\nzob. https://www.zolta-firma.pl/kontakt\nsame-zolta_koniec\n")
    out = straznik.scan_files(tmp_git, {straznik.digest("zolta")})
    assert out == ["d.md:2: słowo z listy", "d.md:3: słowo z listy"]


def test_banned_phrase_in_a_file_name_is_reported_on_line_zero(tmp_git):
    write(tmp_git, "zolta-firma-notatki.md", "nic ciekawego\n")
    assert straznik.scan_files(tmp_git, {ZOLTA_FIRMA}) == ["zolta-firma-notatki.md:0: słowo z listy"]


def test_banned_words_are_matched_whole_not_as_fragments(tmp_git):
    write(tmp_git, "e.md", "zoltaaa firmaaa, zolta-firmowy\n")
    assert straznik.scan_files(tmp_git, {ZOLTA_FIRMA}) == []


@pytest.mark.skipif(sys.platform == "win32", reason="dowiązania symboliczne wymagają uprawnień na Windowsie")
def test_symlink_target_is_checked_as_text(tmp_git):
    link = tmp_git / "dowiazanie"
    link.symlink_to("zolta-firma/tajny-folder")
    git(tmp_git, "add", "--", "dowiazanie")
    assert straznik.scan_files(tmp_git, {ZOLTA_FIRMA}) == ["dowiazanie:1: słowo z listy"]


# --- skan historii -----------------------------------------------------------

def test_history_rejects_foreign_author(tmp_git):
    sha = commit(tmp_git, author=FOREIGN)
    out = straznik.scan_history(tmp_git, set())
    assert any("autor" in x for x in out)
    assert out == [f"commit {sha[:7]}: {FOREIGN_AUTHOR}"]
    assert "Kowalski" not in "".join(out) and "example.com" not in "".join(out)


def test_history_rejects_foreign_committer(tmp_git):
    sha = commit(tmp_git, committer=FOREIGN)
    assert straznik.scan_history(tmp_git, set()) == [f"commit {sha[:7]}: {FOREIGN_COMMITTER}"]


def test_history_reports_both_author_and_committer_when_both_are_foreign(tmp_git):
    sha = commit(tmp_git, author=FOREIGN, committer=FOREIGN)
    assert straznik.scan_history(tmp_git, set()) == [
        f"commit {sha[:7]}: {FOREIGN_AUTHOR}", f"commit {sha[:7]}: {FOREIGN_COMMITTER}",
    ]


def test_history_accepts_neutral_identity_and_allowed_trailers(tmp_git):
    write(tmp_git, "a.md", "nic\n")
    commit(tmp_git, message="Dodaj plik\n\nCo-Authored-By: Claude <noreply@anthropic.com>", author=NEUTRAL)
    assert straznik.scan_history(tmp_git, set()) == []


def test_history_reports_commits_whose_dates_are_not_in_utc(tmp_git, monkeypatch):
    """Strefa czasowa w dacie commita zdradza, gdzie był autor, więc w publicznej historii są tylko daty +0000."""
    commit(tmp_git, "w UTC")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-01-02T12:00:00+0700")
    author_zone = commit(tmp_git, "autor w innej strefie")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-01-03T12:00:00+0000")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-03T12:00:00-0500")
    committer_zone = commit(tmp_git, "committer w innej strefie")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-01-04T12:00:00+0100")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-04T12:00:00+0100")
    both = commit(tmp_git, "obie daty w innej strefie")
    out = straznik.scan_history(tmp_git, set())
    assert sorted(out) == sorted([f"commit {author_zone[:7]}: {AUTHOR_ZONE}",
                                  f"commit {committer_zone[:7]}: {COMMITTER_ZONE}",
                                  f"commit {both[:7]}: {AUTHOR_ZONE}", f"commit {both[:7]}: {COMMITTER_ZONE}"])
    assert not any("+0700" in x or "-0500" in x for x in out)


def test_history_of_empty_repo_is_clean(tmp_git):
    assert straznik.scan_history(tmp_git, set()) == []


def test_history_checks_every_branch(tmp_git):
    commit(tmp_git, "start")
    git(tmp_git, "checkout", "-q", "-b", "boczna")
    sha = commit(tmp_git, "obcy", author=FOREIGN)
    git(tmp_git, "checkout", "-q", "-")
    assert straznik.scan_history(tmp_git, set()) == [f"commit {sha[:7]}: {FOREIGN_AUTHOR}"]


def test_history_handles_merge_commits_and_reports_content_once(tmp_git):
    write(tmp_git, "baza.md", "nic\n")
    commit(tmp_git, "start")
    git(tmp_git, "checkout", "-q", "-b", "boczna")
    write(tmp_git, "k.txt", SAMPLES["klucz sk_"] + "\n")
    on_branch = commit(tmp_git, "klucz na bocznej gałęzi")
    git(tmp_git, "checkout", "-q", "-")
    write(tmp_git, "inny.md", "nic\n")
    commit(tmp_git, "zmiana na głównej")
    git(tmp_git, "merge", "-q", "--no-ff", "-m", "scal", "boczna")
    assert straznik.scan_history(tmp_git, set()) == [f"commit {on_branch[:7]}: klucz sk_"]


def test_history_finds_key_that_was_removed_later(tmp_git):
    key = SAMPLES["klucz sk_"]
    write(tmp_git, "k.txt", key + "\n")
    first = commit(tmp_git, "dodaj")
    git(tmp_git, "rm", "-q", "k.txt")
    commit(tmp_git, "usuń")
    write(tmp_git, "inny.md", "nic\n")
    third = commit(tmp_git, "inny plik")
    out = straznik.scan_history(tmp_git, set())
    assert f"commit {first[:7]}: klucz sk_" in out
    assert not any(third[:7] in x for x in out)
    assert key not in "".join(out)


def test_history_checks_commit_messages_and_reports_each_reason_once_per_commit(tmp_git):
    key, mail = SAMPLES["klucz sk_"], SAMPLES["adres e-mail"]
    sha = commit(tmp_git, f"Dodaj {key}\n\nKontakt {mail}, znów {key}")
    assert straznik.scan_history(tmp_git, set()) == [
        f"commit {sha[:7]}: klucz sk_", f"commit {sha[:7]}: adres e-mail",
    ]


def test_history_finds_banned_phrase_in_diff_message_and_path(tmp_git):
    write(tmp_git, "plik.md", "Pozdrawia Żółta Firma\n")
    in_diff = commit(tmp_git, "dodaj plik")
    in_message = commit(tmp_git, "Notatka o Żółtej Firmie: żółta firma")
    write(tmp_git, "zolta-firma.md", "nic\n")
    in_path = commit(tmp_git, "inny plik")
    commit(tmp_git, "zwykły commit")
    out = straznik.scan_history(tmp_git, {ZOLTA_FIRMA})
    assert sorted(out) == sorted(f"commit {s[:7]}: słowo z listy" for s in (in_diff, in_message, in_path))


def test_history_does_not_mistake_diff_markers_for_part_of_the_content(tmp_git):
    """W diffie przed dodaną linią stoi `+` (przed usuniętą `-`), więc `+@pytest.fixture` wyglądało jak adres e-mail."""
    write(tmp_git, "kod.py", "@pytest.fixture\n@pytest.mark.skipif(True, reason=\"x\")\ndef f():\n    pass\n")
    commit(tmp_git, "dodaj kod")
    git(tmp_git, "rm", "-q", "kod.py")
    commit(tmp_git, "usuń kod")
    assert straznik.scan_history(tmp_git, set()) == []


def test_history_finds_content_that_starts_right_after_the_diff_marker(tmp_git):
    mail, pem = SAMPLES["adres e-mail"], SAMPLES["klucz prywatny (BEGIN PRIVATE KEY)"]
    write(tmp_git, "dane.txt", mail + "\n" + pem + "\n")
    sha = commit(tmp_git, "dodaj dane")
    assert straznik.scan_history(tmp_git, set()) == [
        f"commit {sha[:7]}: klucz prywatny (BEGIN PRIVATE KEY)", f"commit {sha[:7]}: adres e-mail",
    ]


def test_history_ignores_banned_words_without_list(tmp_git):
    write(tmp_git, "plik.md", "Pozdrawia Żółta Firma\n")
    commit(tmp_git, "dodaj plik")
    assert straznik.scan_history(tmp_git, set()) == []


# --- wartości z plików .env --------------------------------------------------

def test_env_values_found_without_printing(tmp_git, tmp_path):
    value = "wartosc-testowa-" + "x9" * 8  # wymyślona, co najmniej 16 znaków
    env_file = tmp_path / "przyklad.env"
    env_file.write_text('# komentarz\nKLUCZ="' + value + '"\nKROTKI=abc\n', encoding="utf-8")
    write(tmp_git, "ustawienia.md", "a\nklucz = " + value + "\nb\n")
    sha = commit(tmp_git, "dodaj ustawienia")

    values = straznik.env_values(env_file)
    assert values == [value]
    files = straznik.scan_files(tmp_git, set(), values)
    history = straznik.scan_history(tmp_git, set(), values)
    assert files == ["ustawienia.md:2: wartość z .env"]
    assert history == [f"commit {sha[:7]}: wartość z .env"]
    assert value not in "".join(files + history)
    assert straznik.scan_files(tmp_git, set()) == [] and straznik.scan_history(tmp_git, set()) == []


def test_env_values_parsing(tmp_path):
    long_a, long_b, long_c = "a-dluga-wartosc-0123", "b-dluga-wartosc-4567", "c-dluga-wartosc-8901"
    path = tmp_path / "przyklad.env"
    path.write_bytes((
        "﻿# komentarz = " + long_a + "\r\n"
        "\r\n"
        "bez_rownosci_" + long_a + "\r\n"
        "A=" + long_a + "\r\n"
        "export B = '" + long_b + "' \r\n"
        'C="  ' + long_c + '  "\r\n'
        "D=krotka\r\n"
        "E=https://przyklad.example/api?x=1&y=2\r\n"
        "F=" + long_a + " # komentarz po wartości\r\n"
        "G=" + "a" * 15 + "\r\n"
        "H=" + "a" * 16 + "\r\n"
    ).encode("utf-8"))
    # Linia E to publiczny adres bez sekretów: nie daje żadnej wartości do szukania (patrz test adresów niżej).
    assert straznik.env_values(path) == [
        long_a, long_b, long_c, long_a + " # komentarz po wartości", "a" * 16,
    ]


def test_env_values_missing_file_is_an_error_without_echoing_the_path(tmp_path):
    with pytest.raises(straznik.StraznikError) as caught:
        straznik.env_values(tmp_path / "sekretna-nazwa.env")
    assert "sekretna-nazwa" not in str(caught.value)


def test_env_public_url_not_flagged_but_url_token_is(tmp_git, tmp_path, capsys):
    """Publiczny adres API z .env nie daje fałszywych trafień w kodzie, który go legalnie zawiera.

    Sekret schowany w adresie (tu segment ścieżki webhooka) nadal jest wykrywany i nie trafia do wyjścia.
    """
    token = "AbCdEfGhIjKlMnOpQrStUvWx"
    env_file = tmp_path / "przyklad.env"
    env_file.write_text(
        "API_BASE=https://api.example.com/api/v1\n"
        f"HOOK=https://hooks.example.com/services/T000/B000/{token}\n",
        encoding="utf-8",
    )
    write(tmp_git, "docs.md", "Adres API: https://api.example.com/api/v1\n")
    assert straznik.main(["--env-plik", str(env_file)], root=tmp_git) == 0
    out, err = capsys.readouterr()
    assert out == "Strażnik: czysto (pliki).\n"

    write(tmp_git, "hook.md", f"webhook: {token}\n")
    assert straznik.main(["--env-plik", str(env_file)], root=tmp_git) == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == ["hook.md:1: wartość z .env", "Strażnik: trafień: 1 (pliki)."]
    assert token not in out + err


URL_TOKEN = "AbCdEfGhIjKlMnOpQrSt"   # wymyślony, 20 znaków
URL_CASES = [
    # Publiczny adres: schemat, host (też długi), port, krótkie segmenty, nazwy i krótkie wartości parametrów, krótki fragment.
    ("https://api.example.com/api/v1", []),
    ("https://bardzo-dlugi-adres-hosta.example.com:8443/v1/items?limit=50&sort=asc#top", []),
    # Segment ścieżki, wartość parametru zapytania i fragment od 16 znaków.
    (f"https://api.example.com/v1/{URL_TOKEN}/items", [URL_TOKEN]),
    (f"https://api.example.com/v1/items?limit=50&token={URL_TOKEN}&verbose=1", [URL_TOKEN]),
    (f"https://app.example.com/callback#{URL_TOKEN}", [URL_TOKEN]),
    # Nazwa parametru i parametr bez „=” (nie ma wartości) nie są sprawdzane.
    ("https://api.example.com/v1/items?nazwa_parametru_dluga_jak_token&inny_parametr_dlugi=", []),
    # Dane logowania: `user:hasło` w całości (także krótkie), do tego osobno nazwa i hasło od 16 znaków.
    (f"postgres://app:{URL_TOKEN}@db.example.com:5432/appdb", [f"app:{URL_TOKEN}", URL_TOKEN]),
    ("redis://cache:s3cret@example.com/0", ["cache:s3cret"]),
    (f"https://{URL_TOKEN}:x-oauth-basic@example.com/", [f"{URL_TOKEN}:x-oauth-basic", URL_TOKEN]),
    (f"https://{URL_TOKEN}@sentry.example.com/1", [URL_TOKEN]),        # token w miejscu użytkownika
    ("ssh://git@example.com/org/repo.git", []),                        # sama krótka nazwa użytkownika to nie sekret
    # „@” w ścieżce albo w zapytaniu to nie dane logowania.
    (f"https://api.example.com/users/@me/{URL_TOKEN}", [URL_TOKEN]),
    (f"https://api.example.com/v1/items?mail=jan@example.com&t={URL_TOKEN}", [URL_TOKEN]),
    # Wszystko naraz, w kolejności: dane logowania, ścieżka, zapytanie, fragment.
    (
        f"https://u:{URL_TOKEN}1@example.com/{URL_TOKEN}2/x?k={URL_TOKEN}3&l=krotka#{URL_TOKEN}4",
        [f"u:{URL_TOKEN}1", f"{URL_TOKEN}1", f"{URL_TOKEN}2", f"{URL_TOKEN}3", f"{URL_TOKEN}4"],
    ),
    # Komentarz po adresie (` # …`) nie jest fragmentem adresu.
    ("https://api.example.com/api/v1  # publiczny adres API klienta", []),
    (f"https://api.example.com/p/{URL_TOKEN}  # komentarz", [URL_TOKEN]),
]


@pytest.mark.parametrize("line, expected", URL_CASES)
def test_env_values_of_an_address_keep_only_parts_that_can_carry_a_secret(tmp_path, line, expected):
    path = tmp_path / "przyklad.env"
    path.write_text("ADRES=" + line + "\n", encoding="utf-8")
    assert straznik.env_values(path) == expected


def test_env_value_with_an_address_only_in_the_comment_is_still_checked_as_a_whole(tmp_path):
    """„://” w komentarzu nie robi z wartości adresu: sekret przed komentarzem nadal jest sprawdzany."""
    path = tmp_path / "przyklad.env"
    path.write_text(f"KLUCZ={URL_TOKEN} # zob. https://docs.example.com/x\n", encoding="utf-8")
    assert URL_TOKEN in straznik.env_values(path)


# --- lista zakazanych fraz ---------------------------------------------------

def test_load_banned_returns_digests_and_ignores_comments_blanks_and_bom(tmp_path):
    path = tmp_path / "lista.txt"
    path.write_bytes("﻿# prywatna lista\r\n\r\n  Żółta   FIRMA  \r\nŁukasz Ząb\r\n   # inny komentarz\r\nzolta-firma.pl\r\n".encode("utf-8"))
    assert straznik.load_banned(path) == {
        straznik.digest("zolta firma"), straznik.digest("lukasz zab"), straznik.digest("zolta-firma.pl"),
    }


def test_load_banned_rejects_phrases_that_can_never_match_and_reports_only_line_numbers(tmp_path):
    path = tmp_path / "lista.txt"
    path.write_text("# nagłówek\nzolta firma\nala ma kota i psa\n\n@nick\nok\n", encoding="utf-8")
    with pytest.raises(straznik.ListError) as caught:
        straznik.load_banned(path)
    assert caught.value.lines == [3, 5]
    assert "kota" not in str(caught.value) and "nick" not in str(caught.value)


def test_load_banned_rejects_an_empty_list(tmp_path):
    path = tmp_path / "pusta.txt"
    path.write_text("# tylko komentarz\n\n", encoding="utf-8")
    with pytest.raises(straznik.ListError):
        straznik.load_banned(path)


# --- wiersz poleceń ----------------------------------------------------------

def test_cli_without_list_checks_patterns_only(tmp_git, capsys):
    assert straznik.NO_LIST_NOTICE == "Brak listy zakazanych słów: sprawdzam tylko klucze, e-maile i autorów."
    write(tmp_git, "a.md", "Pozdrawia Żółta Firma")
    sha = commit(tmp_git, author=FOREIGN)
    assert straznik.main([], root=tmp_git) == 0                     # bez --historia autorów nie sprawdza
    out, err = capsys.readouterr()
    assert err == straznik.NO_LIST_NOTICE + "\n"
    assert out == "Strażnik: czysto (pliki).\n"

    write(tmp_git, "b.md", "klucz: " + SAMPLES["klucz sk_"])
    assert straznik.main(["--historia"], root=tmp_git) == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "b.md:1: klucz sk_",
        f"commit {sha[:7]}: {FOREIGN_AUTHOR}",
        "Strażnik: trafień: 2 (pliki i historia).",
    ]
    assert straznik.NO_LIST_NOTICE in err
    assert SAMPLES["klucz sk_"] not in out + err


def test_cli_uses_list_from_option_or_environment_and_option_wins(tmp_git, tmp_path, monkeypatch, capsys):
    write(tmp_git, "c.md", "Pozdrawia Żółta Firma")
    lista = tmp_path / "lista.txt"
    lista.write_bytes("﻿# prywatna lista\n\n  Żółta   FIRMA  \n".encode("utf-8"))

    assert straznik.main(["--lista", str(lista)], root=tmp_git) == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == ["c.md:1: słowo z listy", "Strażnik: trafień: 1 (pliki)."]
    assert "Brak listy" not in err and "fraz: 1" in err
    assert "żółta" not in (out + err).lower() and "firma" not in (out + err).lower()

    monkeypatch.setenv(straznik.LIST_ENV, str(lista))
    assert straznik.main([], root=tmp_git) == 1
    capsys.readouterr()

    monkeypatch.setenv(straznik.LIST_ENV, str(tmp_path / "nie-ma.txt"))
    assert straznik.main(["--lista", str(lista)], root=tmp_git) == 1    # opcja ma pierwszeństwo
    capsys.readouterr()


def test_cli_help_lists_the_options(capsys):
    with pytest.raises(SystemExit) as caught:
        straznik.main(["--help"])
    assert caught.value.code == 0
    out = capsys.readouterr().out
    assert "--historia" in out and "--lista" in out and "--env-plik" in out and straznik.LIST_ENV in out


def test_cli_empty_environment_variable_means_no_list(tmp_git, monkeypatch, capsys):
    monkeypatch.setenv(straznik.LIST_ENV, "")
    assert straznik.main([], root=tmp_git) == 0
    assert straznik.NO_LIST_NOTICE in capsys.readouterr().err


def test_cli_invalid_list_exits_2_with_line_numbers_only(tmp_git, tmp_path, capsys):
    lista = tmp_path / "lista.txt"
    lista.write_text("# nagłówek\nzolta firma\nala ma kota i psa\n", encoding="utf-8")
    assert straznik.main(["--lista", str(lista)], root=tmp_git) == 2
    out, err = capsys.readouterr()
    assert out == "" and "linie: 3" in err
    assert "kota" not in err and "psa" not in err


def test_cli_missing_files_exit_2_without_echoing_paths(tmp_git, tmp_path, capsys):
    assert straznik.main(["--lista", str(tmp_path / "sekretna-lista.txt")], root=tmp_git) == 2
    assert straznik.main(["--env-plik", str(tmp_path / "sekretny.env")], root=tmp_git) == 2
    assert "sekretn" not in capsys.readouterr().err


def test_cli_env_plik_reports_without_printing_or_writing_anything(tmp_git, tmp_path, capsys):
    value = "inna-wartosc-testowa-" + "7z" * 6
    env_a = tmp_path / "a.env"
    env_b = tmp_path / "b.env"
    env_a.write_text("KLUCZ=" + value + "\nKROTKI=1\n", encoding="utf-8")
    env_b.write_text("INNY=zupelnie-inna-wartosc-0123\n", encoding="utf-8")
    write(tmp_git, "plik.md", "wartość: " + value + "\n")
    sha = commit(tmp_git, "dodaj plik")

    def names():
        return sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if ".git" not in p.parts)

    before = names()
    code = straznik.main(["--historia", "--env-plik", str(env_a), "--env-plik", str(env_b)], root=tmp_git)
    out, err = capsys.readouterr()
    assert code == 1
    assert out.splitlines() == [
        "plik.md:1: wartość z .env",
        f"commit {sha[:7]}: wartość z .env",
        "Strażnik: trafień: 2 (pliki i historia).",
    ]
    assert value not in out + err and "zupelnie-inna" not in out + err
    assert "Wartości z .env do sprawdzenia: 2." in err
    assert names() == before


def test_cli_history_flag_adds_the_history_scan(tmp_git, capsys):
    sha = commit(tmp_git, author=FOREIGN)
    assert straznik.main([], root=tmp_git) == 0
    capsys.readouterr()
    assert straznik.main(["--historia"], root=tmp_git) == 1
    assert f"commit {sha[:7]}: {FOREIGN_AUTHOR}" in capsys.readouterr().out.splitlines()


def test_cli_outside_a_git_repo_exits_2(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "zwykly-folder"
    folder.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert straznik.main([], root=folder) == 2
    out, err = capsys.readouterr()
    assert out == "" and "git" in err


def test_script_runs_from_tools_folder_of_a_repo_and_does_not_flag_itself(tmp_git):
    (tmp_git / "tools").mkdir()
    shutil.copy(CODE / "tools" / "straznik.py", tmp_git / "tools" / "straznik.py")
    git(tmp_git, "add", "--", "tools/straznik.py")
    commit(tmp_git, "dodaj strażnika")

    def run(*args):
        return subprocess.run(
            [sys.executable, "tools/straznik.py", *args], cwd=tmp_git, capture_output=True,
            text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"},
        )

    clean = run("--historia")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert clean.stdout == "Strażnik: czysto (pliki i historia).\n"
    assert clean.stderr == straznik.NO_LIST_NOTICE + "\n"

    write(tmp_git, "k.md", "klucz: " + SAMPLES["klucz sk_"])
    dirty = run()
    assert dirty.returncode == 1
    assert dirty.stdout.splitlines()[0] == "k.md:1: klucz sk_"
    assert SAMPLES["klucz sk_"] not in dirty.stdout + dirty.stderr
