# Backup, recovery și continuitate

Scopul nu este doar să salvezi fișiere, ci să poți reconstrui o instanță funcțională a lui JarvisCodex pe hardware nou.

## Ce se salvează

```text
ledger SQLite + attachments + export memory + projects + plugins + policy
config fără secrete + manifest de versiuni + checksum-uri + instrucțiuni restore
```

Secretele au flux separat: keyring/password manager și procedură documentată de reprovisionare. Nu sunt în Git și nu intră în exportul de memorie.

## Standard operațional

- strategie 3-2-1: trei copii, două tipuri de mediu, una în afara calculatorului;
- arhive criptate, cu integritate verificată;
- backup incremental zilnic și snapshot înainte de L3–L5;
- restore testat periodic într-un director/machine curat;
- obiectiv măsurabil: RPO (câtă stare poți pierde) și RTO (cât durează reactivarea).

## Test de restore obligatoriu

Un test automat creează date de referință, face backup, restaurează într-un mediu gol și verifică: numărul de evenimente, hash-urile, memoriile cu provenance, pluginurile active și faptul că serviciul pornește în dry-run. Fără acest test, promisiunea de „creier recuperabil” nu este demonstrată.

`tests/recovery/test_restore.py` acoperă partea de bază (evenimente, hash, provenance) prin copiere de fișier. `tests/recovery/test_backup_restore.py` acoperă fluxul complet criptat de mai jos. Pluginurile active și boot-ul de serviciu în dry-run rămân pentru Faza A.4 (policy engine + executor).

## Implementare: backup criptat cu `age`

Criptare asimetrică (`age -r <recipient>`): procesul de backup are nevoie doar de o cheie publică, niciodată de cea privată. Cheia privată e singurul secret din acest flux.

**O singură dată, pe orice mașină de pe care faci backup:**

```bash
omarchy pkg add age               # dacă nu e deja instalat
age-keygen -o ~/jarviscodex-backup-identity.txt
```

Fișierul conține pe prima linie `# public key: age1...` și pe a doua identitatea privată (`AGE-SECRET-KEY-...`).

1. Copiază linia `age1...` (cheia publică) în `JARVIS_CODEX_BACKUP_RECIPIENT` din `.env` — nu e secretă, poate sta și necriptată.
2. Mută conținutul întregului fișier (identitatea privată) într-un password manager / keyring. Păstrează o copie locală doar dacă mașina face restore-uri automate; altfel șterge-o de pe disc după ce e salvată în siguranță.
3. Nu comite niciodată `jarviscodex-backup-identity.txt` — `secrets/` și `*.txt` cu identități nu intră în Git.

**Backup:**

```bash
JARVIS_CODEX_DATA_DIR=/path/to/data/live \
JARVIS_CODEX_BACKUP_RECIPIENT=age1... \
python3 scripts/backup_now.py
```

Scrie `jarvis-<timestamp>.tar.gz.age` (criptat: ledger SQLite + export Markdown/JSON) și `jarvis-<timestamp>.manifest.json` (necriptat: checksum-uri SHA-256 per fișier, hash-ul arhivei, numărul de evenimente, `schema_version`).

**Restore:**

```bash
python3 scripts/restore_backup.py jarvis-<ts>.tar.gz.age jarvis-<ts>.manifest.json \
    /path/to/identity.txt /path/to/dest_dir
```

Decriptarea verifică hash-ul arhivei față de manifest înainte de extragere, apoi fiecare fișier extras față de checksum-ul lui — un backup corupt sau modificat e respins, nu restaurat parțial. Vezi `recovery/backup.py` și `recovery/restore.py`.
