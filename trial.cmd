@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" goto brak
rem Kod wyjscia programu idzie dalej przez exit /b %errorlevel% w nastepnej linii
rem (samo "& exit /b" w linii z Pythonem oddaje 0, sprawdzone na Windowsie).
".venv\Scripts\python.exe" -m trial_reels %*
exit /b %errorlevel%
:brak
>&2 echo Brak srodowiska Pythona (.venv). Najpierw krok 1: .claude/skills/trial-reels/kroki/01-programy.md
exit /b 3
