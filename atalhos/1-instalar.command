#!/bin/bash
cd "$(dirname "$0")/.."
echo "Instalando... (só precisa fazer 1 vez)"
python3 -m venv .venv || { echo "ERRO: Python 3 não encontrado. Instale em python.org."; read -p "Enter para sair"; exit 1; }
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt
echo; echo 'Pronto! Agora rode "2-login-charles".'
read -p "Enter para fechar"
