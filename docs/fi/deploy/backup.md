# Varmuuskopiointi ja palautus

`opencde backup HAKEMISTO` kirjoittaa kansion
`HAKEMISTO/opencde-backup-<UTC-aika>/`, jossa on

| Tiedosto | Sisältö |
|---|---|
| `nodes.jsonl.gz` | jokainen solmu: nimiöt ja ominaisuudet, yksi JSON-olio per rivi |
| `relationships.jsonl.gz` | jokainen suhde, alku- ja loppusolmu nimettyinä yksilöllisillä avaimillaan |
| `storage.tar.gz` | tallennushakemisto: asiakirjat, snapshotit, bitmapit, snippetit |
| `manifest.json` | muoto, aika, palvelinversio, dialekti, lukumäärät, jokaisen tiedoston SHA-256 |

Solmut tunnistetaan skeeman yksilöllisillä avaimilla (`id`, `guid`,
`project_id`, …), ei koskaan tietokannan sisäisillä tunnuksilla, joten
Neo4j:stä otettu varmuuskopio palautuu Memgraphiin ja päinvastoin (ADR 0006).
Tietokanta jatkaa toimintaansa varmuuskopioinnin aikana; latausten ollessa
kesken otetusta kopiosta voivat puuttua niiden latausten osat, jotka asiakkaat
yksinkertaisesti tekevät uudelleen.

Kun palvelimen omat tiedot ovat omassa graafissaan (`OPENCDE_STORE_GRAPH_URI`,
[ifc-db.md](../ifc-db.md)), yksi varmuuskopio pitää molemmat graafit
samoissa tiedostoissa, IFC-DB:n solmut IFC-graafista ja muut varastosta, ja
`manifest.json` nimeää varaston dialektin kentässä `store_dialect`. Palautus
vie jokaisen solmun sinne, minne sen nimiö kuuluu, mistä graafeista kopio
tahansa tuli, joten yhden tietokannan kopio palautuu kahteen ja päinvastoin;
se kieltäytyy, elleivät molemmat ole tyhjiä tai `--force` ole annettu, ja
jättää pois näiden kahden lajin välisen suhteen, jonka vain ennen ADR 0027:ää
syntynyt tietokanta voi pitää.

## Palautus

```sh
opencde restore HAKEMISTO/opencde-backup-20261105T031700Z           # tyhjään tietokantaan
opencde restore HAKEMISTO/opencde-backup-20261105T031700Z --force   # korvaa nykyisen sisällön
```

`restore` tarkistaa tarkistussummat, kieltäytyy ei-tyhjästä tietokannasta
ilman `--force`-valitsinta, luo solmut ja suhteet uudelleen erissä ja purkaa
tiedostot tallennushakemistoon. Myös istunnot ja tokenit palautetaan; aja
`opencde revoke --all` jälkeenpäin, jos kopio on vanha tai tulee toiselta
palvelimelta.

## Docker Composessa

`docker/compose.prod.yaml` ajaa `backup`-palvelua, joka kutsuu
`opencde backup /backups` kerran päivässä ja säilyttää 14 uusinta kansiota
`backups`-taltiossa. Kopioi tuo taltio muualle (toiselle isännälle,
objektitallennukseen); samalla levyllä kuin data oleva varmuuskopio on vain
puoli varmuuskopiota:

```sh
docker run --rm -v dataregium_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dataregium-backups.tgz -C /backups .
```

Asennuksella, joka on säilyttänyt vanhan projektinimen, taltio on `kontroll_backups`.

Palauttaaksesi uudelle isännälle käynnistä pino, kopioi varmuuskopiokansio
`api`-konttiin (tai liitä se) ja aja
`docker compose exec api opencde restore /polku --force`.

## Testaa palautuksesi

Varmuuskopio, jota et ole koskaan palauttanut, on toive, ei varmuuskopio.
Integraatiotesti `tests/integration/test_backup.py` palauttaa varmuuskopion
tyhjään tietokantaan sekä Neo4j:ssä että Memgraphissa; tee sama kerran
staging-instanssissa tuotannon pystyttämisen jälkeen.
