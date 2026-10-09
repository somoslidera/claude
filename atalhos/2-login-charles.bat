@echo off
cd /d "%~dp0\.."
.venv\Scripts\python -m instagram_bot login -c config.charles.simon.yaml
pause
