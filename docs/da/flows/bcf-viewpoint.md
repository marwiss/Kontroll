# BCF-viewpoint-forløbet

Hvordan en klient opretter en sag med en visning af modellen, og hvordan en anden åbner
den samme visning. Dette er BCF API 3.0, afsnit 3.2 (sager) og 3.5 (viewpoints).
Eksemplet [create_topic.py](../../examples/create_topic.py) gør første halvdel med
klientbiblioteket.

```mermaid
sequenceDiagram
    autonumber
    participant A as Rapportørens klient
    participant S as Server
    participant G as Grafdatabase
    participant F as Fillager
    participant B as Læserens klient

    A->>S: POST /bcf/3.0/projects/{id}/topics (titel, type, status)
    S->>G: Tjek rollen gennem MEMBER_OF, opret Topic
    S-->>A: 201 sag med guid og server_assigned_id
    A->>S: POST …/topics/{guid}/viewpoints (kamera, komponenter, billede)
    S->>F: Gem billedet under et navn, serveren vælger
    S->>G: Opret Viewpoint og dets Component
    S->>G: Link komponenter til færdige modeller med SAME_AS, hvis IFC-grafen er slået til
    S-->>A: 201 viewpoint med guid
    A->>S: POST …/topics/{guid}/comments (comment, viewpoint_guid)
    S-->>A: 201 kommentar
    B->>S: GET …/topics/{guid}/viewpoints
    S-->>B: 200 viewpoints med deres kameraer
    B->>S: GET …/viewpoints/{guid}/snapshot
    S->>F: Læs billedet
    S-->>B: 200 billede
    B->>S: GET …/viewpoints/{guid}/selection, coloring, visibility
    S-->>B: 200 komponenter
```

Et viewpoint kan ikke ændres. Det oprettes helt og slettes helt, så en kommentar, der
peger på det, fortsat peger på det samme.

## Hvad et viewpoint indeholder

| Del | Hvad den siger | Hvor en klient læser den |
|---|---|---|
| Kamera | Position, retning og opadvektor, perspektiv eller ortogonal | I viewpointet |
| Linjer og snitplaner | Hvad der tegnes i visningen, og hvad der skæres væk | I viewpointet |
| Markering | Komponenterne, der er markeret | `/selection` |
| Farvelægning | Komponenterne, der har en farve | `/coloring` |
| Synlighed | Hvad der er synligt fra start, og undtagelserne | `/visibility` |
| Øjebliksbillede | Et billede af visningen, PNG eller JPEG | `/snapshot` |
| Bitmaps | Billeder placeret i visningen | `/bitmaps/{id}` |

## Hvem må hvad

| Handling | Kræver |
|---|---|
| Læse sager, kommentarer og viewpoints | Medlemskab af projektet, i en hvilken som helst rolle |
| Oprette en sag | Handlingen `createTopic`: contributor, editor eller manager |
| Tilføje et viewpoint eller en kommentar | Handlingen `createViewpoint` eller `createComment`: contributor, editor eller manager |
| Slette et viewpoint | Dets forfatter som contributor; editor og manager sletter et hvilket som helst |

Et projekt, brugeren ikke er medlem af, findes ikke for vedkommende (404).

## Fra et viewpoint til modellen

Når [IFC-LPG](../ifc-lpg.md) er slået til, får hver komponent, der nævner et
`GlobalId`, en `SAME_AS`-relation til det element i projektets færdige modeller, også
når modellen uploades bagefter.

```cypher
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```
