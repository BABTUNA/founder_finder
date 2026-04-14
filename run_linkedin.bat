@echo off
REM Run the LinkedIn company scraper
REM Pass LinkedIn company URLs as arguments or use a file

setlocal

set OUTDIR=data
if not exist %OUTDIR% mkdir %OUTDIR%

for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set DATESTAMP=%%c_%%a_%%b

set OUTFILE=%OUTDIR%\linkedin_companies_%DATESTAMP%.json

echo ============================================
echo   LinkedIn Company Scraper
echo ============================================
echo.
echo Output file: %OUTFILE%
echo.

REM Usage: run_linkedin.bat <url1> [url2] ...
REM   or:  run_linkedin.bat --file companies.txt
python linkedin_scraper.py %* -o %OUTFILE%

echo.
echo Done! Results saved to %OUTFILE%
pause
