"""CLI.

    python -m instagram_bot chrome             # (modo cdp) abre o Chrome para o bot se conectar
    python -m instagram_bot login              # 1x: abre o Chrome para você logar
    python -m instagram_bot analisar           # só lista quem começou a seguir (não age)
    python -m instagram_bot run                # executa a rotina uma vez
    python -m instagram_bot run --dry-run      # simula, sem curtir/seguir nada
    python -m instagram_bot loop               # repete a rotina o dia todo
    python -m instagram_bot status             # contadores do dia e fila
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time

from .analysis import analyze, print_table, save_csv
from .config import load_config
from .instagram import Instagram, InstagramError, launch_chrome_for_cdp
from .routine import Routine
from .storage import Storage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="instagram_bot")
    ap.add_argument("command", choices=["chrome", "login", "analisar", "run", "loop", "status"])
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="simula sem executar ações")
    ap.add_argument("--browser", choices=["chrome", "cdp", "chromium"],
                    help="sobrescreve 'browser' do config.yaml")
    ap.add_argument("--headless", action="store_true", help="navegador sem janela")
    ap.add_argument("-n", "--quantidade", type=int, default=20,
                    help="analisar: quantos seguidores mais recentes listar")
    ap.add_argument("--interval", type=int, default=60,
                    help="minutos (aprox.) entre execuções no modo loop")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(args.config)
    cfg.dry_run = cfg.dry_run or args.dry_run
    cfg.headless = cfg.headless or args.headless
    cfg.browser = args.browser or cfg.browser
    storage = Storage(cfg.db_path)

    if args.command == "status":
        print(json.dumps(storage.summary(), indent=2, ensure_ascii=False))
        return 0

    def open_ig(headless: bool) -> Instagram:
        return Instagram(cfg.profile_dir, headless=headless,
                         browser=cfg.browser, cdp_url=cfg.cdp_url)

    try:
        if args.command == "chrome":
            launch_chrome_for_cdp(cfg.profile_dir, cfg.cdp_port)
            print(f"Chrome aberto (porta {cfg.cdp_port}). Faça login no Instagram nele, se "
                  "ainda não fez, e deixe a janela aberta.\n"
                  "Depois rode: python -m instagram_bot run --browser cdp --dry-run")
            return 0

        if args.command == "login":
            with open_ig(headless=False) as ig:
                if ig.is_logged_in():
                    print("Já está logado.")
                else:
                    ig.interactive_login()
                    print("Login salvo. Agora rode: python -m instagram_bot run --dry-run")
            return 0

        if args.command == "analisar":
            with open_ig(headless=cfg.headless) as ig:
                ig.ensure_logged_in()
                rows = analyze(cfg, ig, storage, args.quantidade)
            print(f"\nSeguidores mais recentes de @{cfg.username} (1 = mais recente):\n")
            print_table(rows)
            print(f"\nRelatório salvo em: {save_csv(rows, cfg.data_dir)}")
            if rows and rows[0]["novo"] == "-":
                print("(1ª análise: estes viraram a base. Nas próximas, quem seguir depois "
                      "aparece como 'novo' e entra na fila da rotina.)")
            return 0

        while True:
            with open_ig(headless=cfg.headless) as ig:
                ig.ensure_logged_in()
                Routine(cfg, ig, storage).run()
            if args.command == "run":
                return 0
            # Intervalo com variação de ±30% para não ter padrão fixo.
            wait = args.interval * 60 * random.uniform(0.7, 1.3)
            logging.info("Próxima execução em %.0f min.", wait / 60)
            time.sleep(wait)
    except InstagramError as e:
        logging.error("%s", e)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        storage.close()


if __name__ == "__main__":
    sys.exit(main())
