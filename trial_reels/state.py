"""Stan operacyjny: wersje rolek, terminy i ID postów (plik dane/stan.json).

Odczyt i zapis w UTF-8. Zmiany robimy w bloku `with locked() as st:`: blokada pilnuje, żeby dwa uruchomienia
naraz nie nadpisały sobie stanu.

Pakiet filelock ładuje się dopiero w `locked()`. Komenda `aktualizuj` importuje ten moduł, a nie może załadować
żadnego pakietu spoza biblioteki standardowej (na Windowsie uv nie podmieni bibliotek, które proces ma załadowane).
"""
from __future__ import annotations

import contextlib

from . import config


def _empty() -> dict:
    return {"seq": 0, "versions": {}, "brake": {"on": False}}


@contextlib.contextmanager
def locked():
    """Wyłączny dostęp do stanu: drugi proces czeka, nie nadpisuje. Stan zapisuje się przy wyjściu z bloku bez błędu."""
    from filelock import FileLock  # dopiero tu (patrz opis modułu)

    config.DATA.mkdir(parents=True, exist_ok=True)
    with FileLock(str(config.DATA / ".stan.lock")):
        st = load()
        yield st
        save(st)


def load() -> dict:
    """Czyta stan (UTF-8). Gdy pliku nie ma, zwraca pusty stan. Uszkodzony plik zgłasza błąd z jego ścieżką."""
    st = config.read_json(config.STATE, None)
    return _empty() if st is None else st


def save(st: dict) -> None:
    """Zapisuje stan atomowo (UTF-8): najpierw plik tymczasowy obok, potem podmiana."""
    config.write_json(config.STATE, st)


def next_id(st: dict) -> str:
    """Kolejny numer wersji (TR-001, TR-002…). Licznik `seq` rośnie w stanie, więc zapisz go po wywołaniu."""
    st["seq"] = int(st.get("seq", 0)) + 1
    return "TR-%03d" % st["seq"]
