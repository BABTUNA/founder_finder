@echo off
REM Run the Luma scraper for all popular tech cities
REM Output is saved to a timestamped JSON file in the data/ folder

setlocal

REM Generate timestamp for the filename
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set DATESTAMP=%%c_%%a_%%b
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set TIMESTAMP=%%a%%b

set OUTDIR=data
if not exist %OUTDIR% mkdir %OUTDIR%

set OUTFILE=%OUTDIR%\luma_events_%DATESTAMP%.json

echo ============================================
echo   Luma Event Scraper - All Cities
echo ============================================
echo.
echo Output file: %OUTFILE%
echo.

python luma_scraper_app.py --category both -o %OUTFILE%

echo.
echo Done! Results saved to %OUTFILE%
pause
