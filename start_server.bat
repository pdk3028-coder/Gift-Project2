@echo off
cd /d "%~dp0"
:: Start the Flask server in a new window
start "Employee Info System Server" python app.py

:: Wait for 3 seconds to ensure server is ready
timeout /t 3 /nobreak >nul

:: Open the default web browser
start http://127.0.0.1:5000
