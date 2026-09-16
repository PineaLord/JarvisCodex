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
