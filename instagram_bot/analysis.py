"""Análise (somente leitura) de quem começou a seguir o perfil.

Não curte, não segue e não envia nada: só lê e gera um relatório. Os seguidores
vistos são registrados com a mesma regra da rotina (1ª vez = base; depois, quem
for novo entra na fila), para que a coluna "novo" faça sentido entre análises.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from .config import Config
from .instagram import ActionBlockedError, Instagram, InstagramError
from .limits import human_pause
from .storage import Storage

log = logging.getLogger(__name__)

COLUMNS = ["ordem", "username", "nome", "novo", "privado", "ja_sigo",
           "posts", "seguidores", "seguindo", "link"]


def analyze(cfg: Config, ig: Instagram, storage: Storage, count: int,
            pause=human_pause) -> list[dict]:
    usernames = ig.recent_followers(cfg.username, count)
    has_history = storage.has_any_follower()
    known = storage.known_followers()
    _register(cfg, storage, usernames, first_run=not has_history)
    rows = []
    for i, username in enumerate(usernames, 1):
        row = {"ordem": i, "username": username, "nome": "",
               "novo": ("sim" if username not in known else "não") if has_history else "-",
               "privado": "", "ja_sigo": "", "posts": "", "seguidores": "", "seguindo": "",
               "link": f"https://www.instagram.com/{username}/"}
        if i > 1:
            pause((1.5, 4.0))  # leitura também tem limite; vai devagar
        try:
            p = ig.get_profile(username)
            row.update(nome=p.full_name, privado=_yn(p.is_private),
                       ja_sigo=_yn(p.followed_by_me or p.requested_by_me),
                       posts=p.posts, seguidores=p.followers, seguindo=p.following)
        except ActionBlockedError:
            log.warning("Instagram limitou as leituras; relatório parcial.")
            rows.append(row)
            break
        except InstagramError as e:
            log.warning("@%s: %s", username, e)
        rows.append(row)
    return rows


def _register(cfg: Config, storage: Storage, usernames: list[str], first_run: bool) -> None:
    if first_run and cfg.baseline_on_first_run:
        storage.add_new_followers(usernames, baseline=True)
    else:
        storage.add_new_followers(list(reversed(usernames)))


def _yn(v: bool) -> str:
    return "sim" if v else "não"


def save_csv(rows: list[dict], data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"analise-seguidores-{datetime.now():%Y%m%d-%H%M}.csv"
    # utf-8-sig + ";" para abrir direto no Excel em português.
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    return path


def print_table(rows: list[dict]) -> None:
    cols = ["ordem", "username", "nome", "novo", "privado", "ja_sigo", "posts", "seguidores"]
    widths = {c: max(len(c), *(len(str(r[c])[:28]) for r in rows)) for c in cols} if rows else {}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c])[:28].ljust(widths[c]) for c in cols))
