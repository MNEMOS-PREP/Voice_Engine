@echo off
setlocal
cd /d "%~dp0"

REM ============================================================
REM  Dispatcher. The launchers are start_all.bat and
REM  start_voice.bat; this file stays because README.md,
REM  PORTS.txt and dependencies.txt all tell you to type
REM  `start.bat`.
REM
REM    start.bat            everything          -> start_all.bat
REM    start.bat voice      this module only    -> start_voice.bat
REM    start.bat m11        same thing
REM    start.bat check      prerequisites, launch nothing
REM
REM  What actually runs the services: scripts\launch.ps1
REM  What you add a service to:       scripts\services.txt
REM  What closes them again:          scripts\control.ps1
REM ============================================================

if /i "%~1"=="check" goto CHECK
if /i "%~1"=="voice" goto ONLY
if /i "%~1"=="m11"   goto ONLY
if /i "%~1"=="all"   goto ALL
if "%~1"==""         goto ALL
goto USAGE

:ALL
call "%~dp0start_all.bat"
exit /b %errorlevel%

:ONLY
call "%~dp0start_voice.bat"
exit /b %errorlevel%

:CHECK
call "%~dp0start_all.bat" -Check
exit /b %errorlevel%

:USAGE
echo.
echo   Unknown option "%~1".
echo.
echo     start.bat            everything
echo     start.bat voice      M11 only  ^(same as start_voice.bat^)
echo     start.bat check      verify prerequisites, launch nothing
echo.
exit /b 1
