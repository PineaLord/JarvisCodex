# Sistemul de pluginuri

Un plugin nu este cod cu acces liber la sistem. Este un pachet versionat cu manifest, scheme de input/output, capabilități declarate, nivel de risc, teste și instrucțiuni de rollback.

## Viața unui plugin

```text
draft → validate manifest/tests → review → active → deprecated/revoked
```

Activarea, extinderea permisiunilor și actualizarea unui plugin sunt acțiuni separate. Niciun plugin nu se activează singur, inclusiv unul generat de agent.

## Tipuri inițiale

- `memory-consolidator` — produce candidate memories, nu rescrie profilul.
- `research` — citește surse și produce raport cu provenance.
- `project-review` — detectează open loops și propune taskuri.
- `omarchy-observer` — colectează numai telemetrie aprobată.

Vezi [manifestul de exemplu](../plugins/core/research/plugin.yaml). Un plugin de sistem se execută printr-un adapter controlat, niciodată direct din prompt.
