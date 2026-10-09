"""Persistência em SQLite: seguidores já vistos e histórico de ações."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS followers (
    username     TEXT PRIMARY KEY,
    first_seen   TEXT NOT NULL,
    processed_at TEXT,          -- NULL = ainda na fila
    status       TEXT           -- done | skipped | baseline | error
);
CREATE TABLE IF NOT EXISTS actions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    day       TEXT NOT NULL,
    username  TEXT NOT NULL,
    action    TEXT NOT NULL,    -- follow | like | story_like | dm
    detail    TEXT,
    dry_run   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_actions_day ON actions(day, action);
"""


class Storage:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- seguidores -------------------------------------------------------
    def has_any_follower(self) -> bool:
        return self.conn.execute("SELECT 1 FROM followers LIMIT 1").fetchone() is not None

    def add_new_followers(self, usernames: list[str], baseline: bool = False) -> list[str]:
        """Registra quem ainda não conhecemos; retorna apenas os novos."""
        now = datetime.now().isoformat(timespec="seconds")
        new = []
        with self.conn:
            for u in usernames:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO followers(username, first_seen, processed_at, status)"
                    " VALUES (?, ?, ?, ?)",
                    (u, now, now if baseline else None, "baseline" if baseline else None),
                )
                if cur.rowcount:
                    new.append(u)
        return new

    def pending_followers(self, limit: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT username FROM followers WHERE processed_at IS NULL"
            " ORDER BY first_seen, rowid LIMIT ?",
            (limit,),
        ).fetchall()
        return [r[0] for r in rows]

    def mark_processed(self, username: str, status: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE followers SET processed_at = ?, status = ? WHERE username = ?",
                (datetime.now().isoformat(timespec="seconds"), status, username),
            )

    # --- ações ------------------------------------------------------------
    def log_action(self, username: str, action: str, detail: str = "", dry_run: bool = False) -> None:
        now = datetime.now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO actions(ts, day, username, action, detail, dry_run)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (now.isoformat(timespec="seconds"), now.date().isoformat(),
                 username, action, detail, int(dry_run)),
            )

    def count_today(self, action: str, today: date | None = None) -> int:
        day = (today or date.today()).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) FROM actions WHERE day = ? AND action = ? AND dry_run = 0",
            (day, action),
        ).fetchone()
        return row[0]

    def summary(self) -> dict:
        q = self.conn.execute
        return {
            "seguidores_conhecidos": q("SELECT COUNT(*) FROM followers").fetchone()[0],
            "na_fila": q("SELECT COUNT(*) FROM followers WHERE processed_at IS NULL").fetchone()[0],
            "hoje": {a: self.count_today(a) for a in ("follow", "like", "story_like", "dm")},
        }
