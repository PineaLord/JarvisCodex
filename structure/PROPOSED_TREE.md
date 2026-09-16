# Arbore propus

```text
JarvisCodex/
├── apps/                    # adapters: CLI, Telegram, viitor UI
├── core/                    # orchestration, intents, goals, context
├── contracts/               # interfețe stabile și modele tipizate
├── storage/                 # SQLite ledger, projections, migrations
├── memory/                  # exporters și formate lizibile, nu raw secrets
├── policy/                  # rules, capabilities, evaluare de risc
├── executors/               # sandbox, process supervisor, tool adapters
├── backends/                # Claude/Codex/local implementations
├── plugins/
│   ├── core/                # pluginuri de referință, versionate
│   ├── drafts/
│   ├── active/
│   └── registry.yaml
├── recovery/                # backup, restore, verificare integritate
├── observability/           # health, audit, metrici fără secrete
├── schemas/                 # JSON Schema publică și versionată
├── systemd/                 # unități user service/timer
├── scripts/                 # tooling local, niciun secret
├── tests/                   # policy, restore, contract, integrare
└── docs/
```

`data/live/`, `runtime/`, `backups/` și `secrets/` sunt intenționat excluse din Git.
