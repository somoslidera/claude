# Instagram — rotina automática para novos seguidores

Automatiza a rotina que hoje é feita à mão. Para cada **novo seguidor**:

1. abre o perfil
2. curte as **N fotos mais recentes** (padrão: 2)
3. **segue de volta**
4. curte o **story** atual, se houver
5. *(opcional, desligado)* envia uma **DM de boas-vindas**

## ⚠️ Antes de usar

- A API oficial do Instagram **não permite** curtir, seguir nem curtir stories. Por isso o bot
  controla um navegador real logado na sua conta (Playwright).
- Automação desse tipo **vai contra os Termos de Uso do Instagram**. A conta pode sofrer
  "ação bloqueada" ou suspensão temporária. Para reduzir o risco, o bot já vem com:
  limites diários baixos, pausas aleatórias, horário ativo, parada imediata ao detectar
  bloqueio e modo de simulação (`--dry-run`).
- Rode **no seu computador** (mesmo IP/dispositivo que você usa normalmente), não em servidor/nuvem.
- Comece com limites ainda menores que os padrões e aumente aos poucos ao longo das semanas.

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp config.example.yaml config.yaml                  # edite o username e os limites
```

## Uso

```bash
python -m instagram_bot login           # 1x: abre o navegador, você loga (com 2FA). A sessão fica salva.
python -m instagram_bot run --dry-run   # simula: mostra o que faria, sem curtir/seguir
python -m instagram_bot run             # executa a rotina uma vez
python -m instagram_bot loop --interval 60   # repete ~a cada 60 min (com variação aleatória)
python -m instagram_bot status          # ações do dia e tamanho da fila
```

**Primeira execução:** os seguidores atuais são registrados como "base" e nada é feito com
eles — só quem seguir *depois* entra na rotina (`baseline_on_first_run`).

### Agendar (em vez do `loop`)

- **macOS/Linux** (`crontab -e`), a cada hora entre 9h e 21h:
  `17 9-21 * * * cd /caminho/do/projeto && .venv/bin/python -m instagram_bot run >> data/bot.log 2>&1`
- **Windows:** Agendador de Tarefas → ação `python -m instagram_bot run`, iniciar em: pasta do projeto.

## Como funciona

| Arquivo | Função |
|---|---|
| `instagram_bot/instagram.py` | navegador: login, leitura de seguidores/perfil, cliques em Seguir/Curtir/Story/DM |
| `instagram_bot/routine.py` | a rotina por seguidor, limites, dry-run |
| `instagram_bot/storage.py` | SQLite em `data/bot.sqlite3`: quem já foi processado e histórico de ações |
| `instagram_bot/limits.py` | limites diários, horário ativo, pausas aleatórias |
| `config.example.yaml` | todas as opções comentadas |

- Perfis com erro são marcados e pulados; se o Instagram sinalizar bloqueio (HTTP 429 ou
  "Seguir" que não confirma), a execução **para na hora** e a fila é mantida para depois.
- O histórico completo fica na tabela `actions` (dá para abrir com qualquer visualizador SQLite).

## Quando algo parar de funcionar

O Instagram muda o site com frequência. Os textos e seletores dos botões ficam no topo de
`instagram_bot/instagram.py` (`FOLLOW_BTN`, `LIKE_SVG`, etc.), em português e inglês. Rode com
`headless: false` para ver onde o bot travou.

## Testes

```bash
pip install pytest && python -m pytest
```
