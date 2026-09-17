# Roadmap

## Faza A — nucleu durabil

1. Scheme versionate pentru event, task, approval și memory candidate.
2. SQLite ledger + proiecții Markdown/JSON exportabile.
3. Backup criptat + test automat de restore.
4. Policy engine testat adversarial și executor dry-run.

## Faza B — conversație și memorie

1. CLI local, apoi adapter Telegram autentificat.
2. `ReasoningBackend` cu un singur provider.
3. Session events, retrieval și candidate memory cu provenance.
4. `/status`, `/approvals`, `/kill` și healthcheck.

## Faza C — inițiativă controlată

1. intent → signal → candidate initiative → goal.
2. consolidation loop.
3. heartbeat rar, bugetat, fără L3–L5.

## Faza D — extensii și evoluție

1. plugin registry și pluginuri draft/review/activate.
2. JEP, sandbox de patch-uri, test, snapshot, aprobare, rollback.
3. Observare Omarchy și numai apoi propuneri de configurare.
4. Backend local/hibrid, fără schimbarea stării sau politicilor.

## Implementare: Faza C

`core/initiative.py` — euristică deterministă, fără ML: o afirmație de memorie propusă de cel puțin două ori (`REPEAT_THRESHOLD`) devine un `signal.detected`; un semnal devine un `initiative.proposed` la nivel **L2 fix, niciodată mai sus**. Orice inițiativă trece prin *același* `RuleBasedPolicyEngine` ca orice altă acțiune (`contracts/policy.py`) — nu există o cale de aprobare separată, "mai relaxată" pentru ideile proprii ale sistemului.

`run_consolidation` (bucla de consolidare) rulează pasul complet: detectează semnale, propune inițiative, reevaluează orice inițiativă încă `proposed` — dacă politica zice `allow`, inițiativa e acceptată și devine `goal.created` (+ `memory.candidate_confirmed`); dacă `require_approval`, apare direct în `jarvis approvals list` (nu există o listă separată de inițiative de aprobat); dacă `deny`, e respinsă cu motiv. Nimic nu se scrie direct în tabela `initiatives` în afara evenimentelor — starea „în așteptare” se recalculează la fiecare trecere, nu se persistă separat.

`run_heartbeat` = un pas de consolidare cu buget zilnic pe capabilitatea `memory.consolidate` (cota vine din `policy/engine.py`, care acum își derivă utilizarea din evenimentele `action.simulated` de azi din ledger — **nu** dintr-un contor în memorie, altfel bugetul zilnic nu ar supraviețui unei reporniri de proces, exact scenariul unui heartbeat rulat periodic). Cooldown per subiect (`SIGNAL_COOLDOWN_HOURS`) evită resemnalarea aceleiași afirmații la fiecare trecere.

`jarvis heartbeat` (CLI) rulează un pas manual. `systemd/jarviscodex-heartbeat.{service,timer}` rulează unul automat, rar (implicit la 6 ore) — fișierele există, dar **nu sunt activate automat**; activarea e o decizie a utilizatorului:
```bash
cp systemd/jarviscodex-heartbeat.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jarviscodex-heartbeat.timer
```

Heartbeat-ul întoarce un singur rezumat agregat (nu un mesaj per eveniment) — trimiterea lui pe un canal (Telegram) rămâne o decizie separată, neconstruită încă, tocmai pentru că un mesaj proactiv nesolicitat e mai aproape de „efect extern” (L4) decât de observare autonomă.

## Criteriu de trecere

Nu avansezi la o fază până când testele de recovery, policy și audit ale fazei precedente nu trec. Funcții noi fără recuperabilitate și control cresc fragilitatea, nu inteligența.
