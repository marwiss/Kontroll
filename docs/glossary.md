# Glossary

The words this documentation uses, with what they mean here. Topic, comment,
viewpoint and project are the same words as in Dataspatium.

## Standards

| Word | What it means here |
|---|---|
| OpenCDE | buildingSMART's APIs for a common data environment: Foundation, BCF and Documents |
| CDE | Common data environment: the shared place for a project's information |
| Foundation API | The part of OpenCDE that says which APIs a server offers, how to sign in and who you are |
| BCF | BIM Collaboration Format, for issues about a building model. BCF API 3.0 is its web API |
| Documents API | The part of OpenCDE that uploads and selects documents through pages in the browser |
| IFC | Industry Foundation Classes, the open file format for building models |

## In a project

| Word | What it means here |
|---|---|
| Project | The shared space: its members, topics and documents |
| Member, role | Someone in a project, as viewer, contributor, editor or manager. The role decides what they may do |
| Administrator | A user who manages users, projects and clients. It is not a role in a project and gives no access to a project's content |
| Extensions | The values a project allows for type, status, priority, labels and so on |
| Topic | An issue: something to do, check or answer. The BCF word for it |
| Comment | A remark on a topic, which can point at a viewpoint |
| Viewpoint | A saved view of the model: camera, components and an image |
| Component | A building part a viewpoint names, by its `GlobalId` |
| Snapshot | The image of a viewpoint |
| Event | An entry in the history of a topic or comment |
| Document, version | A file with a title; a new upload of it is a new version |

## Signing in

| Word | What it means here |
|---|---|
| Client | A program that works on a user's behalf, registered on the server |
| Public client | A client that cannot keep a secret, such as a browser or desktop app |
| Confidential client | A client on a server of its own, which can keep a secret |
| Self-registration | A client registering itself, off by default |
| Redirect URI | The address the server sends the browser back to after the sign-in |
| PKCE | A one-time proof that whoever exchanges the code is whoever asked for it |
| Access token | A short-lived proof sent with every request to the APIs |
| Refresh token | A longer-lived proof that gets a new access token, good for one use |
| Scope | What a token may be used for: `profile`, `bcf`, `documents` or `admin` |

## The model as a graph

| Word | What it means here |
|---|---|
| IFC graph | An uploaded model as nodes and relationships in the database, optional |
| `GlobalId` | The permanent id of an element in an IFC file |
| `SAME_AS` | The relationship from a viewpoint's component to the element in a model |
| GTIN | Global Trade Item Number, a product's number; here read from the property set `Reuse` |
| Cypher | The query language of the graph database |
| Bolt | The database's own connection, optional for those who query the graph directly |

## Running the server

| Word | What it means here |
|---|---|
| Stack | The containers that make up a running server: the API, the database and, in production, the proxy and the backup |
| Seed | `opencde seed`, which loads demonstration data into an empty database |
| Capabilities | `/.well-known/kontroll`, which says what this server has switched on |
| Request log | An optional record of the requests the server has answered |
| Audit log | The record of who signed in and changed what |
