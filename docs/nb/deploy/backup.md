# Sikkerhetskopiering og gjenoppretting

`opencde backup MAPPE` skriver en mappe `MAPPE/opencde-backup-<UTC-tid>/` med

| Fil | Innhold |
|---|---|
| `nodes.jsonl.gz` | hver node: etiketter og egenskaper, ett JSON-objekt per linje |
| `relationships.jsonl.gz` | hver relasjon, med start- og sluttnode angitt ved sine unike nøkler |
| `storage.tar.gz` | lagringsmappen: dokumenter, snapshots, bitmaps, snippets |
| `manifest.json` | format, tid, serverversjon, dialekt, antall, SHA-256 for hver fil |

Noder identifiseres med skjemaets unike nøkler (`id`, `guid`, `project_id`, …),
aldri med databaseinterne id-er, så en sikkerhetskopi tatt fra Neo4j kan
gjenopprettes i Memgraph og omvendt (ADR 0006). Databasen kjører videre under
sikkerhetskopieringen; en kopi tatt mens opplastinger pågår, kan mangle delene
av de opplastingene, som klientene ganske enkelt gjør om igjen.

Med serverens egne data i en egen graf (`OPENCDE_STORE_GRAPH_URI`,
[ifc-lpg.md](../ifc-lpg.md)) holder én sikkerhetskopi begge grafene i de samme
filene, IFC-LPGs noder fra IFC-grafen og resten fra lageret, og
`manifest.json` angir lagerets dialekt i `store_dialect`. En gjenoppretting
legger hver node der etiketten hører hjemme, uansett hvilke grafer kopien kom
fra, slik at en kopi av én database gjenopprettes i to og omvendt; den nekter
med mindre begge er tomme eller `--force` gis, og utelater en relasjon mellom
de to slagene, som bare en database fra før ADR 0027 kan holde.

## Gjenoppretting

```sh
opencde restore MAPPE/opencde-backup-20261105T031700Z           # inn i en tom database
opencde restore MAPPE/opencde-backup-20261105T031700Z --force   # erstatt det nåværende innholdet
```

`restore` verifiserer kontrollsummene, avviser en ikke-tom database uten
`--force`, gjenskaper noder og relasjoner i bunter og pakker ut filene i
lagringsmappen. Sesjoner og tokens gjenopprettes også; kjør
`opencde revoke --all` etterpå hvis kopien er gammel eller kommer fra en annen
server.

## I Docker Compose

`docker/compose.prod.yaml` kjører en tjeneste `backup` som kaller
`opencde backup /backups` én gang om dagen og beholder de 14 nyeste mappene i
volumet `backups`. Kopier det volumet et annet sted (en annen vert,
objektlagring); en sikkerhetskopi på samme disk som dataene er bare en halv
sikkerhetskopi:

```sh
docker run --rm -v dataregium_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dataregium-backups.tgz -C /backups .
```

En installasjon som har beholdt det gamle prosjektnavnet, har volumet som `kontroll_backups`.

For å gjenopprette på en ny vert: start stakken, kopier en sikkerhetskopimappe
inn i containeren `api` (eller monter den) og kjør
`docker compose exec api opencde restore /sti --force`.

## Test gjenopprettingen din

En sikkerhetskopi du aldri har gjenopprettet, er et håp, ikke en
sikkerhetskopi. Integrasjonstesten `tests/integration/test_backup.py`
gjenoppretter en kopi i en tom database på både Neo4j og Memgraph; gjør det
samme én gang på en staging-instans etter at produksjonen er satt opp.
