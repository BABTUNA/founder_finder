@echo off
setlocal EnableExtensions
REM Launch Chrome with remote debugging so Playwright can connect_over_cdp.
REM Must use ONE LINE for start+chrome+args — multi-line ^ continuations often drop flags on Windows.

echo ============================================
echo   Starting Chrome with Remote Debugging
echo ============================================
echo.

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
    echo ERROR: chrome.exe not found. Install Google Chrome or edit this script with the correct path.
    pause
    exit /b 1
)

set "UD=%LOCALAPPDATA%\Google\Chrome\User Data"

echo Closing existing Chrome instances...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Launching Chrome on debug port 9222...
REM Window title is first quoted arg to START; exe path must be quoted; user-data-dir needs quotes (spaces in "User Data").
start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%UD%" --profile-directory=Default --no-first-run

echo Waiting until http://127.0.0.1:9222 responds...
set /a n=0
:waitloop
curl.exe -s -f "http://127.0.0.1:9222/json/version" >nul 2>&1
if not errorlevel 1 goto debugok
set /a n+=1
if %n% geq 45 goto debugfail
timeout /t 1 /nobreak >nul
goto waitloop

:debugfail
echo.
echo ERROR: Nothing is listening on port 9222 after ~45s.
echo Chrome may have failed to start with remote debugging, or the launch line dropped arguments.
echo Try: close all Chrome windows, run this script again, then run triage with --cdp
pause
exit /b 1

:debugok
echo OK: remote debugging port 9222 is up.
echo.
echo ============================================
echo  Now run in another terminal, for example:
echo    python triage_linkedin.py companies.txt -o triage.csv --resume --cdp
echo.
echo  Leave Chrome running. Close this window when done.
echo ============================================
pause
endlocal
