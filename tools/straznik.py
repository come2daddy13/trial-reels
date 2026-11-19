"""Strażnik danych: sprawdza pliki repo i historię gita pod kątem kluczy API, adresów e-mail,
obcych autorów commitów, dat commitów spoza UTC i fraz z prywatnej listy.

Uruchomienie z katalogu repo:

    python tools/straznik.py [--historia] [--lista PLIK] [--env-plik PLIK]...

Kod wyjścia: 0 gdy czysto, 1 przy trafieniu, 2 przy błędzie (zła lista, brak pliku, git).

Strażnik nigdy nie wypisuje trafienia ani wartości, tylko miejsce i powód:

    plik:linia: powód        (linia 0 oznacza samą nazwę pliku)
    commit <sha7>: powód

Prywatna lista leży poza repo: jedna fraza na linię, `#` zaczyna komentarz. Strażnik zamienia każdą frazę
na skrót SHA-256 w pamięci i porównuje skróty, więc treść fraz nie trafia na ekran ani na dysk.

Wartości z plików .env (`--env-plik`) strażnik szuka jako dosłownych podciągów. Wartość od 16 znaków wchodzi
w całości, a wartość z „://” to adres: wchodzą z niego tylko części, które mogą nieść sekret (dane logowania
przed „@”, segmenty ścieżki, wartości parametrów zapytania i fragment po „#”). Publiczny adres API nie daje
więc trafień w kodzie, który go legalnie zawiera. Wartości zostają w pamięci: nie są wypisywane ani zapisywane.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Jedyna tożsamość, jaką może mieć autor i committer każdego commita.
ALLOWED_IDENTITY = "Trial Reels <trial-reels@users.noreply.github.com>"
# Pliki binarne pomijamy w skanie plików (zdjęcia, czcionki, archiwa, wideo).
SKIPPED_EXTENSIONS = frozenset({".png", ".ttf", ".zip", ".ico", ".mp4"})
LIST_ENV = "TRIAL_REELS_STRAZNIK_LISTA"
MIN_ENV_VALUE = 16
_COMMENT_MARK = " #"   # po wartości w .env zaczyna komentarz
NO_LIST_NOTICE = "Brak listy zakazanych słów: sprawdzam tylko klucze, e-maile i autorów."

REASON_WORD = "słowo z listy"
REASON_ENV = "wartość z .env"
REASON_AUTHOR = "autor spoza dozwolonej tożsamości"
REASON_COMMITTER = "committer spoza dozwolonej tożsamości"
# Strefa czasowa w dacie commita zdradza, gdzie był autor, więc w historii są tylko daty w UTC.
ALLOWED_ZONE = "+0000"
REASON_AUTHOR_ZONE = "data autora w strefie innej niż +0000"
REASON_COMMITTER_ZONE = "data committera w strefie innej niż +0000"

# Adres e-mail spoza dozwolonych: `noreply@anthropic.com`, `*@users.noreply.github.com`, `*@example.com`.
# Dozwolony adres musi się kończyć na granicy domeny (po nim nie ma już znaku domeny ani „.litera”),
# więc adres z dłuższą domeną, na przykład z dopiskiem kraju po example.com, nie przechodzi.
# Część lokalna zaczyna się od litery lub cyfry, więc `+@pytest.fixture` (dekorator ze znacznikiem diffu)
# nie jest adresem, a adres tuż po `+`, `-` albo `_` nadal jest. Jedna litera po backslashu to sekwencja
# ucieczki (w kodzie i JSON-ie podpis z nickiem po łamaniu linii wygląda jak `\n@nick.konto`), a nie adres.
_EMAIL_LOCAL = r"[A-Za-z0-9][A-Za-z0-9._%+-]*"
_ALLOWED_EMAIL = (
    r"(?:noreply@anthropic\.com"
    rf"|{_EMAIL_LOCAL}@(?:users\.noreply\.github\.com|example\.com))"
)
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?!(?<=\\)[A-Za-z0-9]@)"
    rf"(?!{_ALLOWED_EMAIL}(?![A-Za-z0-9-]|\.[A-Za-z0-9]))"
    rf"{_EMAIL_LOCAL}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{{2,}}",
    re.IGNORECASE,
)

# Prefiks klucza zaczyna się na granicy: przed nim nie stoi litera ani cyfra. Prawdziwy klucz zawsze ma
# przed sobą separator (spację, `=`, cudzysłów), a bez granicy każdy identyfikator `mask_…` czy `task_…`
# z długim ogonem wyglądałby jak klucz z prefiksem sk_.
_B = r"(?<![A-Za-z0-9])"

# Nazwa wzorca jest powodem trafienia w wyniku.
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "klucz sk_": re.compile(_B + r"sk_[A-Za-z0-9_-]{16,}"),
    "klucz sk-ant-": re.compile(_B + r"sk-ant-[A-Za-z0-9_-]{10,}"),
    "token ntn_": re.compile(_B + r"ntn_[A-Za-z0-9]{20,}"),
    "token secret_": re.compile(_B + r"secret_[A-Za-z0-9]{20,}"),
    "token GitHub (gh?_)": re.compile(_B + r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "token GitHub github_pat_": re.compile(_B + r"github_pat_[A-Za-z0-9_]{20,}"),
    "klucz AWS AKIA": re.compile(_B + r"AKIA[0-9A-Z]{16}"),
    "klucz prywatny (BEGIN PRIVATE KEY)": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "token Slack xox": re.compile(_B + r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    "adres e-mail": _EMAIL,
}

# Kolejność powodów w wyniku: wzorce, potem lista, potem wartości z .env.
_REASON_ORDER = [*SECRET_PATTERNS, REASON_WORD, REASON_ENV]
_REASON_RANK = {reason: rank for rank, reason in enumerate(_REASON_ORDER)}

_WORD = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")
_JOINERS = re.compile(r"[-_.]")

# Separatory pól w wyniku `git log`: nie występują w zwykłych komunikatach i diffach.
_RECORD, _FIELD = "\x1e", "\x1f"
_LOG_FORMAT = "%x1e%H%x1f%an%x1f%ae%x1f%ai%x1f%cn%x1f%ce%x1f%ci%x1f%B%x1f"


class StraznikError(Exception):
    """Błąd kończący strażnika kodem 2. Komunikat nie zawiera trafień, wartości ani ścieżek prywatnych plików."""


class ListError(StraznikError):
    """Prywatna lista jest nieczytelna, pusta albo ma frazy, których nie da się porównać z tekstem."""

    def __init__(self, message: str, lines: Iterable[int] = ()):
        super().__init__(message)
        self.lines = list(lines)


class GitError(StraznikError):
    """Polecenie git nie zadziałało (brak gita, to nie jest repo, błąd odczytu)."""


# --- tokeny i skróty ---------------------------------------------------------

def normalize(text: str) -> str:
    """Małe litery bez znaków diakrytycznych, a „ł” jako „l”: „Żółta Firma” daje „zolta firma”."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return plain.replace("ł", "l")


def _token_stream(text: str) -> Iterator[tuple[str, int]]:
    """Tokeny razem z numerem linii (od 1), na której się zaczynają.

    Token to słowo (`[a-z0-9]+` łączone znakami `-`, `_` albo `.`), jego część albo n-gram z 2 lub 3
    kolejnych części, połączonych spacją. N-gramy przechodzą przez koniec linii, więc fraza zawinięta
    w połowie też zostaje znaleziona (numer linii to jej początek).
    """
    parts: list[tuple[str, int]] = []
    for number, line in enumerate(text.split("\n"), start=1):
        for match in _WORD.finditer(normalize(line)):
            word = match.group()
            pieces = _JOINERS.split(word)
            if len(pieces) > 1:
                yield word, number
            for piece in pieces:
                yield piece, number
                parts.append((piece, number))
    for size in (2, 3):
        for start in range(len(parts) - size + 1):
            yield " ".join(piece for piece, _ in parts[start:start + size]), parts[start][1]


def tokens(text: str) -> set[str]:
    """Wszystkie tokeny tekstu (po normalizacji): słowa, ich części oraz bigramy i trigramy części."""
    return {token for token, _ in _token_stream(text)}


def digest(token: str) -> str:
    """Skrót SHA-256 (hex) tokenu zapisanego w UTF-8."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- skan tekstu -------------------------------------------------------------

def _scan_text(text: str, banned: set[str], values: list[str]) -> list[tuple[int, str]]:
    """Trafienia w tekście jako (numer linii, powód). Ten sam powód zgłaszamy najwyżej raz na linię."""
    hits: set[tuple[int, str]] = set()
    for number, line in enumerate(text.split("\n"), start=1):
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                hits.add((number, name))
        if any(value in line for value in values):
            hits.add((number, REASON_ENV))
    if banned:
        hits.update((number, REASON_WORD) for token, number in _token_stream(text) if digest(token) in banned)
    return sorted(hits, key=lambda hit: (hit[0], _REASON_RANK[hit[1]]))


def _reasons(text: str, banned: set[str], values: list[str]) -> list[str]:
    """Powody trafień w tekście bez numerów linii, w stałej kolejności."""
    found = {reason for _, reason in _scan_text(text, banned, values)}
    return [reason for reason in _REASON_ORDER if reason in found]


def _git(root: Path, *args: str) -> bytes:
    try:
        done = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=root, capture_output=True, stdin=subprocess.DEVNULL,
        )
    except OSError:
        raise GitError("nie można uruchomić gita w tym folderze") from None
    if done.returncode != 0:
        lines = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise GitError(f"git {args[0]} zakończył się błędem" + (f": {lines[0]}" if lines else ""))
    return done.stdout


def _tracked_files(root: Path) -> list[str]:
    raw = _git(root, "ls-files", "-z")
    names = (os.fsdecode(chunk) for chunk in raw.split(b"\0") if chunk)
    return [name for name in names if Path(name).suffix.lower() not in SKIPPED_EXTENSIONS]


def _read_text(path: Path) -> str | None:
    """Treść pliku jako tekst UTF-8 (błędne bajty zamieniamy); dla dowiązania tekst jego celu. Brak pliku daje None."""
    try:
        if path.is_symlink():
            return os.readlink(path)
        return path.read_bytes().decode("utf-8", errors="replace")
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return None  # plik jest w indeksie, ale nie na dysku, albo to podmoduł
    except OSError:
        raise StraznikError("nie można odczytać pliku z repo (brak uprawnień?)") from None


def scan_files(root: Path, banned: set[str], values: Iterable[str] = ()) -> list[str]:
    """Sprawdza pliki z `git ls-files` i ich nazwy. Zwraca wpisy „plik:linia: powód” (linia 0 to nazwa pliku).

    `banned` to skróty fraz (patrz `digest`), `values` to wartości z .env szukane jako dosłowne podciągi.
    Samego trafienia nie zwraca nigdy.
    """
    root = Path(root)
    wanted = [value for value in values if value]
    entries: list[str] = []
    for name in _tracked_files(root):
        entries.extend(f"{name}:0: {reason}" for reason in _reasons(name, banned, wanted))
        text = _read_text(root / name)
        if text is not None:
            entries.extend(f"{name}:{number}: {reason}" for number, reason in _scan_text(text, banned, wanted))
    return entries


def scan_history(root: Path, banned: set[str], values: Iterable[str] = ()) -> list[str]:
    """Przegląda `git log --all -p` razem z treścią commitów. Zwraca wpisy „commit <sha7>: powód”.

    Zgłasza autora i committera innych niż `ALLOWED_IDENTITY`, daty autora i committera w strefie innej niż
    +0000, a w komunikacie i zmianach commita te same trafienia co `scan_files`. Każdy powód pojawia się
    najwyżej raz na commit. Commit scalający nie ma własnego diffu (jak w `git log -p`): jego treść
    sprawdzamy w commitach, z których powstała.
    """
    root = Path(root)
    wanted = [value for value in values if value]
    raw = _git(
        root, "log", "--all", "-p", "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
        "--no-show-signature", "--encoding=UTF-8", f"--format={_LOG_FORMAT}",
    )
    entries: list[str] = []
    for record in raw.decode("utf-8", errors="replace").split(_RECORD):
        if not record.strip():
            continue
        fields = record.split(_FIELD, 8)
        fields += [""] * (9 - len(fields))
        (sha, author_name, author_email, author_date, committer_name, committer_email, committer_date,
         message, patch) = fields
        reasons = []
        if f"{author_name} <{author_email}>" != ALLOWED_IDENTITY:
            reasons.append(REASON_AUTHOR)
        if f"{committer_name} <{committer_email}>" != ALLOWED_IDENTITY:
            reasons.append(REASON_COMMITTER)
        if not author_date.strip().endswith(ALLOWED_ZONE):
            reasons.append(REASON_AUTHOR_ZONE)
        if not committer_date.strip().endswith(ALLOWED_ZONE):
            reasons.append(REASON_COMMITTER_ZONE)
        reasons += _reasons(message + "\n" + patch, banned, wanted)
        entries.extend(f"commit {sha.strip()[:7]}: {reason}" for reason in reasons)
    return entries


# --- prywatna lista i wartości z .env ----------------------------------------

def load_banned(path: str | os.PathLike) -> set[str]:
    """Wczytuje prywatną listę fraz i zwraca ich skróty (treść fraz zostaje tylko w pamięci).

    Linia pusta albo zaczynająca się od `#` jest pomijana. Fraza przechodzi tę samą normalizację co tekst,
    ze spacjami zwiniętymi do jednej. Fraza, której nie ma wśród `tokens(fraza)` (np. 4 słowa albo znak
    specjalny), nigdy nie znalazłaby się w tekście, więc to błąd. Zgłaszamy go samymi numerami linii.
    """
    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        raise ListError("nie można odczytać pliku listy zakazanych słów") from None
    banned: set[str] = set()
    bad: list[int] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        phrase = " ".join(normalize(line).split())
        if phrase in tokens(phrase):
            banned.add(digest(phrase))
        else:
            bad.append(number)
    if bad:
        raise ListError(
            "lista zakazanych słów: nieprawidłowe linie: " + ", ".join(map(str, bad))
            + " (fraza ma mieć od 1 do 3 słów z liter i cyfr; inne znaki nie przejdą porównania)",
            bad,
        )
    if not banned:
        raise ListError("lista zakazanych słów jest pusta")
    return banned


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def _address_parts(address: str) -> list[str]:
    """Części adresu (tekstu z „://”), które mogą nieść sekret. Reszta to publiczny adres, który kod legalnie zawiera.

    Zwraca: dane logowania przed „@” (`user:hasło` w całości, także krótkie, oraz osobno nazwę i hasło od 16 znaków),
    segmenty ścieżki, wartości parametrów zapytania (po „=”) i fragment po „#”, każde od 16 znaków. Pomija schemat,
    host, port, nazwy parametrów, parametry bez wartości oraz krótkie części. Sama krótka nazwa użytkownika
    (`git@…`) to nie sekret.
    """
    rest = address.split("://", 1)[1]
    rest, _, fragment = rest.partition("#")
    rest, _, query = rest.partition("?")
    authority, _, path = rest.partition("/")
    parts: list[str] = []
    userinfo, at, _ = authority.rpartition("@")
    if at:
        name, _, password = userinfo.partition(":")
        if password:
            parts.append(userinfo)
        parts += [piece for piece in (name, password) if len(piece) >= MIN_ENV_VALUE]
    plain = [*path.split("/"), *(pair.partition("=")[2] for pair in query.split("&")), fragment]
    return parts + [part for part in plain if len(part) >= MIN_ENV_VALUE]


def _env_parts(value: str) -> list[str]:
    """Co z jednej wartości z .env szukamy w repo: całą wartość od 16 znaków, a z adresu tylko części niosące sekret.

    Wartość zawierająca „://” (przed ewentualnym komentarzem ` # …`) to adres. Szukany w całości dawałby fałszywe
    trafienia w kodzie, który publiczny adres API legalnie zawiera.
    """
    address = value.split(_COMMENT_MARK, 1)[0].strip()
    if "://" in address:
        return _address_parts(address)
    return [value] if len(value) >= MIN_ENV_VALUE else []


def env_values(path: str | os.PathLike) -> list[str]:
    """Wartości z pliku .env do znalezienia w repo (po pierwszym „=”, bez cudzysłowów i spacji na brzegach).

    Wartość od 16 znaków wchodzi w całości. Wartość z „://” to adres: wchodzą z niego tylko części, które mogą
    nieść sekret (patrz `_address_parts`). Gdy po wartości stoi komentarz (` # …`), sprawdzamy ją w całości
    i samą wartość przed komentarzem. Wartości trafiają tylko do pamięci.
    """
    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        raise StraznikError("nie można odczytać pliku .env") from None
    found: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        raw = line.split("=", 1)[1]
        candidates = [_unquote(raw)]
        if _COMMENT_MARK in raw:
            candidates.append(_unquote(raw.split(_COMMENT_MARK, 1)[0]))
        for value in candidates:
            for part in _env_parts(value):
                if part not in found:
                    found.append(part)
    return found


# --- wiersz poleceń ----------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="straznik",
        description="Strażnik danych: klucze, e-maile, obcy autorzy i frazy z prywatnej listy.",
        epilog="Kody wyjścia: 0 czysto, 1 trafienie, 2 błąd. Trafień ani wartości nie wypisuję.",
    )
    parser.add_argument("--historia", action="store_true",
                        help="sprawdź też historię gita (wszystkie gałęzie) i autorów commitów")
    parser.add_argument("--lista", metavar="PLIK",
                        help=f"prywatna lista zakazanych fraz, jedna na linię (albo zmienna {LIST_ENV})")
    parser.add_argument("--env-plik", metavar="PLIK", action="append", default=[], dest="env_pliki",
                        help="plik .env: jego wartości (od 16 znaków; z adresów tylko części niosące sekret) "
                             "nie mogą wystąpić w repo; można podać kilka razy")
    return parser


def main(argv: list[str] | None = None, root: str | os.PathLike | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(root) if root is not None else ROOT
    scope = "pliki i historia" if args.historia else "pliki"
    try:
        list_path = args.lista or os.environ.get(LIST_ENV)
        banned: set[str] = set()
        if list_path:
            banned = load_banned(list_path)
            print(f"Lista zakazanych słów: fraz: {len(banned)}.", file=sys.stderr)
        else:
            print(NO_LIST_NOTICE, file=sys.stderr)
        values: list[str] = []
        for number, env_path in enumerate(args.env_pliki, start=1):
            try:
                values += [value for value in env_values(env_path) if value not in values]
            except StraznikError as err:
                raise StraznikError(f"--env-plik nr {number}: {err}") from None
        if args.env_pliki:
            print(f"Wartości z .env do sprawdzenia: {len(values)}.", file=sys.stderr)
        entries = scan_files(root, banned, values)
        if args.historia:
            entries += scan_history(root, banned, values)
    except StraznikError as err:
        print(f"Strażnik: {err}", file=sys.stderr)
        return 2
    for entry in entries:
        print(entry)
    if entries:
        print(f"Strażnik: trafień: {len(entries)} ({scope}).")
        return 1
    print(f"Strażnik: czysto ({scope}).")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
