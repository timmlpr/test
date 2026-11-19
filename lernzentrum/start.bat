@echo off
rem Lernzentrum – Doppelklick startet alles (Docker Desktop, sonst Python/Node direkt).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
