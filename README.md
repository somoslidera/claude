# Instagram — rotina automática para novos seguidores

Automatiza a rotina que hoje é feita à mão. Para cada **novo seguidor**:

1. abre o perfil
2. curte as **N fotos mais recentes** (padrão: 2)
3. **segue de volta**
4. curte o **story** atual, se houver
5. *(opcional, desligado)* envia uma **DM de boas-vindas**

## ⚠️ Antes de usar

- A API oficial do Instagram **não permite** curtir, seguir nem curtir stories. Por isso o bot
  controla o **Google Chrome** logado na sua conta (via Playwright).
- Automação desse tipo **vai contra os Termos de Uso do Instagram**. A conta pode sofrer
  "ação bloqueada" ou suspensão temporária. Para reduzir o risco, o bot já vem com:
  limites diários baixos, pausas aleatórias, horário ativo, parada imediata ao detectar
  bloqueio e modo de simulação (`--dry-run`).
- Rode **no seu computador** (mesmo IP/dispositivo que você usa normalmente), não em servidor/nuvem.
- Comece com limites ainda menores que os padrões e aumente aos poucos ao longo das semanas.

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt               # precisa do Google Chrome instalado
cp config.example.yaml config.yaml                  # edite o username e os limites
```

## Conexão com o Chrome

Há dois modos (`browser:` no `config.yaml`, ou `--browser` na linha de comando):

| Modo | Como funciona | Quando usar |
|---|---|---|
| `chrome` *(padrão)* | o bot abre o Chrome sozinho, roda a rotina e fecha | rodar agendado / sem ninguém olhando |
| `cdp` | você deixa um Chrome aberto e o bot se conecta nele, trabalhando numa aba nova | acompanhar ao vivo na mesma janela |

Modo `cdp`, passo a passo:

```bash
python -m instagram_bot chrome                    # abre o Chrome do bot (porta 9222); faça login nele
python -m instagram_bot run --browser cdp --dry-run
```

> **Importante:** desde o Chrome 136 o Google bloqueia automação no seu perfil pessoal do
> Chrome. Por isso os dois modos usam um **perfil separado** (`data/browser-profile`): é um Chrome
> "limpo", em que você entra no Instagram uma única vez. O login fica salvo e vale para os dois
> modos. Seu Chrome normal não é tocado. Só não dá para usar os dois modos ao mesmo tempo:
> se o Chrome do modo `cdp` estiver aberto, rode com `--browser cdp`.

Sem o Chrome instalado, use `browser: chromium` e rode antes `playwright install chromium`.

## Jeito mais fácil: clique duplo (pasta `atalhos/`)

Precisa do **Python 3** (python.org — no Windows, marque *"Add python.exe to PATH"* na instalação)
e do **Google Chrome**. Depois, na pasta `atalhos/`, em ordem:

| | Windows | Mac |
|---|---|---|
| 1. instalar (só 1x) | `1-instalar.bat` | `1-instalar.command` |
| 2. login na conta do Charles (só 1x) | `2-login-charles.bat` | `2-login-charles.command` |
| 3. analisar quem começou a seguir | `3-analisar-charles.bat` | `3-analisar-charles.command` |

No Mac, se aparecer "não é possível abrir", clique com o botão direito → **Abrir**.

## Primeiro teste: analisar quem começou a seguir

Só leitura — não curte, não segue, não manda nada:

```bash
python -m instagram_bot login    -c config.charles.simon.yaml   # 1x: login na conta do Charles
python -m instagram_bot analisar -c config.charles.simon.yaml   # lista os 20 seguidores mais recentes
python -m instagram_bot analisar -c config.charles.simon.yaml -n 50
```

Mostra uma tabela (nome, se é novo, privado, se já segue de volta, posts, seguidores) e salva um
CSV (abre no Excel) em `data/charles.simon/`. Na 1ª análise todos viram "base"; nas seguintes,
quem seguiu depois aparece como **novo** e fica na fila da rotina.

Cada conta tem seu próprio arquivo de config e sua pasta em `data/` (Chrome, histórico e
relatórios separados), então dá para atender vários clientes sem misturar.

## Uso

```bash
python -m instagram_bot login           # 1x: abre o Chrome, você loga (com 2FA). A sessão fica salva.
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
| `instagram_bot/instagram.py` | Chrome (abrir ou conectar via CDP), login, leitura de seguidores/perfil, cliques em Seguir/Curtir/Story/DM |
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
