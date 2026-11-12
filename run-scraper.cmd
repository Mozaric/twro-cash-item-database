@echo off
rem Run the scraper locally, then commit and push docs/ changes.
rem Usage:
rem   run-discover.cmd              -> python -m scraper.cli --discover
rem   run-discover.cmd <notice_id>  -> python -m scraper.cli <notice_id>
setlocal
cd /d "%~dp0"

set "TARGET_BRANCH=main"

if "%~1"=="" (
    echo [1/3] Running scraper discover...
    python -m scraper.cli --discover
) else (
    echo [1/3] Running scraper for notice %~1...
    python -m scraper.cli "%~1"
)
if errorlevel 1 (
    echo ERROR: scraper exited with code %errorlevel%. Aborting without commit.
    goto :fail
)

echo [2/3] Staging docs/ changes...
git add -A -- docs/
if errorlevel 1 goto :fail

git diff --cached --quiet -- docs/
if not errorlevel 1 (
    echo No changes in docs/. Skipping commit and push.
    goto :done
)
git status --short -- docs/

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TIMESTAMP=%%i"

echo [3/3] Committing and pushing to %TARGET_BRANCH%...
git commit -m "docs: update data %TIMESTAMP%" -- docs/
if errorlevel 1 goto :fail
git push origin "HEAD:refs/heads/%TARGET_BRANCH%"
if errorlevel 1 goto :fail

:done
echo Done.
endlocal
pause
exit /b 0

:fail
echo FAILED.
endlocal
pause
exit /b 1
