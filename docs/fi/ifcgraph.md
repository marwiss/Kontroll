# IFC-graafi

Valinnainen IFC-graafimoduuli muuttaa lähetetyn IFC-mallin graafidataksi,
jotta BCF-viewpointin komponentit voidaan yhdistää rakennusosiin, joihin ne
viittaavat, ja jotta mallista voidaan kysyä Cypherillä asioiden ja
asiakirjojen rinnalla.

Kytke se päälle asetuksella `OPENCDE_IFCGRAPH_ENABLED=true` ja asenna
`ifcgraph`-lisäosa (`uv sync --extra ifcgraph`). Docker-kuva sisältää
lisäosan oletuksena (`ARG OPENCDE_EXTRAS` Dockerfilessa), mikä yli
kaksinkertaistaa sen koon (noin 680 MB vastaan 300 MB); rakenna
`--build-arg OPENCDE_EXTRAS=` saadaksesi kevyemmän kuvan ilman
IfcOpenShelliä, kun moduuli pysyy pois päältä.

## Mitä lähetyksessä tapahtuu

1. Documents API -lähetys valmistuu (tai tiedosto lähetetään valintasivulta,
   tai BCF-projektiasiakirja postataan) nimellä, jonka pääte on `.ifc` tai
   `.ifczip`.
2. Palvelin luo projektiin liitetyn `IfcModel`-solmun (tila `queued`) ja
   käynnistää muunnoksen taustalla, yhden kerrallaan.
3. Erillinen työprosessi (`python -m opencde.ifcgraph.worker`) jäsentää
   tiedoston IfcOpenShellillä. Se toimii aikarajalla
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minuuttia), osoiteavaruusrajalla
   POSIX-järjestelmissä (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) ja entiteettien
   ylärajalla (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). Kaatuminen tai jumiutuminen
   tappaa työprosessin, ei palvelinta. `.ifczip` puretaan lähetyksen
   kokorajan puitteissa.
4. Tietueet tuodaan erissä `UNWIND … CREATE` -lauseilla (siirrettävä Cypher,
   ei APOC:ia). `IfcModel` päätyy tilaan `done` lukumäärineen ja
   `IfcProject`-guidin kanssa, tai tilaan `failed` virheen kanssa.

## Graafi

Jokaisesta entiteetistä tulee `IfcEntity`-solmu, joka kantaa luokkaansa ja
kaikkia ylätyyppejään nimiöinä, esimerkiksi `IfcEntity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Ominaisuus | Merkitys |
|---|---|
| `id` | `<mallin tunnus>:<STEP-tunnus>`, yksilöllinen |
| `model_id`, `step_id` | malli ja tiedoston `#123`-numero |
| `ifc_class` | konkreettinen luokka |
| `GlobalId`, `Name`, `Description`, `Tag`, … | entiteetin jokainen literaaliattribuutti IFC-nimellään |

Toisiin entiteetteihin viittaavista attribuuteista tulee attribuutin mukaan
nimettyjä suhteita, jotka kirjoitetaan kuten jokainen graafin suhdetyyppi
isoin kirjaimin ja alaviivoin sanarajoilla:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Käänteisistä attribuuteista tulee myös suhteita, joten molemmat suunnat
luetaan luontevasti: `(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select-arvot puretaan (`IfcLabel('3')` muuttuu `"3"`:ksi).

Jätetään oletuksena pois (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`):
esitysalkiot, esitykset, profiilit, sijoitukset ja tyylit; ne ovat suurin osa
mallista ja harvoin sitä, mitä CDE-kysely tarvitsee. `IfcOwnerHistory`
säilytetään vain `IfcProject`-entiteetille.

## Ylläpito

Jokainen IFC-tiedoston lähetys lisää `IfcModel`-solmun entiteetteineen, joten
uusia versioita vastaanottava projekti kerää graafeja, joita kukaan ei
kysele. Komentorivi luettelee ja karsii ne; asiakirjat ja niiden tiedostot
säilyvät aina:

```sh
uv run opencde ifcgraph list --project <projektin tunnus>
uv run opencde ifcgraph prune                   # epäonnistuneet mallit sekä valmiit mallit, jotka saman asiakirjan
                                                # uudempi valmis versio on korvannut
uv run opencde ifcgraph prune --project <id> --all   # yhden projektin jokainen malli (esimerkiksi testipino)
```

Jonossa olevia ja käynnissä olevia malleja ei karsita koskaan. Kyselyjen,
jotka haluavat yhden graafin asiakirjaa kohti, tulee itse valita uusin valmis
malli, koska vanhemmat versiot säilyvät karsintaan asti:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## BCF-komponenttien linkitys

Kun viewpoint luodaan komponenttien kanssa, jokainen komponentti, jonka
`ifc_guid` vastaa jonkin projektin tuodun mallin rakennusosan
`GlobalId`-arvoa, saa `SAME_AS`-suhteen siihen. Sama linkitys ajetaan
projektin jokaiselle olemassa olevalle komponentille, kun mallin tuonti
valmistuu, joten myös ennen mallin lähettämistä tai sen muuntamisen aikana
luodut viewpointit linkitetään. Jos rakennusosa kantaa määritettyä
ominaisuutta (`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`), sen arvo kopioidaan komponenttiin
`gtin`-kenttänä. Tämä on vuoden 2023 tutkimusraportin käyttötapaus:
tarkastus (BCF-asia), joka viittaa GTIN-koodilla tunnistettuihin
rakennustuotteisiin.

```cypher
// Mihin tuotteisiin tämä viewpoint viittaa, ja mitkä ovat niiden GTIN-koodit?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// Raportin kysely suoraan mallista: jokaisen seinän GTIN.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Jokainen asia, joka koskee annettua rakennusosaa.
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-palvelu `files_information` näyttää tuotujen mallien `IfcProject`-guidin
`ifc_project`-kenttänä, minkä avulla asiakkaat voivat täyttää asian
otsakkeen tiedostot.

## Kyselyt Dataspatiumista

[Dataspatium](https://github.com/marwiss/Dataspatium), tämän palvelimen
kanssa kehitettävä selainasiakas, ajaa Cypheriä tätä graafia vasten
Neo4j-lähteensä kautta Boltilla (WebSocket Bolt-portissa), kun ylläpitäjä
avaa tietokannan, kuten kehityspäällyste tekee osoitteessa `localhost:7697`.
Sen Kontroll-työtila käyttää yllä olevia malleja (mallit, luokat,
komponentit `SAME_AS`-suhteen kautta, uusin valmis malli asiakirjaa kohti);
kyselyt ovat Dataspatiumin dokumentaatiossa (`docs/cad-bim.md`), ja live-ajot
on lueteltu tiedostossa [acceptance.md](../acceptance.md). Tuotantopalvelin
ei julkaise Boltia; hallintarajapinnan graafikysely
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) antaa
järjestelmänvalvojille lukevan Cypherin ilman porttia.

## Rajat ja tila

- Yksi muunnos kerrallaan; suuret mallit jonottavat. Esimerkkimalli (248
  entiteettiä) tuodaan noin sekunnissa; 200 MB:n arkkitehtimalli vie
  minuutteja.
- `IfcModel`-solmu kantaa kentät `state`, `entities`, `relationships`,
  `skipped`, `schema`, `ifc_project_guid`, aikaleimat ja `error`.
  Järjestelmänvalvojat voivat tarkastella sitä Neo4j Browserissa tai
  Memgraph Labissa:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Projektin poisto poistaa sen mallien entiteetit samalla.
