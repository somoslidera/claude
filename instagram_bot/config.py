"""Carregamento e validação da configuração (config.yaml)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml


@dataclass
class Limits:
    # Limites diários. Mantenha baixos: contas novas ou pouco ativas são
    # bloqueadas com bem menos ações do que contas antigas.
    follows_per_day: int = 40
    likes_per_day: int = 120
    story_likes_per_day: int = 60
    dms_per_day: int = 15
    profiles_per_run: int = 10


@dataclass
class Delays:
    # Intervalos aleatórios (segundos) para imitar o ritmo humano.
    between_actions: tuple[float, float] = (4.0, 11.0)
    between_profiles: tuple[float, float] = (45.0, 120.0)


@dataclass
class Routine:
    like_posts: bool = True
    posts_to_like: int = 2           # quantos posts recentes curtir
    follow_back: bool = True
    like_story: bool = True
    send_dm: bool = False            # desligado por padrão: DM é o que mais gera bloqueio
    dm_templates: list[str] = field(default_factory=lambda: [
        "Oi {username}! Obrigado por seguir 😊",
    ])
    skip_private: bool = True        # perfis privados: só segue, não curte
    skip_usernames: list[str] = field(default_factory=list)


@dataclass
class Config:
    username: str
    data_dir: Path = Path("data")
    headless: bool = False
    active_hours: tuple[int, int] = (9, 22)   # só roda entre 9h e 22h
    followers_to_scan: int = 50
    # Na 1ª execução, marca os seguidores atuais como "já vistos" para não
    # sair curtindo/seguindo a base inteira de seguidores antigos.
    baseline_on_first_run: bool = True
    dry_run: bool = False
    limits: Limits = field(default_factory=Limits)
    delays: Delays = field(default_factory=Delays)
    routine: Routine = field(default_factory=Routine)

    @property
    def profile_dir(self) -> Path:
        return self.data_dir / "browser-profile"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bot.sqlite3"


def _build(cls, raw: dict | None):
    raw = raw or {}
    known = {f.name for f in fields(cls)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Chaves desconhecidas em '{cls.__name__}': {sorted(unknown)}")
    kwargs = {}
    for k, v in raw.items():
        if isinstance(v, list) and k in ("between_actions", "between_profiles", "active_hours"):
            v = tuple(v)
        kwargs[k] = v
    return cls(**kwargs)


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not raw.get("username"):
        raise ValueError("Defina 'username' (seu @ sem o arroba) no config.yaml")
    cfg = _build(Config, {
        k: v for k, v in raw.items() if k not in ("limits", "delays", "routine")
    })
    cfg.username = cfg.username.lstrip("@").strip()
    cfg.data_dir = Path(cfg.data_dir)
    cfg.limits = _build(Limits, raw.get("limits"))
    cfg.delays = _build(Delays, raw.get("delays"))
    cfg.routine = _build(Routine, raw.get("routine"))
    cfg.routine.skip_usernames = [u.lstrip("@").lower() for u in cfg.routine.skip_usernames]
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    for name in ("between_actions", "between_profiles"):
        lo, hi = getattr(cfg.delays, name)
        if lo < 0 or hi < lo:
            raise ValueError(f"delays.{name} deve ser [min, max] com 0 <= min <= max")
    start, end = cfg.active_hours
    if not (0 <= start <= 23 and 1 <= end <= 24):
        raise ValueError("active_hours deve ser [inicio, fim] entre 0 e 24")
    if cfg.routine.send_dm and not cfg.routine.dm_templates:
        raise ValueError("routine.send_dm está ligado mas routine.dm_templates está vazio")
