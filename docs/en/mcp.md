# The MCP endpoint (extension)

Through `POST /mcp`, AI programs that speak the Model Context Protocol (Claude,
ChatGPT, VS Code, Cursor and the clients of local models) read the IFC models of
the projects a person is a member of, in that person's name. The AI proposes and
a person approves: no tool approves, publishes, uploads, merges, deletes or
administers anything (ADR 0028). The server runs no AI of its own; the program,
its model and its budget are the client's.

## Turning it on

The endpoint is off until `OPENCDE_MCP_ENABLED=true`. `opencde init --local`
turns it on in the local engine, where `http://127.0.0.1:8000/mcp` answers on
the loopback only. On a team server it goes through the proxy like the API, with
https. While it is on, the capabilities document announces it as `mcp`
([client guide](client-guide.md), §1), and the authorization server lists the
scopes `mcp` and `mcp:propose`.

## A token for the endpoint

The endpoint takes only a token issued for it, and no REST API takes such a
token:

1. Register the program as a client, as any client is registered: itself, where
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` is on (the local engine), or by an
   administrator.
2. The program finds the way in by itself: `401` from `/mcp` names
   `/.well-known/oauth-protected-resource/mcp`, which names the authorization
   server, whose metadata is at `/.well-known/oauth-authorization-server`.
3. It signs the person in with `resource=<public_url>/mcp` and the scope `mcp`
   (reading). `mcp:propose`, for the change sets, is asked for when a tool needs
   it: `403 insufficient_scope` names both scopes. The consent page says what
   they give and that nothing is approved or published through them.

The [client guide](client-guide.md) (§2) has the rules of the binding.

## Connecting an AI program

The program needs the endpoint's address alone; it registers, signs the person
in and finds the scopes by itself, as above.

- The local engine: `http://127.0.0.1:8000/mcp`, for programs on the same
  computer, which reach every project.
- A team server: `https://cde.example.org/mcp` with the server's own name, which reaches only the
  projects whose AI policy is `cloud`. A program that runs in the cloud, such
  as a connector of Claude or ChatGPT, reaches a team server on the internet
  and never the local engine.

As the programs' own guides describe it, Claude Code adds it with a command,
VS Code in `.vscode/mcp.json` and Cursor in `~/.cursor/mcp.json`:

```sh
claude mcp add --transport http dataregium https://cde.example.org/mcp
```

```json
{"servers": {"dataregium": {"type": "http", "url": "https://cde.example.org/mcp"}}}
```

```json
{"mcpServers": {"dataregium": {"url": "https://cde.example.org/mcp"}}}
```

The first call opens the server's sign-in page in the browser; after the
consent the program lists the tools. A good start is `list_models`, then
`server_query` with `name` null for the queries a model answers. To propose,
the program asks for `mcp:propose` at the first change-set tool, and the person
is an editor or a manager of the project. Where the server registers no client
by itself, an administrator registers the program with the redirect URI it
names: `http://127.0.0.1` with any port, and `http://localhost` with any port
for a sign-in to this endpoint alone; the server sends no other sign-in there.

## The protocol

Streamable HTTP with one JSON answer per request and no SSE. Revision
2026-07-28 is stateless: every request carries its revision and the client's
capabilities in `_meta`, and the headers `MCP-Protocol-Version`, `Mcp-Method`
and `Mcp-Name` repeat what the body says. Its methods are `server/discover`,
`tools/list` and `tools/call`; the results carry `resultType`, and the
discovery and the list of tools `ttlMs` (an hour) and `cacheScope` (`private`).
The revisions 2025-11-25, 2025-06-18 and 2025-03-26 get `initialize` and `ping`
too, without a session: the server never makes an `Mcp-Session-Id`, and every
call is answered on its own. A request without `MCP-Protocol-Version` is of
2025-03-26.

```http
POST /mcp HTTP/1.1
Authorization: Bearer <a token bound to the endpoint>
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: list_models

{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
 "params": {"name": "list_models", "arguments": {"project_id": null},
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                      "io.modelcontextprotocol/clientCapabilities": {}}}}
```

| Answer | When |
|---|---|
| `400`, `-32700` or `-32600` | The body is not JSON, is a batch, or is not one JSON-RPC request or notification |
| `400`, `-32602` | `_meta` lacks the revision or the capabilities; an unknown tool; arguments that are not an object |
| `400`, `-32020` | A header does not say what the body says, or is missing or given twice |
| `400`, `-32022` | A revision the endpoint does not answer; `data` names those it does |
| `404`, `-32601` | A method the endpoint does not have |
| `202` | A notification |
| `401`, `403` | No token bound to the endpoint, or a tool's scope missing |
| `403` | An `Origin` that is neither the server's own nor named in `OPENCDE_CORS_ORIGINS`; `null` and `*` do not count |
| `405` | `GET`, `DELETE` and every method but `POST` |
| `413` | A body larger than 1 MB |

The handshake revisions answer the errors of a request with `200`, as their
servers did. `/mcp` has no CORS: no browser needs it.

## The tools

Every argument is required, and `null` means "not given". A refusal (a project
that is not the caller's, the AI policy, arguments the tool does not take) is a
tool result with `isError: true` that the AI can read; the answer is
`structuredContent` and the same JSON as text.

- `list_models` (scope `mcp`): one row per IFC document of the person's projects,
  or of one `project_id`: `project_id`, `project_name`, the person's `role`, the
  project's `ai_policy`, `document_id`, the `title` and `file_name` of the latest
  version, its `version_index`, its `model_state` (`done` when the model can be
  queried, `queued`, `running` or `failed`, `null` without a model) and its IFC
  `schema`. At most 200 rows, and `truncated` when there were more.

```json
{"models": [{"project_id": "…", "project_name": "Building permit", "role": "editor", "ai_policy": "cloud",
             "document_id": "…", "title": "Walls", "file_name": "walls.ifc", "version_index": 2,
             "model_state": "done", "schema": "IFC4"}],
 "truncated": false}
```

- `server_query` (scope `mcp`): the [named queries](ifc-db.md#named-queries)
  of a version's model, by `document_id` and `version_index` (`null` for the
  latest), as the Documents API asks them. `name` is one of the queries in the
  server's catalogue, and each of their parameters is a field of its own
  (`class`, `pset`, `property`, `global_id`, `since`); the tool's description
  lists the queries with their parameters, so a query IFC-DB adds appears when
  the server is updated. `name: null` lists them, with the model's
  `model_state` and `workcopy`. A query answers `name`, `columns`, at most 500
  `rows`, `count` (the rows it found, at most 10,000) and `truncated`; a text in
  a row is cut at 1,000 characters.
- `get_publication` (scope `mcp`): whether a version is published, and if it is
  `published_at`, `published_by`, `file_name`, `size_in_bytes` and `sha256`,
  each `null` while it is not; never where the archive is downloaded.
- `start_clash_check` (scope `mcp`): a [clash check](ifc-db.md#clash-check) of
  two versions of a project: `project_id`, `a` and `b` with `document_id`,
  `version_index` and `types` (IFC classes, `null` for every element with a
  body), `mode` (`intersection` or `clearance`), and `tolerance` and `clearance`
  in metres (`null` for 0.001 and 0.05). It answers `clash_id` and `state`, and
  the audit log records `mcp.clash.started`.
- `get_clash_check` (scope `mcp`): the report of a check, by `project_id` and
  `clash_id`, waiting at most `wait_seconds` (20 at the most) for one that is
  queued or running: its `state`, the request, `count`, `set_a`, `set_b`,
  `missing`, `seconds` and at most 200 `clashes`, with `truncated` when there
  were more. Both clash tools refuse unless `OPENCDE_IFC_DB_CLASH_ENABLED=true`.
  The three are listed only while the IFC-DB module is on. A user has at most
  two checks waiting or running, in all their projects together; a third is
  refused, and the audit log records `mcp.denied` with the reason `limit`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## The change sets

While the IFC-DB module is on (`OPENCDE_IFC_DB_ENABLED`), which tries the
change sets, the list also holds the tools that propose changes to a model, in
Dataspatium's order. They need the scope `mcp:propose`, the role `editor` or
`manager` in the project, checked at every call as the REST API checks it, and
the project's AI policy; a refused role is `mcp.denied` with the reason `role`.
No tool approves: a person does, in Dataspatium.

- `open_changeset` (`document_id`, `version_index`, `null` for the latest):
  opens a change set on a version of an IFC document and answers its
  `changeset_id`, its `base`, `expires_at` and `max_steps` (200).
- The write tools `create_storeys_and_grid`, `define_type`, `create_wall`,
  `create_slab`, `create_roof`, `create_opening`, `create_element`,
  `create_spaces`, `set_properties`, `set_classification`, `assign`,
  `edit_element`, `transform_elements`, `delete_elements` (with `confirm: true`)
  and `set_site`: Dataspatium's own, with its schemas unchanged and `changeset_id`
  first. A call is one operation of the change set's `ops` in the form
  `dataspatium-tools/1`, exactly as the app makes it (the defaults filled in, the
  numbers checked, the texts cut at 200 characters, an optional field only when it
  is given), or the app's error, which the AI mends. A type, wall, slab, roof,
  opening or building element gets a ref, `new-1`, `new-2` …, and so does each
  room that `create_spaces` lists; an element or a type is named by its GlobalId,
  its STEP id or a ref. The descriptions leave out the app's read tools
  `search_ifc_class` and `get_parameters`, which this endpoint does not offer, and
  `set_properties` answers the guidance's advice on the name of a set of the
  model's own as `note`.
- `manage_changeset` (`action`: `list`, `remove_last` or `clear`): the steps with
  their tools, refs and descriptions; the last step removed, with its refs; or
  none left.
- `change_attribute` (`guid` or `step_id`, `path`, `attribute`, `op` `set`, `add`
  or `remove`, `index`, `old`, `new`, `copy`): one attribute of one instance of the
  base, a post in the change set's `changes` in the form of its schema; `old` is
  checked when the change set is tried.
- `propose_changes` (`title`; `description`, `null` for the steps' own lines;
  `ai_model`, what the AI says it is): a BCF topic in the project with the change
  set as its snippet, whose trial the server queues. Its provenance names the
  user, the stated `ai_model` and `tool_call` `mcp:` with the steps' tools. Called
  again with the same handle, it puts the change set as it is then on the same
  topic and tries it again. Answers `project_id`, `topic_guid`, `state`
  (`queued`) and how many `ops` and `changes` the change set holds.
- `get_proposal` (`project_id`, `topic_guid`, `wait_seconds` up to 20; scope
  `mcp`): the trial as `GET …/ifc-proposal` gives it, waiting while it is
  `queued` or `running`, with at most 50 findings, `created` (the GlobalId of what
  the operations made, by its ref) and `notes`.
- `list_proposals` (`document_id`, `limit` up to 50; scope `mcp`): the proposals
  against a document, newest first, as `GET …/ifc-proposals` lists them, with the
  `project_id` and without the addresses.

The flow:

1. `list_models` gives the document and its latest version.
2. `open_changeset` gives the handle, and the write tools and `change_attribute`
   fill the change set step by step; a step that went wrong is mended with
   `manage_changeset` `remove_last` and a new step.
3. `propose_changes` makes the proposal, and `get_proposal` answers `clean`,
   `issues` with the findings, or `failed`. With findings the AI mends the change
   set and proposes it again.
4. At `clean` the AI tells the person, who approves it in Dataspatium: a manager
   of the project, or the responsible of the one team whose part it touches.

```json
{"ok": true, "step": 1, "ref": "new-1",
 "description": "new-1 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high"}
```

The open change set is a draft on the server, the user's own. Its handle is a
name, not a permission: every call checks that the draft is the caller's and in
one of the caller's projects. It closes 24 hours after its last use, and the
server deletes it; an unknown or closed handle is a tool error that asks for a
new one. A user has at most 10 open, and a change set at most 200 steps.

## The AI policy

A project's `ai_policy` is `local`, the default, or `cloud`, set by its manager
or an administrator. The local engine serves every project, since the computer
is the boundary. Any other server lists `local` projects not at all, and asked
for one, by its id or by one of its documents, a tool refuses and the audit log
records `mcp.denied`. The server keeps where the data goes; which model reads it
is the client's choice, and another program on the same computer can still send
the answers to a model in the cloud.

## Limits and logs

- A body is at most 1 MB, and an answer at most 256 kB, with at most 500 rows of
  a query and 200 clashes; names and titles are cut at 200 characters, and a
  text in a query's rows at 1,000. `get_clash_check` waits at most 20 seconds.
- A user makes at most 120 tool calls a minute, whatever the token, beside the limit per address
  that all programs share (`OPENCDE_RATE_LIMIT_API`); past it the tool answers
  `isError` with the seconds to wait.
- The request log keeps the method and the tool's name, never the body. The
  audit log keeps `mcp.denied` with the reason (`policy`, `role`, `scope` or `limit`) and
  `mcp.clash.started` with the project, the check and its two versions, each
  with the tool and the client, never an argument or a text from the projects.
- The audit log keeps `mcp.changeset.opened` and `mcp.changeset.proposed` too,
  with the project, the document, the base, the change set, the topic, the
  numbers of operations and changes and the stated AI model, cut at 100
  characters; never a title, a description or a step.

## Data, never instructions

Everything a tool returns is data from the projects: a name, a title or a text
from IFC, BCF or a document comes back as it is, in a named field, whatever it
says. The tool descriptions and the server's `instructions` are fixed texts that
say so. A person approves a proposal in Dataspatium, signed in there; a token
for the endpoint never reaches an approval or a publication.
