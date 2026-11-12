# Sikkerhedskopiering og gendannelse

`opencde backup MAPPE` skriver en mappe `MAPPE/opencde-backup-<UTC-tid>/` med

| Fil | Indhold |
|---|---|
| `nodes.jsonl.gz` | hver node: etiketter og egenskaber, ét JSON-objekt pr. linje |
| `relationships.jsonl.gz` | hver relation, med start- og slutnode angivet ved deres unikke nøgler |
| `storage.tar.gz` | lagermappen: dokumenter, snapshots, bitmaps, snippets |
| `manifest.json` | format, tid, serverversion, dialekt, antal, SHA-256 for hver fil |

Noder identificeres ved skemaets unikke nøgler (`id`, `guid`, `project_id`, …),
aldrig ved databaseinterne id'er, så en sikkerhedskopi taget fra Neo4j kan
gendannes i Memgraph og omvendt (ADR 0006). Databasen kører videre under
sikkerhedskopieringen; en kopi taget, mens uploads er i gang, kan mangle
delene af de uploads, hvilket klienterne blot gør om.

Med serverens egne data i en graf for sig (`OPENCDE_STORE_GRAPH_URI`,
[ifc-lpg.md](../ifc-lpg.md)) holder én sikkerhedskopi begge grafer i de samme
filer, IFC-LPG's knuder fra IFC-grafen og resten fra lageret, og
`manifest.json` angiver lagerets dialekt i `store_dialect`. En gendannelse
lægger hver knude, hvor dens etiket hører hjemme, uanset hvilke grafer kopien
kom fra, så en kopi af én database gendannes i to og omvendt; den nægter,
medmindre begge er tomme eller `--force` gives, og udelader en relation mellem
de to slags, som kun en database fra før ADR 0027 kan holde.

## Gendannelse

```sh
opencde restore MAPPE/opencde-backup-20261105T031700Z           # i en tom database
opencde restore MAPPE/opencde-backup-20261105T031700Z --force   # erstat det nuværende indhold
```

`restore` kontrollerer kontrolsummerne, afviser en ikke-tom database uden
`--force`, genskaber noder og relationer i partier og pakker filerne ud i
lagermappen. Sessioner og tokens gendannes også; kør `opencde revoke --all`
bagefter, hvis kopien er gammel eller kommer fra en anden server.

## I Docker Compose

`docker/compose.prod.yaml` kører en tjeneste `backup`, der kalder
`opencde backup /backups` én gang om dagen og beholder de 14 nyeste mapper i
volumen `backups`. Kopiér den volume et andet sted hen (en anden vært,
objektlager); en sikkerhedskopi på samme disk som dataene er kun en halv
sikkerhedskopi:

```sh
docker run --rm -v dataregium_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dataregium-backups.tgz -C /backups .
```

En installation, der har beholdt det gamle projektnavn, har volumen som `kontroll_backups`.

For at gendanne på en ny vært: start stakken, kopiér en sikkerhedskopimappe
ind i containeren `api` (eller montér den), og kør
`docker compose exec api opencde restore /sti --force`.

## Test din gendannelse

En sikkerhedskopi, du aldrig har gendannet, er et håb, ikke en sikkerhedskopi.
Integrationstesten `tests/integration/test_backup.py` gendanner en kopi i en
tom database på både Neo4j og Memgraph; gør det samme én gang på en
staging-instans, når produktionen er sat op.
