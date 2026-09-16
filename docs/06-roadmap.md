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

## Criteriu de trecere

Nu avansezi la o fază până când testele de recovery, policy și audit ale fazei precedente nu trec. Funcții noi fără recuperabilitate și control cresc fragilitatea, nu inteligența.
