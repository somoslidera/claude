"""A rotina: detecta novos seguidores e engaja com cada um."""

from __future__ import annotations

import logging
import random

from .config import Config
from .instagram import ActionBlockedError, Instagram, InstagramError, Profile
from .limits import RateLimiter, human_pause, within_active_hours
from .storage import Storage

log = logging.getLogger(__name__)


class Routine:
    def __init__(self, cfg: Config, ig: Instagram, storage: Storage, pause=human_pause):
        self.cfg = cfg
        self.ig = ig
        self.storage = storage
        self.limiter = RateLimiter(cfg, storage)
        self.pause = pause

    # --- etapa 1: descobrir novos seguidores --------------------------------
    def sync_followers(self) -> list[str]:
        followers = self.ig.recent_followers(self.cfg.username, self.cfg.followers_to_scan)
        first_run = not self.storage.has_any_follower()
        if first_run and self.cfg.baseline_on_first_run:
            self.storage.add_new_followers(followers, baseline=True)
            log.info("1ª execução: %d seguidores atuais registrados como base (sem ações).",
                     len(followers))
            return []
        # A API devolve do mais recente para o mais antigo; invertemos para
        # que a fila seja processada na ordem em que as pessoas seguiram.
        new = self.storage.add_new_followers(list(reversed(followers)))
        log.info("%d novo(s) seguidor(es): %s", len(new), ", ".join(new) or "-")
        return new

    # --- etapa 2: engajar ------------------------------------------------------
    def run(self) -> None:
        if not within_active_hours(self.cfg.active_hours):
            log.info("Fora do horário ativo %s — nada a fazer.", self.cfg.active_hours)
            return
        self.sync_followers()
        queue = self.storage.pending_followers(self.cfg.limits.profiles_per_run)
        for i, username in enumerate(queue):
            if i:
                self.pause(self.cfg.delays.between_profiles)
            try:
                self.process(username)
            except ActionBlockedError as e:
                log.error("PARANDO: %s", e)
                return

    def process(self, username: str) -> None:
        r = self.cfg.routine
        if username.lower() in r.skip_usernames:
            self.storage.mark_processed(username, "skipped")
            return
        try:
            profile = self.ig.get_profile(username)
        except ActionBlockedError:
            raise
        except InstagramError as e:
            log.warning("@%s: %s", username, e)
            self.storage.mark_processed(username, "error")
            return

        log.info("→ @%s (privado=%s)", username, profile.is_private)
        try:
            can_see_content = not profile.is_private or profile.followed_by_me
            if r.like_posts and (can_see_content or not r.skip_private):
                self._like_posts(profile)
            if r.follow_back:
                self._follow(profile)
            if r.like_story and can_see_content:
                self._like_story(profile)
            if r.send_dm:
                self._send_dm(profile)
        except ActionBlockedError:
            raise
        except InstagramError as e:
            log.warning("@%s: %s", username, e)
            self.storage.mark_processed(username, "error")
            return
        self.storage.mark_processed(username, "done")

    # --- ações individuais ---------------------------------------------------
    def _act(self, action: str, username: str, detail: str, fn) -> bool:
        """Executa uma ação respeitando limite diário, dry-run e pausa."""
        if not self.limiter.allowed(action):
            log.info("   limite diário de '%s' atingido", action)
            return False
        if self.cfg.dry_run:
            log.info("   [dry-run] %s %s", action, detail)
            self.storage.log_action(username, action, detail, dry_run=True)
            return True
        done = fn()
        if done:
            log.info("   ✓ %s %s", action, detail)
            self.storage.log_action(username, action, detail)
            self.pause(self.cfg.delays.between_actions)
        return done

    def _like_posts(self, p: Profile) -> None:
        for code in p.recent_shortcodes[: self.cfg.routine.posts_to_like]:
            self._act("like", p.username, code, lambda c=code: self.ig.like_post(c))

    def _like_story(self, p: Profile) -> None:
        self._act("story_like", p.username, "", lambda: self.ig.like_story(p.username))

    def _follow(self, p: Profile) -> None:
        if p.followed_by_me or p.requested_by_me:
            return
        self._act("follow", p.username, "", lambda: self.ig.follow(p.username))

    def _send_dm(self, p: Profile) -> None:
        text = random.choice(self.cfg.routine.dm_templates).format(username=p.username)

        def send():
            self.ig.send_dm(p.username, text)
            return True

        self._act("dm", p.username, text, send)
