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
