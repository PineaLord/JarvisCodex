# Stare, memorie și proveniență

## Două forme ale aceleiași realități

**SQLite** este sursa tranzacțională pentru evenimente, aprobări, taskuri, relații și deduplicare. **Markdown/JSON/YAML** sunt proiecții lizibile de om și exporturi portabile. Nu folosim fișiere JSONL drept singurul adevăr pentru starea concurentă.

```text
input → event immutable → projections → candidate memory → approved/consolidated memory
                  │                                  │
                  └──────── source IDs ──────────────┘
```

## Tipuri de memorie

| Tip | Exemplu | Reprezentare exportată |
|---|---|---|
| Episodică | „am discutat X luni” | jurnal zilnic |
| Semantică | „preferă local-first” | note pe concept/persoană/sistem |
| Procedurală | workflow reutilizabil | plugin/skill versionat |
| Working state | proiect, deadline, open loop | YAML per proiect |

Fiecare afirmație memorată are: `id`, afirmație, încredere, surse (`event_id`), momentul revizuirii, politică de retenție și statut. O memorie poate fi corectată sau retrasă; nu se rescrie tăcut.

## Date care nu intră automat în memorie

Conversația brută, parolele, tokenurile, datele financiare sau inferențele sensibile nu devin semantic memory fără o regulă explicită și, unde e nevoie, confirmarea utilizatorului.

## Migrații

Toate evenimentele și toate schemele au `schema_version`. Migrațiile sunt idempotente, testate pe o copie și incluse în backup/restore. Aceasta e condiția pentru ca „creierul” să poată fi reactivat peste ani.
