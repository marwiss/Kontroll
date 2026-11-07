# BCF-näkymän kulku

Miten asiakas luo asian, jossa on näkymä malliin, ja miten joku toinen avaa saman
näkymän. Tämä on BCF API 3.0, osat 3.2 (asiat) ja 3.5 (näkymät). Esimerkki
[create_topic.py](../../examples/create_topic.py) tekee ensimmäisen puoliskon
asiakaskirjastolla.

```mermaid
sequenceDiagram
    autonumber
    participant A as Raportoijan asiakas
    participant S as Palvelin
    participant G as Graafitietokanta
    participant F as Tiedostotallennus
    participant B as Lukijan asiakas

    A->>S: POST /bcf/3.0/projects/{id}/topics (otsikko, tyyppi, tila)
    S->>G: Tarkista rooli reunan MEMBER_OF kautta, luo Topic
    S-->>A: 201 asia, jossa guid ja server_assigned_id
    A->>S: POST …/topics/{guid}/viewpoints (kamera, komponentit, kuva)
    S->>F: Tallenna kuva palvelimen valitsemalla nimellä
    S->>G: Luo Viewpoint ja sen Component-solmut
    S->>G: Linkitä komponentit valmiisiin malleihin suhteella SAME_AS, jos IFC-graafi on käytössä
    S-->>A: 201 näkymä, jossa guid
    A->>S: POST …/topics/{guid}/comments (comment, viewpoint_guid)
    S-->>A: 201 kommentti
    B->>S: GET …/topics/{guid}/viewpoints
    S-->>B: 200 näkymät kameroineen
    B->>S: GET …/viewpoints/{guid}/snapshot
    S->>F: Lue kuva
    S-->>B: 200 kuva
    B->>S: GET …/viewpoints/{guid}/selection, coloring, visibility
    S-->>B: 200 komponentit
```

Näkymää ei voi muuttaa. Se luodaan kokonaisena ja poistetaan kokonaisena, joten siihen
osoittava kommentti osoittaa yhä samaan asiaan.

## Mitä näkymä sisältää

| Osa | Mitä se kertoo | Mistä asiakas sen lukee |
|---|---|---|
| Kamera | Sijainti, suunta ja ylösvektori, perspektiivi tai ortogonaalinen | Näkymästä |
| Viivat ja leikkaustasot | Mitä näkymään piirretään ja mitä leikataan pois | Näkymästä |
| Valinta | Valitut komponentit | `/selection` |
| Väritys | Komponentit, joilla on väri | `/coloring` |
| Näkyvyys | Mikä näkyy oletuksena, ja poikkeukset | `/visibility` |
| Tilannekuva | Kuva näkymästä, PNG tai JPEG | `/snapshot` |
| Bittikartat | Näkymään sijoitetut kuvat | `/bitmaps/{id}` |

## Kuka saa tehdä mitä

| Toiminto | Vaatii |
|---|---|
| Lukea asioita, kommentteja ja näkymiä | Jäsenyyden projektissa, missä tahansa roolissa |
| Luoda asian | Toiminnon `createTopic`: contributor, editor tai manager |
| Lisätä näkymän tai kommentin | Toiminnon `createViewpoint` tai `createComment`: contributor, editor tai manager |
| Poistaa näkymän | Sen tekijä roolissa contributor; editor ja manager poistavat minkä tahansa |

Projekti, jonka jäsen käyttäjä ei ole, ei ole hänelle olemassa (404).

## Näkymästä malliin

Kun [IFC-LPG](../ifc-lpg.md) on käytössä, jokainen komponentti, joka nimeää
`GlobalId`-tunnuksen, saa `SAME_AS`-suhteen kyseiseen elementtiin projektin valmiissa
malleissa, myös kun malli ladataan jälkeenpäin.

```cypher
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```
