@echo off
REM ============================================================
REM  M11 only.
REM
REM  The services in scripts\services.txt whose id starts with
REM  m11-. Upstream modules are NOT started - each one is
REM  optional and /v1/deps says which are missing. Use
REM  start_all.bat to bring up the siblings as well.
REM
REM  Usage:  start_voice.bat         launch M11
REM          start_voice.bat -Check  verify prerequisites only
REM ============================================================

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" -Only m11 -Title "M11 - Voice Engine" %*
