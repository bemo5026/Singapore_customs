@echo off
rem Extract Singapore customs data (value and quantity) from SingStat TableBuilder.
rem Usage: run.bat [config file] [extra options such as --verbose]
rem Default config file: config.yaml next to this script. See README.md and docs\.

setlocal
cd /d "%~dp0"

set "CONFIG=%~1"
if "%CONFIG%"=="" set "CONFIG=config.yaml"

if not exist ".venv\Scripts\python.exe" (
    echo Creating the Python virtual environment in .venv ...
    py -3 -m venv .venv || python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Python 3.12 or later is required. Install it from https://www.python.org/downloads/
        exit /b 1
    )
)

echo Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo ERROR: dependency installation failed.
    exit /b 1
)

".venv\Scripts\python.exe" -m singapore_customs --config "%CONFIG%" %2 %3 %4
if errorlevel 1 (
    echo.
    echo ERROR: the extraction failed. See the latest file in the logs folder.
    exit /b 1
)

echo.
echo Extraction finished. Files are in the output folder.
exit /b 0
