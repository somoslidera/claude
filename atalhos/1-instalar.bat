@echo off
cd /d "%~dp0\.."
echo Instalando... (so precisa fazer 1 vez)
py -3 -m venv .venv 2>nul || python -m venv .venv || (echo. & echo ERRO: Python nao encontrado. Instale em python.org e marque "Add python.exe to PATH". & pause & exit /b 1)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt
echo.
echo Pronto! Agora rode "2-login-charles".
pause
