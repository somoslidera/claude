"""CLI.

    python -m instagram_bot login              # 1x: abre o navegador para você logar
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

from .config import load_config
from .instagram import Instagram, InstagramError
from .routine import Routine
from .storage import Storage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="instagram_bot")
    ap.add_argument("command", choices=["login", "run", "loop", "status"])
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="simula sem executar ações")
    ap.add_argument("--headless", action="store_true", help="navegador sem janela")
    ap.add_argument("--interval", type=int, default=60,
                    help="minutos (aprox.) entre execuções no modo loop")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(args.config)
    cfg.dry_run = cfg.dry_run or args.dry_run
    cfg.headless = cfg.headless or args.headless
    storage = Storage(cfg.db_path)

    if args.command == "status":
        print(json.dumps(storage.summary(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "login":
        with Instagram(cfg.profile_dir, headless=False) as ig:
            ig.interactive_login()
        print("Login salvo. Agora rode: python -m instagram_bot run --dry-run")
        return 0

    try:
        while True:
            with Instagram(cfg.profile_dir, headless=cfg.headless) as ig:
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
