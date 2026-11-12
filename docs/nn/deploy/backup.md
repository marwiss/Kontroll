# Tryggingskopiering og gjenoppretting

`opencde backup MAPPE` skriv ei mappe `MAPPE/opencde-backup-<UTC-tid>/` med

| Fil | Innhald |
|---|---|
| `nodes.jsonl.gz` | kvar node: etikettar og eigenskapar, eitt JSON-objekt per linje |
| `relationships.jsonl.gz` | kvar relasjon, med start- og sluttnode oppgjevne ved dei unike nøklane sine |
| `storage.tar.gz` | lagringsmappa: dokument, snapshots, bitmaps, snippets |
| `manifest.json` | format, tid, serverversjon, dialekt, tal, SHA-256 for kvar fil |

Nodar blir identifiserte med dei unike nøklane i skjemaet (`id`, `guid`,
`project_id`, …), aldri med databaseinterne id-ar, så ein tryggingskopi
teken frå Neo4j kan gjenopprettast i Memgraph og omvendt (ADR 0006). Databasen
køyrer vidare under tryggingskopieringa; ein kopi teken medan opplastingar
er i gang, kan mangle delane av dei opplastingane, som klientane ganske enkelt
gjer om igjen.

Med dei eigne dataa til serveren i ein eigen graf (`OPENCDE_STORE_GRAPH_URI`,
[ifc-db.md](../ifc-db.md)) held éin tryggingskopi begge grafane i dei same
filene, nodane til IFC-DB frå IFC-grafen og resten frå lageret, og
`manifest.json` oppgjev dialekten til lageret i `store_dialect`. Ei
gjenoppretting legg kvar node der etiketten høyrer heime, kva grafar kopien
enn kom frå, slik at ein kopi av éin database blir gjenoppretta i to og
omvendt; ho nektar med mindre begge er tomme eller `--force` blir gjeve, og
utelèt ein relasjon mellom dei to slaga, som berre ein database frå før
ADR 0027 kan halde.

## Gjenoppretting

```sh
opencde restore MAPPE/opencde-backup-20261105T031700Z           # inn i ein tom database
opencde restore MAPPE/opencde-backup-20261105T031700Z --force   # erstatt det noverande innhaldet
```

`restore` verifiserer kontrollsummane, avviser ein ikkje-tom database utan
`--force`, gjenskaper nodar og relasjonar i buntar og pakkar ut filene i
lagringsmappa. Sesjonar og tokens blir gjenoppretta òg; køyr
`opencde revoke --all` etterpå om kopien er gammal eller kjem frå ein annan
server.

## I Docker Compose

`docker/compose.prod.yaml` køyrer ei teneste `backup` som kallar
`opencde backup /backups` éin gong om dagen og held på dei 14 nyaste mappene i
volumet `backups`. Kopier det volumet ein annan stad (ein annan vert,
objektlagring); ein tryggingskopi på same disk som dataa er berre ein halv
tryggingskopi:

```sh
docker run --rm -v dataregium_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dataregium-backups.tgz -C /backups .
```

Ein installasjon som har halde på det gamle prosjektnamnet, har volumet som `kontroll_backups`.

For å gjenopprette på ein ny blir: start stakken, kopier ei
tryggingskopimappe inn i containeren `api` (eller monter henne) og køyr
`docker compose exec api opencde restore /sti --force`.

## Test gjenopprettinga di

Ein tryggingskopi du aldri har gjenoppretta, er eit håp, ikkje ein
tryggingskopi. Integrasjonstesten `tests/integration/test_backup.py`
gjenopprettar ein kopi i ein tom database på både Neo4j og Memgraph; gjer det
same éin gong på ein staging-instans etter at produksjonen er sett opp.
