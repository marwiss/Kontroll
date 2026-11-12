# BCF-viewpoint-flödet

Hur en klient lägger upp ett ärende med en vy av modellen, och hur någon annan öppnar
samma vy. Detta är BCF API 3.0, avsnitten 3.2 (ärenden) och 3.5 (viewpoints). Exemplet
[create_topic.py](../../examples/create_topic.py) gör första halvan med
klientbiblioteket.

```mermaid
sequenceDiagram
    autonumber
    participant A as Rapportörens klient
    participant S as Server
    participant G as Grafdatabas
    participant F as Fillagring
    participant B as Läsarens klient

    A->>S: POST /bcf/3.0/projects/{id}/topics (titel, typ, status)
    S->>G: Kontrollera rollen genom MEMBER_OF, skapa Topic
    S-->>A: 201 ärende med guid och server_assigned_id
    A->>S: POST …/topics/{guid}/viewpoints (kamera, komponenter, bild)
    S->>F: Spara bilden under ett namn som servern väljer
    S->>G: Skapa Viewpoint och dess Component
    S->>G: Kopiera GTIN från de färdiga modellerna till komponenterna, om IFC-grafen är på
    S-->>A: 201 viewpoint med guid
    A->>S: POST …/topics/{guid}/comments (comment, viewpoint_guid)
    S-->>A: 201 kommentar
    B->>S: GET …/topics/{guid}/viewpoints
    S-->>B: 200 viewpoints med sina kameror
    B->>S: GET …/viewpoints/{guid}/snapshot
    S->>F: Läs bilden
    S-->>B: 200 bild
    B->>S: GET …/viewpoints/{guid}/selection, coloring, visibility
    S-->>B: 200 komponenter
```

En viewpoint går inte att ändra. Den skapas hel och tas bort hel, så att en kommentar
som pekar på den fortsätter att peka på samma sak.

## Vad en viewpoint innehåller

| Del | Vad den säger | Var en klient läser den |
|---|---|---|
| Kamera | Position, riktning och uppåtvektor, perspektiv eller ortogonal | I viewpointen |
| Linjer och snittplan | Vad som ritas i vyn och vad som skärs bort | I viewpointen |
| Markering | Komponenterna som är markerade | `/selection` |
| Färgläggning | Komponenterna som har en färg | `/coloring` |
| Synlighet | Vad som syns från början, och undantagen | `/visibility` |
| Ögonblicksbild | En bild av vyn, PNG eller JPEG | `/snapshot` |
| Bitmappar | Bilder placerade i vyn | `/bitmaps/{id}` |

## Vem får göra vad

| Åtgärd | Kräver |
|---|---|
| Läsa ärenden, kommentarer och viewpoints | Medlemskap i projektet, i vilken roll som helst |
| Skapa ett ärende | Åtgärden `createTopic`: contributor, editor eller manager |
| Lägga till en viewpoint eller en kommentar | Åtgärden `createViewpoint` eller `createComment`: contributor, editor eller manager |
| Lägga till ett dokument i projektet och hänvisa till det från ett ärende | Åtgärden `createDocument`: contributor, editor eller manager; en contributor hänvisar från sina egna ärenden |
| Ta bort en viewpoint | Dess författare som contributor; editor och manager tar bort vilken som helst |

Ett projekt som användaren inte är medlem i finns inte för hen (404).

## Från en viewpoint till modellen

När [IFC-LPG](../ifc-lpg.md) är på får varje komponent som nämner ett `GlobalId`
som projektets färdiga modeller har elementets GTIN som `gtin`, också när modellen
laddas upp efteråt; själva elementet hittas genom sitt `GlobalId`:

```cypher
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)
MATCH (e:IfcProduct {GlobalId: c.ifc_guid})
RETURN c.ifc_guid, e.Name, c.gtin
```
