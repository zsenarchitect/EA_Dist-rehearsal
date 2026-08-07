@echo off
REM InfraWatch collector launcher. Finds a usable Python 3 and runs collect_all.py.
REM Forwards all args (e.g. --heavy, --events-only) to the script.
REM
REM 2026-04-22: now PROPAGATES the Python exit code (was `exit /b 0` regardless,
REM which is exactly the wrapper-exit-masking trap from feedback_exit_code_not_proof_of_success.md).
REM Task Scheduler's "Last Result" should reflect actual collector outcome, not whether the bat ran.
REM The "no Python interpreter found" branch still exits 0 because that is a deployment gap,
REM not a per-run failure to alarm on.

setlocal
set SCRIPT_DIR=%~dp0
set COLLECT=%SCRIPT_DIR%collect_all.py

REM 1. EnneadTab-OS dev venv (present on szhang canary machine)
set VENV=%SCRIPT_DIR%..\..\..\..\..\.venv\Scripts\pythonw.exe
if exist "%VENV%" (
    "%VENV%" "%COLLECT%" %* >nul 2>&1
    exit /b %ERRORLEVEL%
)

REM 2. Python Launcher (reliable on workstations with Python 3)
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 "%COLLECT%" %* >nul 2>&1
    exit /b %ERRORLEVEL%
)

REM 3. python.exe on PATH
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python "%COLLECT%" %* >nul 2>&1
    exit /b %ERRORLEVEL%
)

REM 4. Fallback to legacy InfraWatch_Collect.exe if Python is not on PATH.
REM    The exe bundles its own CPython interpreter (PyInstaller) so it works
REM    even on machines with no system Python. This path only activates on
REM    machines outside the standard office image.
set LEGACY_EXE=%SCRIPT_DIR%..\..\ExeProducts\InfraWatch_Collect.exe
if exist "%LEGACY_EXE%" (
    "%LEGACY_EXE%" %* >nul 2>&1
    exit /b %ERRORLEVEL%
)

REM 5. No Python and no exe found. Exit 0 so Task Scheduler does not alarm on every cycle for
REM what is really a one-time deployment-gap problem (would need ErrorDump to surface).
exit /b 0
