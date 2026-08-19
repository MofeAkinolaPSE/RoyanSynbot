@echo off
REM Double-click launcher for scan_hope_source.py.
REM Run this WHILE connected to the client VPN with the Hope share mounted.
REM It only reads the share and writes a local report — safe to interrupt
REM (close this window) and re-run later; it resumes where it left off.

setlocal
set ROOT=%1
if "%ROOT%"=="" set ROOT=Z:\

echo Scanning %ROOT% ...
echo (Close this window any time — progress is saved and re-running resumes.)
echo.

cd /d "%~dp0\.."
python scripts\scan_hope_source.py "%ROOT%"

echo.
echo Done. Report is in data-assimilation\scan_reports\
pause
