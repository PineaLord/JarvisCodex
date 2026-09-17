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

## Implementare: canal CLI + ReasoningBackend

`contracts/reasoning.py` fixează contractul: un `ReasoningRequest` (text, context recuperat, id-ul evenimentului sursă) intră, un `ReasoningResponse` (text + propuneri de memorie cu surse) iese. `backends/echo.py` e o implementare locală, fără cost și fără rețea, care dovedește restul fluxului înainte de a conecta un provider real (Claude/Codex/local) — schimbarea backend-ului nu atinge `core/conversation.py` sau CLI-ul.

`core/conversation.py` (`handle_message`) implementează Milestone 0.1: înregistrează intrarea ca eveniment `session.message`, adună context (ultimele mesaje din aceeași sesiune + ultimele candidate de memorie, indiferent de sesiune — memoria e recuperabilă cross-session, mesajele brute nu), cheamă backend-ul, înregistrează răspunsul și orice memorie propusă cu `source_event_ids` verificabile. E agnostic de canal: `apps/cli/jarvis.py` e primul apelant; un adapter Telegram viitor trebuie să cheme aceeași funcție, nu să-și reimplementeze fluxul.

`apps/cli/jarvis.py` expune: `chat`, `status`, `approvals list`/`approvals decide` (peste tabela de aprobări deja construită în Faza A), `healthcheck` (verifică migrațiile și disponibilitatea `age`), și `kill` — un no-op onest, pentru că nu există încă scheduler/job supervisor de oprit (vine în Faza C). Adapterul Telegram din roadmap rămâne neconstruit.
