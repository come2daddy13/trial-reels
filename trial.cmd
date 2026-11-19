@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" goto brak
rem Python i wyjscie w jednej linii: cmd.exe czyta ten plik linia po linii, wiec aktualizacja, ktora go
rem podmieni w trakcie dzialania programu, nie da mu do wykonania reszty nowego pliku.
".venv\Scripts\python.exe" -m trial_reels %* & exit /b
:brak
>&2 echo Brak srodowiska Pythona (.venv). Najpierw krok 1: .claude/skills/trial-reels/kroki/01-programy.md
exit /b 3
