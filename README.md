# JarvisCodex

Un blueprint pentru un **personal cognitive operating layer** persistent, extensibil și recuperabil. Nu este încă o implementare și nu conține secrete sau conexiuni active.

JarvisCodex păstrează ideea bună din Jarvis — un asistent care îți înțelege proiectele și poate propune inițiative — dar pune de la început în centru patru proprietăți:

1. **Creier recuperabil:** starea importantă are backup criptat, export portabil și restore testat.
2. **Nucleu independent de model:** Claude, Codex, un LLM local sau un router pot fi înlocuite fără a pierde memoria, politica sau istoricul.
3. **Pluginuri fără privilegii implicite:** pluginurile declară capabilități; brokerul și policy engine-ul decid ce execută efectiv.
4. **Autonomie intelectuală, nu auto-autorizare:** poate observa, cerceta, memora, propune și testa izolat; nu își mărește singur autoritatea.

## Ce este și ce nu este

```text
JarvisCodex = control plane + state durabil + policy + orchestration
LLM         = motor de reasoning înlocuibil
Plugins     = capabilități declarative, controlate
Omarchy     = mediul peste care poate face propuneri
Telegram/UI = canale de interacțiune, nu nucleul
```

Nu este un fork Omarchy, un swarm de agenți sau un sistem care execută modificări de sistem fără aprobare.

## Ordinea de citire

1. [Arhitectura](docs/01-architecture.md)
2. [Starea, memoria și proveniența](docs/02-state-and-memory.md)
3. [Contractul de pluginuri](docs/03-plugin-system.md)
4. [Siguranța și capabilitățile](docs/04-safety-model.md)
5. [Backup și disaster recovery](docs/05-recovery.md)
6. [Roadmap](docs/06-roadmap.md)
7. [Arborele propus](structure/PROPOSED_TREE.md)

## Milestone 0.1

Spui o idee. Sistemul o înregistrează durabil, găsește contextul relevant, îți răspunde, propune o memorie cu surse verificabile și, într-o conversație ulterioară, o poate recupera. Nicio schimbare externă nu poate trece de policy engine fără aprobarea ta.

## Status

🟢 Faza A (nucleu durabil) — completă. Există: scheme versionate pentru event/task/approval/memory candidate, un event ledger SQLite append-only, proiecții reconstruibile din evenimente (`storage/projections.py`), export Markdown/JSON, backup criptat cu `age` + test de restore automat (`tests/recovery/`), și un policy engine (`policy/engine.py`) cu executor dry-run (`policy/executor.py`) testat adversarial (`tests/policy/test_policy_adversarial.py`) — capabilități tipizate cu nivel de risc fix, aprobări L3+ auditabile în ledger, fără efecte reale înainte de Faza C.

Rulare teste (stdlib + binarul `age` instalat, fără alte dependențe):

```bash
python3 -m unittest discover -t . -s tests -v
```

Backup/restore manual: vezi `docs/05-recovery.md` și `scripts/backup_now.py` / `scripts/restore_backup.py`.

🟡 Faza B (conversație și memorie) — în lucru. CLI local (`apps/cli/jarvis.py`: `chat`, `status`, `approvals list/decide`, `healthcheck`, `kill`), contractul `ReasoningBackend` (`contracts/reasoning.py`) cu un backend local de test fără cost (`backends/echo.py`), și fluxul complet din Milestone 0.1 (`core/conversation.py`): mesaj → înregistrare durabilă → context recuperat → răspuns → memorie propusă cu surse verificabile, recuperabilă în conversații ulterioare.

```bash
JARVIS_CODEX_DATA_DIR=./data/live python3 apps/cli/jarvis.py chat myself "o idee de reținut"
JARVIS_CODEX_DATA_DIR=./data/live python3 apps/cli/jarvis.py status
```

🟢 Faza B (conversație și memorie) — completă. Adapter Telegram autentificat (`apps/telegram/bot.py`, testat live), `ReasoningBackend` real cu Claude prin Anthropic API (`backends/claude.py`, propuneri de memorie printr-un tool call explicit, nu parsare de text), ales prin `JARVIS_CODEX_BACKEND` (`echo` implicit, `claude` la cerere — vezi `docs/01-architecture.md`).

```bash
# implicit: gratuit, local, fără rețea
python3 apps/cli/jarvis.py chat myself "o idee"

# cu Claude real, după ce pui ANTHROPIC_API_KEY în .env
JARVIS_CODEX_BACKEND=claude python3 apps/cli/jarvis.py chat myself "o idee"
```

Următorul pas e Faza C din `docs/06-roadmap.md`: intent → signal → candidate initiative → goal, consolidation loop, heartbeat rar și bugetat.
