#!/bin/bash
cd "$(dirname "$0")/.."
.venv/bin/python -m instagram_bot analisar -c config.charles.simon.yaml
read -p "Enter para fechar"
