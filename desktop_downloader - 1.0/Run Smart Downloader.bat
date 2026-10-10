@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python 3 was not found. Install Python from https://www.python.org/downloads/
    echo During installation, include Tcl/Tk and the Python launcher.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating a private Python environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo Could not create the app environment. Check that Python 3 and venv are installed.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "import tkinter, requests, yt_dlp" >nul 2>nul
if errorlevel 1 (
    echo Installing downloader packages. The first launch can take several minutes...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    ".venv\Scripts\python.exe" -c "import tkinter, requests, yt_dlp"
    if errorlevel 1 (
        echo Required packages are not ready. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" launch.py
if errorlevel 1 (
    echo Smart Downloader closed with an error.
    pause
)
