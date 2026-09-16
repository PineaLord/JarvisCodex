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
