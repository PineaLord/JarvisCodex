# Arhitectură

## Principiul central

Modelul nu este JarvisCodex. Modelul este un backend care primește context minim și propune rezultate structurate. Nucleul păstrează identitatea, memoria, politica, aprobările și istoricul.

```text
Channels (Telegram, CLI, UI)
             │
             ▼
       Ingress / Event API
             │
             ▼
┌────── JarvisCodex Control Plane ──────┐
│ intent · context · goals · policy      │
│ event ledger · memory · approvals      │
│ scheduler · audit · recovery           │
└───────┬───────────────┬────────────────┘
        │               │
        ▼               ▼
 Reasoning backend   Capability broker
 Claude/Codex/local       │
                         Plugins / tools / Omarchy
```

## Limite de responsabilitate

| Componentă | Este responsabilă pentru | Nu decide |
|---|---|---|
| Control plane | stare, context, task lifecycle | conținutul brut al reasoningului |
| LLM backend | analiză, clasificare, propuneri | permisiuni, execuție directă |
| Policy engine | clasificarea riscului | intenția utilizatorului |
| Capability broker | token/capability minimă per tool | autorizare permanentă |
| Plugin | efectul său declarat | acces în afara manifestului |

## Contracte care nu trebuie sparte

`ReasoningBackend`, `EventStore`, `MemoryStore`, `PluginManifest`, `CapabilityBroker` și `ChannelAdapter` sunt interfețele de stabilizat înainte de a scrie integrări. Înlocuirea unui LLM sau adăugarea unui plugin trebuie să fie o implementare nouă a unui contract, nu un refactor al nucleului.

## Autonomie

Există trei bucle, dar se introduc numai după ce nucleul este stabil: event loop, consolidation loop și heartbeat. Heartbeat-ul produce doar taskuri L0–L2, cu buget pe zi, cooldown per subiect și notificări agregate.

Implementare: `core/initiative.py` — vezi „Implementare: Faza C” în `docs/06-roadmap.md`. Consolidation loop și heartbeat rutează orice inițiativă prin `policy/engine.py`, exact ca orice altă acțiune; nu există o cale de auto-autorizare pentru ideile proprii ale sistemului.

## Implementare: canal CLI + ReasoningBackend

`contracts/reasoning.py` fixează contractul: un `ReasoningRequest` (text, context recuperat, id-ul evenimentului sursă) intră, un `ReasoningResponse` (text + propuneri de memorie cu surse) iese. `backends/echo.py` e o implementare locală, fără cost și fără rețea, care dovedește restul fluxului înainte de a conecta un provider real (Claude/Codex/local) — schimbarea backend-ului nu atinge `core/conversation.py` sau CLI-ul.

`core/conversation.py` (`handle_message`) implementează Milestone 0.1: înregistrează intrarea ca eveniment `session.message`, adună context (ultimele mesaje din aceeași sesiune + ultimele candidate de memorie, indiferent de sesiune — memoria e recuperabilă cross-session, mesajele brute nu), cheamă backend-ul, înregistrează răspunsul și orice memorie propusă cu `source_event_ids` verificabile. E agnostic de canal: `apps/cli/jarvis.py` e primul apelant; un adapter Telegram viitor trebuie să cheme aceeași funcție, nu să-și reimplementeze fluxul.

`apps/cli/jarvis.py` expune: `chat`, `status`, `approvals list`/`approvals decide` (peste tabela de aprobări deja construită în Faza A), `healthcheck` (verifică migrațiile și disponibilitatea `age`), și `kill` — un no-op onest, pentru că nu există încă scheduler/job supervisor de oprit (vine în Faza C).

## Implementare: canal Telegram

`apps/telegram/client.py` e un client minimal peste Telegram Bot API, doar `urllib` din stdlib, cu long-polling (`getUpdates`) — nu webhook, ca să nu fie nevoie de port public sau certificat TLS pe o mașină personală. Token-ul nu ajunge niciodată în mesajele de eroare, în ledger sau în contextul modelului; e folosit doar de apelurile HTTP din acest client.

`apps/telegram/bot.py` (`process_updates`) rutează un mesaj către `core.conversation.handle_message` doar dacă `from.id` e în `TELEGRAM_ALLOWED_USERS`. Orice alt expeditor e respins și respingerea devine un eveniment `channel.message_rejected` în ledger — o încercare de contact neautorizată e auditabilă, nu doar ignorată tăcut. Sesiunea e `telegram:<chat_id>`, deci contextul se comportă identic cu CLI-ul (izolat per conversație, cu memoria recuperabilă cross-sesiune).

**Configurare (o singură dată):**

1. Creează un bot cu [@BotFather](https://t.me/BotFather) pe Telegram (`/newbot`) și copiază token-ul primit.
2. Află-ți id-ul numeric de utilizator Telegram (de ex. trimite un mesaj către [@userinfobot](https://t.me/userinfobot)).
3. Pune în `.env` (niciodată în Git): `TELEGRAM_BOT_TOKEN=<token>` și `TELEGRAM_ALLOWED_USERS=<id-ul tău>` (listă separată prin virgulă dacă sunt mai mulți).
4. Testează manual: `set -a; source .env; set +a; JARVIS_CODEX_DATA_DIR=./data/live python3 apps/telegram/bot.py`, apoi scrie-i botului pe Telegram.
5. Pentru rulare permanentă, vezi `systemd/jarviscodex-telegram.service` — ajustează căile dacă clona ta nu e în `~/Work/JarvisCodex`, apoi:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/jarviscodex-telegram.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now jarviscodex-telegram.service
   journalctl --user -u jarviscodex-telegram.service -f
   ```

Backend-ul e ales din `JARVIS_CODEX_BACKEND` (`backends/factory.py`), implicit `echo` — schimbarea la un provider real e o variabilă de mediu, nu o modificare de cod în logica de autentificare/rutare.

## Implementare: ReasoningBackend real (Claude)

`backends/claude.py` (`ClaudeBackend`) cheamă Anthropic Messages API direct cu `urllib` din stdlib. Cheia (`ANTHROPIC_API_KEY`) e folosită doar în headerul cererii — nu ajunge în ledger, în context sau într-un mesaj de eroare. Modelul e configurabil prin `ANTHROPIC_MODEL` (implicit `claude-sonnet-5`).

Propunerea de memorie nu se face prin parsare de text liber, ci printr-un tool call explicit (`propose_memory`, cu `statement` + `confidence`) — modelul decide activ că ceva merită reținut, nu ghicim dintr-un răspuns. `source_event_ids` rămâne gol în propunere; `core/conversation.py` completează automat id-ul evenimentului sursă, la fel ca la `EchoBackend`.

Activare: `JARVIS_CODEX_BACKEND=claude` + `ANTHROPIC_API_KEY=...` în `.env`. Fără asta, sistemul rămâne pe `echo` — nicio schimbare de cod nu poate produce accidental un apel plătit.

## Implementare: ReasoningBackend prin `codex` CLI (fără cheie API separată)

`backends/codex_cli.py` (`CodexCliBackend`) rutează prin `codex exec` local, refolosind un abonament ChatGPT/Codex deja autentificat (`~/.codex/auth.json`) în loc de o cheie API separată plătită per-token. Rulează izolat: director scratch gol proaspăt creat la fiecare apel (`--skip-git-repo-check`, `--ephemeral`), `--sandbox read-only` (nu poate scrie sau executa nimic), `stdin=DEVNULL` (nu se blochează niciodată așteptând input). Nu ajunge niciun secret prin acest modul — autentificarea e gestionată integral de `codex` însuși.

Fără tool-use structurat disponibil peste această interfață, propunerea de memorie se face printr-un marker pe ultimul rând al răspunsului (`MEMORY: <afirmație> | confidence=<0-1>`), extras și eliminat din textul vizibil înainte de a fi întors — mai fragil decât tool call-ul din `backends/claude.py`, dar singura opțiune practică pentru un CLI fără API structurat.

Activare: `JARVIS_CODEX_BACKEND=codex` în `.env` — necesită `codex` autentificat și instalat pe `PATH` (`codex doctor` verifică starea), nimic altceva.
