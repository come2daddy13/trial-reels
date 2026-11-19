"""Testy stanu operacyjnego: odczyt i zapis w UTF-8, numery wersji i blokada przed jednoczesnym zapisem."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import filelock
import pytest

from trial_reels import config, state

CODE = Path(__file__).resolve().parents[1]
EMPTY = {"seq": 0, "versions": {}, "brake": {"on": False}}

# Drugi proces: bierze blokadę, zgłasza to w stdout i trzyma ją, dopóki nie dostanie linii na stdin.
HOLDER = (
    "import sys\n"
    "from trial_reels import state\n"
    "with state.locked() as st:\n"
    "    st['versions']['z-podprocesu'] = {'note': 'ok'}\n"
    "    print('zajete', flush=True)\n"
    "    sys.stdin.readline()\n"
)


# --- odczyt i zapis ----------------------------------------------------------

def test_state_roundtrip_utf8_and_lock():
    with state.locked() as st:
        st["versions"]["TR-001"] = {"note": "żółć 🔥"}
    assert state.load()["versions"]["TR-001"]["note"] == "żółć 🔥"
    with state.locked():
        pass


def test_load_without_file_gives_fresh_empty_state_and_writes_nothing():
    first = state.load()
    assert first == EMPTY and not config.DATA.exists()
    first["versions"]["TR-001"] = {}
    assert state.load() == EMPTY


def test_save_then_load_without_lock():
    st = {"seq": 3, "versions": {"TR-003": {"note": "Zażółć gęślą jaźń"}}, "brake": {"on": True}}
    state.save(st)
    assert state.load() == st


def test_state_file_is_utf8_json_with_unix_newlines_and_leaves_no_temp_files():
    state.save({"seq": 1, "versions": {"TR-001": {"note": "żółć 🔥"}}, "brake": {"on": False}})
    raw = config.STATE.read_bytes()
    assert "żółć 🔥".encode("utf-8") in raw and b"\r" not in raw
    assert json.loads(raw.decode("utf-8"))["seq"] == 1
    assert [p.name for p in config.DATA.iterdir() if p.suffix == ".tmp"] == []


def test_state_in_folder_with_polish_letters_and_space(tmp_path):
    config.use_root(tmp_path / "Łukasz Ząb" / "trial-reels")
    with state.locked() as st:
        st["versions"][state.next_id(st)] = {"note": "Zażółć gęślą jaźń 🔥"}
    assert config.STATE.is_file() and "Łukasz Ząb" in str(config.STATE)
    assert state.load()["versions"]["TR-001"]["note"] == "Zażółć gęślą jaźń 🔥"


def test_state_with_bom_is_readable():
    config.DATA.mkdir(parents=True)
    config.STATE.write_bytes(b"\xef\xbb\xbf" + json.dumps({"seq": 7, "versions": {}, "brake": {"on": True}}).encode("utf-8"))
    st = state.load()
    assert st["seq"] == 7 and st["brake"]["on"] is True


def test_broken_state_file_is_reported_and_left_untouched():
    config.DATA.mkdir(parents=True)
    config.STATE.write_text("{nie json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError, match="stan.json"):
        state.load()
    with pytest.raises(json.JSONDecodeError, match="stan.json"):
        with state.locked():
            pass
    assert config.STATE.read_text(encoding="utf-8") == "{nie json"  # uszkodzonego stanu nie nadpisujemy pustym
    config.STATE.write_text(json.dumps(EMPTY), encoding="utf-8")
    with state.locked():  # po błędzie blokada jest zwolniona
        pass


# --- numery wersji -----------------------------------------------------------

def test_next_id_numbers_versions_in_order():
    st = {"seq": 0, "versions": {}, "brake": {"on": False}}
    assert [state.next_id(st) for _ in range(3)] == ["TR-001", "TR-002", "TR-003"]
    assert st["seq"] == 3
    st["seq"] = 999
    assert state.next_id(st) == "TR-1000"
    assert state.next_id({}) == "TR-001"


def test_ids_keep_counting_after_reload():
    with state.locked() as st:
        assert [state.next_id(st) for _ in range(2)] == ["TR-001", "TR-002"]
    with state.locked() as st:
        assert state.next_id(st) == "TR-003"


# --- blokada -----------------------------------------------------------------

def test_lock_file_lives_in_data_folder():
    with state.locked():
        assert (config.DATA / ".stan.lock").is_file()


def test_locked_saves_changes_only_when_block_finishes():
    with state.locked() as st:
        st["seq"] = 1
    with pytest.raises(RuntimeError):
        with state.locked() as st:
            st["seq"] = 99
            raise RuntimeError("przerwane")
    assert state.load()["seq"] == 1
    with state.locked():  # po błędzie blokada jest zwolniona
        pass


def test_lock_keeps_other_processes_out_until_released():
    env = {**os.environ, "PYTHONUTF8": "1", "TRIAL_REELS_ROOT": str(config.ROOT)}
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER], cwd=CODE, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    watchdog = threading.Timer(60, holder.kill)  # gdyby proces utknął, test ma się wywalić, a nie wisieć
    watchdog.start()
    try:
        assert holder.stdout.readline().strip() == "zajete", holder.stderr.read()
        other = filelock.FileLock(str(config.DATA / ".stan.lock"), timeout=0.3)
        with pytest.raises(filelock.Timeout):
            other.acquire()
        holder.stdin.write("\n")
        holder.stdin.flush()
        _, err = holder.communicate(timeout=60)
        assert holder.returncode == 0, err
        with state.locked() as st:
            assert st["versions"]["z-podprocesu"] == {"note": "ok"}
    finally:
        watchdog.cancel()
        if holder.poll() is None:
            holder.kill()
            holder.communicate()


def test_parallel_writers_lose_no_updates():
    def write_five():
        for _ in range(5):
            with state.locked() as st:
                st["versions"][state.next_id(st)] = {"n": 1}

    threads = [threading.Thread(target=write_five, daemon=True) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    final = state.load()
    assert final["seq"] == 30 and len(final["versions"]) == 30
