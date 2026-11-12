# Säkerhetskopiering och återställning

`opencde backup KATALOG` skriver en mapp `KATALOG/opencde-backup-<UTC-tid>/` med

| Fil | Innehåll |
|---|---|
| `nodes.jsonl.gz` | varje nod: etiketter och egenskaper, ett JSON-objekt per rad |
| `relationships.jsonl.gz` | varje relation, med start- och slutnod angivna genom sina unika nycklar |
| `storage.tar.gz` | lagringskatalogen: dokument, snapshots, bitmaps, snippets |
| `manifest.json` | format, tid, serverversion, dialekt, antal, SHA-256 för varje fil |

Noder identifieras med schemats unika nycklar (`id`, `guid`, `project_id`, …),
aldrig med databasinterna id:n, så en säkerhetskopia tagen från Neo4j kan
återställas i Memgraph och tvärtom (ADR 0006). Databasen fortsätter köra under
säkerhetskopieringen; en kopia tagen medan uppladdningar pågår kan sakna
delarna av de uppladdningarna, vilket klienterna helt enkelt gör om.

Med serverns egna data i en egen graf (`OPENCDE_STORE_GRAPH_URI`,
[ifc-lpg.md](../ifc-lpg.md)) håller en säkerhetskopia båda graferna i samma
filer, IFC-LPG:s noder från IFC-grafen och resten från lagret, och
`manifest.json` anger lagrets dialekt i `store_dialect`. En återställning
lägger varje nod där dess etikett hör hemma, vilka grafer kopian än kom från,
så en kopia av en databas återställs i två och tvärtom; den vägrar om inte
båda är tomma eller `--force` ges, och utelämnar en relation mellan de två
slagen, som bara en databas från före ADR 0027 kan hålla.

## Återställning

```sh
opencde restore KATALOG/opencde-backup-20261105T031700Z           # till en tom databas
opencde restore KATALOG/opencde-backup-20261105T031700Z --force   # ersätt nuvarande innehåll
```

`restore` kontrollerar kontrollsummorna, vägrar en icke-tom databas utan
`--force`, återskapar noder och relationer i omgångar och packar upp filerna i
lagringskatalogen. Sessioner och tokens återställs också; kör
`opencde revoke --all` efteråt om kopian är gammal eller kommer från en annan
server.

## I Docker Compose

`docker/compose.prod.yaml` kör en tjänst `backup` som anropar `opencde backup /backups`
en gång om dagen och behåller de 14 nyaste mapparna i volymen `backups`.
Kopiera den volymen någon annanstans (en annan värd, objektlagring); en
säkerhetskopia på samma disk som datat är bara en halv säkerhetskopia:

```sh
docker run --rm -v dataregium_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dataregium-backups.tgz -C /backups .
```

En installation som behållit det gamla projektnamnet har volymen som `kontroll_backups`.

För att återställa på en ny värd: starta stacken, kopiera en
säkerhetskopiemapp in i containern `api` (eller montera den) och kör
`docker compose exec api opencde restore /sökväg --force`.

## Testa din återställning

En säkerhetskopia du aldrig har återställt är en förhoppning, inte en
säkerhetskopia. Integrationstestet `tests/integration/test_backup.py`
återställer en kopia i en tom databas på både Neo4j och Memgraph; gör samma
sak en gång på en testinstans när produktionen är uppsatt.
