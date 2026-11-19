#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
elif [ -f .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe
else
  echo "Brak środowiska Pythona (.venv). Najpierw krok 1: .claude/skills/trial-reels/kroki/01-programy.md" >&2
  exit 3
fi
exec "$PY" -m trial_reels "$@"
