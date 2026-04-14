@echo off
REM Launch Chrome with remote debugging enabled so the scraper can connect.
REM This will close any existing Chrome instances first.

echo ============================================
echo   Starting Chrome with Remote Debugging
echo ============================================
echo.

REM Kill all existing Chrome instances (required — Chrome ignores the
REM debug flag if another instance is already running with this profile)
echo Closing existing Chrome instances...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Launching Chrome on debug port 9222...
echo.

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" ^
    --profile-directory="Default" ^
    --no-first-run

REM Wait a moment for Chrome to start
timeout /t 3 /nobreak >nul

echo ============================================
echo  Chrome is running with debug port 9222
echo.
echo  Now run the scraper in another terminal:
echo    python linkedin_scraper.py --file companies.txt -o results.json
echo.
echo  Close this window when you're done.
echo ============================================
pause
