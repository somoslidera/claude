"""Cliente do Instagram via navegador (Playwright).

A API oficial do Instagram não permite curtir, seguir nem curtir stories, então
o bot controla o Google Chrome, logado na sua conta. Dois modos:

- "chrome": o bot abre o Chrome instalado no computador, com um perfil próprio
  em `data/browser-profile` (login feito uma vez, à mão, incluindo 2FA).
- "cdp": o bot se conecta a um Chrome que já está aberto com depuração remota
  (`python -m instagram_bot chrome`) e trabalha em uma aba nova dele.

Obs.: desde o Chrome 136 a automação não funciona no seu perfil pessoal do
Chrome; por isso os dois modos usam um perfil separado, só para o bot.

Leitura de dados (lista de seguidores, info do perfil) usa os mesmos endpoints
JSON que o próprio site chama; as ações (seguir, curtir) são feitas clicando
nos botões da página, como uma pessoa faria.

O Instagram muda o HTML com frequência. Se uma ação parar de funcionar, os
seletores estão concentrados nas constantes abaixo.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Error as PWError, Page, sync_playwright

log = logging.getLogger(__name__)

BASE = "https://www.instagram.com"
WEB_APP_ID = "936619743392459"  # app id público usado pelo instagram.com

# Textos/labels em português e inglês (a interface segue o idioma da conta).
FOLLOW_BTN = re.compile(r"^(Seguir|Seguir de volta|Follow|Follow Back)$", re.I)
FOLLOWING_BTN = re.compile(r"^(Seguindo|Solicitado|Following|Requested)$", re.I)
MESSAGE_BTN = re.compile(r"^(Enviar mensagem|Mensagem|Message)$", re.I)
VIEW_STORY_BTN = re.compile(r"^(Ver story|Ver stories|View story|View stories)$", re.I)
NOT_NOW_BTN = re.compile(r"^(Agora não|Not Now)$", re.I)
LIKE_SVG = 'svg[aria-label="Curtir"], svg[aria-label="Like"]'
UNLIKE_SVG = 'svg[aria-label="Descurtir"], svg[aria-label="Unlike"]'


def _sized(selector: str, px: int) -> str:
    return ", ".join(f'{part.strip()}[height="{px}"]' for part in selector.split(","))


def _click_icon(icon) -> None:
    icon.locator("xpath=ancestor::*[@role='button' or self::button][1]").click()


class InstagramError(RuntimeError):
    pass


class ActionBlockedError(InstagramError):
    """Sinal de bloqueio/limite do Instagram: a rotina deve parar na hora."""


@dataclass
class Profile:
    username: str
    user_id: str
    is_private: bool
    followed_by_me: bool
    requested_by_me: bool
    follows_me: bool
    recent_shortcodes: list[str] = field(default_factory=list)


class Instagram:
    def __init__(self, profile_dir: Path, headless: bool = False, browser: str = "chrome",
                 cdp_url: str = "http://localhost:9222"):
        if browser not in ("chrome", "cdp", "chromium"):
            raise ValueError("browser deve ser 'chrome', 'cdp' ou 'chromium'")
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.browser_mode = browser
        self.cdp_url = cdp_url
        self._pw = None
        self._browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    # --- ciclo de vida ------------------------------------------------------
    def __enter__(self) -> "Instagram":
        self._pw = sync_playwright().start()
        try:
            if self.browser_mode == "cdp":
                self._connect_cdp()
            else:
                self._launch()
        except Exception:
            self._pw.stop()
            raise
        self.page.set_default_timeout(20_000)
        return self

    def _launch(self) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.context = self._pw.chromium.launch_persistent_context(
                str(self.profile_dir),
                channel="chrome" if self.browser_mode == "chrome" else None,
                headless=self.headless,
                locale="pt-BR",
                viewport={"width": 1280, "height": 900},
            )
        except PWError as e:
            if self.browser_mode == "chrome" and "chrome" in str(e).lower():
                raise InstagramError(
                    "Google Chrome não encontrado. Instale o Chrome ou rode: "
                    "playwright install chrome"
                ) from e
            raise
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def _connect_cdp(self) -> None:
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        except PWError as e:
            raise InstagramError(
                f"Não consegui conectar ao Chrome em {self.cdp_url}. Abra-o antes com: "
                "python -m instagram_bot chrome"
            ) from e
        self.context = self._browser.contexts[0]
        # Aba própria: não mexe nas abas que você estiver usando.
        self.page = self.context.new_page()

    def __exit__(self, *exc) -> None:
        if self.browser_mode == "cdp":
            # Fecha só a aba do bot; o Chrome continua aberto.
            if self.page and not self.page.is_closed():
                self.page.close()
        elif self.context:
            self.context.close()
        if self._pw:
            self._pw.stop()

    # --- sessão -------------------------------------------------------------
    def is_logged_in(self) -> bool:
        return any(c["name"] == "sessionid" and c["value"] for c in self.context.cookies(BASE))

    def interactive_login(self, timeout_s: int = 300) -> None:
        """Abre a tela de login e espera você entrar manualmente (com 2FA, se houver)."""
        self.page.goto(f"{BASE}/accounts/login/")
        print(f"Faça login na janela do navegador. Aguardando até {timeout_s}s...")
        for _ in range(timeout_s):
            if self.is_logged_in():
                self.page.wait_for_timeout(3000)
                return
            self.page.wait_for_timeout(1000)
        raise InstagramError("Tempo esgotado esperando o login")

    def ensure_logged_in(self) -> None:
        self.page.goto(BASE)
        if not self.is_logged_in():
            raise InstagramError("Não está logado. Rode primeiro: python -m instagram_bot login")

    # --- leitura (JSON) -----------------------------------------------------
    def _api_get(self, path: str) -> dict:
        if not self.page.url.startswith(BASE):
            self.page.goto(BASE)
        result = self.page.evaluate(
            """async ([url, appId]) => {
                const r = await fetch(url, {
                    credentials: 'include',
                    headers: {'X-IG-App-ID': appId, 'X-Requested-With': 'XMLHttpRequest'},
                });
                return {status: r.status, text: await r.text()};
            }""",
            [f"{BASE}{path}", WEB_APP_ID],
        )
        if result["status"] == 429:
            raise ActionBlockedError("Instagram limitou as requisições (429). Pare por algumas horas.")
        if result["status"] != 200:
            raise InstagramError(f"GET {path} -> HTTP {result['status']}: {result['text'][:200]}")
        return json.loads(result["text"])

    def get_profile(self, username: str) -> Profile:
        data = self._api_get(f"/api/v1/users/web_profile_info/?username={username}")
        user = (data.get("data") or {}).get("user")
        if not user:
            raise InstagramError(f"Perfil @{username} não encontrado")
        edges = (user.get("edge_owner_to_timeline_media") or {}).get("edges") or []
        return Profile(
            username=user["username"],
            user_id=str(user["id"]),
            is_private=bool(user.get("is_private")),
            followed_by_me=bool(user.get("followed_by_viewer")),
            requested_by_me=bool(user.get("requested_by_viewer")),
            follows_me=bool(user.get("follows_viewer")),
            recent_shortcodes=[e["node"]["shortcode"] for e in edges if e.get("node")],
        )

    def recent_followers(self, my_username: str, count: int) -> list[str]:
        """Seguidores mais recentes primeiro (ordem que o Instagram devolve)."""
        me = self.get_profile(my_username)
        usernames: list[str] = []
        max_id = ""
        while len(usernames) < count:
            path = f"/api/v1/friendships/{me.user_id}/followers/?count={min(50, count)}"
            if max_id:
                path += f"&max_id={max_id}"
            data = self._api_get(path)
            usernames += [u["username"] for u in data.get("users", [])]
            max_id = data.get("next_max_id") or ""
            if not max_id:
                break
        return usernames[:count]

    # --- ações (cliques) ------------------------------------------------------
    def _dismiss_popups(self) -> None:
        btn = self.page.get_by_role("button", name=NOT_NOW_BTN)
        if btn.count():
            try:
                btn.first.click(timeout=2000)
            except PWError:
                pass

    def _goto(self, path: str) -> None:
        self.page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
        self.page.wait_for_timeout(2500)
        self._dismiss_popups()

    def follow(self, username: str) -> bool:
        """Clica em Seguir/Seguir de volta. Retorna True se passou a seguir."""
        self._goto(f"/{username}/")
        header = self.page.locator("header")
        if header.get_by_role("button", name=FOLLOWING_BTN).count():
            return False
        btn = header.get_by_role("button", name=FOLLOW_BTN)
        if not btn.count():
            raise InstagramError(f"Botão Seguir não encontrado em @{username}")
        btn.first.click()
        try:
            header.get_by_role("button", name=FOLLOWING_BTN).first.wait_for(timeout=8000)
        except PWError:
            raise ActionBlockedError(
                f"Cliquei em Seguir em @{username} mas não confirmou — possível bloqueio de ação"
            )
        return True

    def _click_like_icon(self) -> bool:
        """Curte o post. Usa só o ícone de 24px para ignorar corações de comentários."""
        if self.page.locator(_sized(UNLIKE_SVG, 24)).count():
            return False  # já curtido
        icon = self.page.locator(_sized(LIKE_SVG, 24))
        if not icon.count():
            raise InstagramError("Botão Curtir não encontrado")
        _click_icon(icon.first)
        self.page.wait_for_timeout(1200)
        return True

    def like_post(self, shortcode: str) -> bool:
        self._goto(f"/p/{shortcode}/")
        return self._click_like_icon()

    def like_story(self, username: str) -> bool:
        """Abre o story atual e curte. False se não houver story ou já curtido."""
        self._goto(f"/stories/{username}/")
        if "/stories/" not in self.page.url:
            return False  # sem story ativo: o Instagram redireciona para o perfil
        view = self.page.get_by_role("button", name=VIEW_STORY_BTN)
        if view.count():
            view.first.click()
        self.page.wait_for_timeout(2500)
        # Pausa o story para ele não avançar para o próximo perfil.
        self.page.keyboard.press("Space")
        if self.page.locator(UNLIKE_SVG).count():
            return False
        icon = self.page.locator(LIKE_SVG)
        if not icon.count():
            return False
        _click_icon(icon.first)
        self.page.wait_for_timeout(1200)
        return True

    def send_dm(self, username: str, text: str) -> None:
        self._goto(f"/{username}/")
        btn = self.page.locator("header").get_by_role("button", name=MESSAGE_BTN)
        if not btn.count():
            btn = self.page.locator("header").get_by_role("link", name=MESSAGE_BTN)
        if not btn.count():
            raise InstagramError(f"Botão Mensagem não encontrado em @{username}")
        btn.first.click()
        self.page.wait_for_timeout(3000)
        self._dismiss_popups()
        box = self.page.get_by_role("textbox").last
        box.click()
        box.type(text, delay=60)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(2000)


def find_chrome() -> str:
    """Caminho do executável do Google Chrome instalado."""
    system = platform.system()
    if system == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    elif system == "Windows":
        candidates = [
            os.path.join(os.environ.get(var, ""), r"Google\Chrome\Application\chrome.exe")
            for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
        ]
    else:
        candidates = [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable")]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise InstagramError("Google Chrome não encontrado neste computador")


def launch_chrome_for_cdp(profile_dir: Path, port: int) -> subprocess.Popen:
    """Abre o Chrome com depuração remota, num perfil separado só para o bot."""
    profile_dir = Path(profile_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([
        find_chrome(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        f"{BASE}/",
    ])
