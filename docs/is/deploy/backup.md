# Öryggisafritun og endurheimt

`opencde backup MAPPA` skrifar möppu `MAPPA/opencde-backup-<UTC-tími>/` með

| Skrá | Innihald |
|---|---|
| `nodes.jsonl.gz` | hver hnútur: merkimiðar og eigindi, einn JSON-hlutur á línu |
| `relationships.jsonl.gz` | hvert vensl, með upphafs- og endahnút tilgreinda með einkvæmum lyklum sínum |
| `storage.tar.gz` | geymslumappan: skjöl, snapshots, bitmaps, snippets |
| `manifest.json` | snið, tími, útgáfa þjónsins, mállýska, fjöldi, SHA-256 hverrar skrár |

Hnútar eru auðkenndir með einkvæmum lyklum skemans (`id`, `guid`,
`project_id`, …), aldrei með innri auðkennum gagnagrunnsins, svo að
öryggisafrit tekið úr Neo4j endurheimtist í Memgraph og öfugt (ADR 0006).
Gagnagrunnurinn keyrir áfram meðan afritað er; afrit tekið meðan upphal eru í
gangi getur vantað hluta þeirra upphala, sem biðlararnir einfaldlega
endurtaka.

Með eigin gögn þjónsins í eigin grafi (`OPENCDE_STORE_GRAPH_URI`,
[ifc-lpg.md](../ifc-lpg.md)) heldur eitt öryggisafrit báðum gröfunum í sömu
skrám, hnútum IFC-LPG úr IFC-grafinu og hinu úr geymslunni, og
`manifest.json` nefnir mállýsku geymslunnar í `store_dialect`. Endurheimt
setur hvern hnút þangað sem merkimiði hans á heima, hvaða gröfum sem afritið
kom úr, svo að afrit af einum gagnagrunni endurheimtist í tvo og öfugt; hún
neitar nema báðir séu tómir eða `--force` sé gefið, og sleppir venslum milli
tegundanna tveggja, sem aðeins gagnagrunnur frá því fyrir ADR 0027 getur
haldið.

## Endurheimt

```sh
opencde restore MAPPA/opencde-backup-20261105T031700Z           # í tóman gagnagrunn
opencde restore MAPPA/opencde-backup-20261105T031700Z --force   # skipta út núverandi innihaldi
```

`restore` staðfestir gátsummurnar, neitar gagnagrunni sem er ekki tómur nema
með `--force`, endurgerir hnúta og vensl í lotum og pakkar skránum upp í
geymslumöppuna. Setur og tókar eru líka endurheimt; keyrðu
`opencde revoke --all` eftir á ef afritið er gamalt eða kemur frá öðrum þjóni.

## Í Docker Compose

`docker/compose.prod.yaml` keyrir þjónustu `backup` sem kallar
`opencde backup /backups` einu sinni á dag og heldur 14 nýjustu möppunum í
geymslunni `backups`. Afritaðu þá geymslu eitthvert annað (annan hýsil,
hlutageymslu); öryggisafrit á sama diski og gögnin er bara hálft öryggisafrit:

```sh
docker run --rm -v dataregium_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dataregium-backups.tgz -C /backups .
```

Uppsetning sem hélt gamla verkefnisheitinu hefur geymsluna sem `kontroll_backups`.

Til að endurheimta á nýjum hýsli: ræstu staflann, afritaðu öryggisafritsmöppu
inn í gáminn `api` (eða tengdu hana) og keyrðu
`docker compose exec api opencde restore /slóð --force`.

## Prófaðu endurheimtina þína

Öryggisafrit sem þú hefur aldrei endurheimt er von, ekki öryggisafrit.
Samþættingarprófið `tests/integration/test_backup.py` endurheimtir afrit í
tóman gagnagrunn bæði á Neo4j og Memgraph; gerðu það sama einu sinni á
prófunartilviki eftir að rekstur er settur upp.
