# Model de siguranță

## Niveluri de efect

| Nivel | Efect | Regim |
|---|---|---|
| L0 | observare | autonom |
| L1 | reasoning, raport, draft | autonom |
| L2 | write în spațiul Jarvis | politică + quota |
| L3 | configurare/servicii/pachete | aprobare explicită |
| L4 | efect extern/API/mesaje către alții | aprobare explicită |
| L5 | distructiv, privilegii, credențiale | aprobare puternică + confirmare de țintă |

## Reguli structurale

- Datele web, documentele, emailurile și repository-urile sunt date neîncrezătoare, nu instrucțiuni.
- Modelul nu clasifică propria acțiune; executorul cere o decizie semnată de policy engine.
- Secretul nu ajunge în contextul LLM. Brokerul livrează doar o capacitate punctuală, de exemplu `telegram.send(owner, message)`.
- `/kill` trece direct de LLM, scheduler și queue; oprește doar arborii de procese ai joburilor, nu control plane-ul.
- Orice acțiune L3–L5 are: intenție, ținte exacte, diff/preview, expirare, aprobare, rezultat și rollback unde este posibil.

Matching-ul pe stringuri de shell este insuficient pentru producție. Executorul trebuie să folosească tooluri tipizate sau parsare/allow-list strictă, în sandbox/cgroup pentru joburile neprivilegiate.

## Implementare: policy engine + executor dry-run

`policy/capabilities.py` e sursa unică a nivelului de risc: fiecare capabilitate înregistrată are un `min_level` fix și câmpuri țintă tipizate, obligatorii. O capabilitate nefolosită nu există pentru motor — implicit refuzată. Nu există nicio intrare pentru un "shell exec" generic cu string liber: regula de mai sus e impusă structural, prin simplul fapt că un astfel de tool nu e niciodată înregistrat.

`policy/engine.py` (`RuleBasedPolicyEngine.evaluate`):

- `declared_level` al unui plugin e acceptat doar dacă cere *mai multă* scrutinare decât minimul din registry, niciodată mai puțină.
- Câmpurile țintă lipsă sau cu tip greșit (ex. un dict injectat unde se aștepta un string) → `deny`, nu o încercare de reparare silențioasă.
- Căi de fișier sunt normalizate (`posixpath.normpath`) și verificate contra unei liste albe de prefixe — un `../../etc/passwd` e respins.
- Date cu proveniență neîncrezătoare (`source_trust="untrusted"`) forțează `require_approval` de la L2 în sus, indiferent de cotă.
- L3–L5 fără `target`, `diff_preview` și `requested_expires_in_seconds` → `deny` direct, nu aprobare cu informație incompletă.
- O aprobare cerută devine un eveniment `approval.requested` (cu `expires_at`) în ledger-ul existent — aceeași sursă de adevăr ca restul stării, nu un canal separat. O cerere reevaluată de mai multe ori nu duplică evenimentul.
- O aprobare `pending` expirată devine `deny`, nu rămâne valabilă la nesfârșit.

`policy/executor.py` (`DryRunExecutor`) nu produce niciodată un efect real: pentru o decizie `allow` scrie un eveniment `action.simulated` cu previzualizarea acțiunii; pentru `deny`/`require_approval` întoarce direct motivul, fără să încerce nimic. Acesta e singurul executor care există înainte de Faza C.

Audit-ul e implicit: fiecare decizie de politică care ajunge la `require_approval` sau `allow` (prin simulare) devine un eveniment în ledger-ul din `storage/`, deci istoricul deciziilor e recuperabil exact ca restul stării — vezi `docs/05-recovery.md`.

Teste: `tests/policy/test_policy_engine.py` (fluxul normal) și `tests/policy/test_policy_adversarial.py` (încercări explicite de ocolire — capabilitate neînregistrată, auto-declarare la un nivel mai mic, path traversal, injectare de tip greșit, epuizare cotă, aprobare expirată, replay pe o cerere respinsă).
