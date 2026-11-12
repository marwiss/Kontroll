# Documents API flows

The Documents API 1.0 is a conversation between three parties: the client
application, this server, and the user's browser. The client talks to the API
with a bearer token; the browser shows the server's own pages (sign-in,
metadata entry, document selection); the server never calls the client, it
only redirects the browser to the client's callback URL.

## Upload

```mermaid
sequenceDiagram
    participant C as Client (bearer token)
    participant S as Server
    participant B as Browser
    C->>S: POST /documents/1.0/upload-documents {callback, files}
    S-->>C: {upload_ui_url, expires_in, max_size_in_bytes}
    C->>B: open upload_ui_url
    B->>S: GET /documents/1.0/upload-ui/{token}
    S-->>B: sign-in page if needed, then the metadata form
    B->>S: POST form (title, version, project, form token)
    S-->>B: 302 callback?upload_documents_url=… (or user_cancelled_upload=true)
    B->>C: callback
    C->>S: POST /upload-sessions/{id}/instructions {files: [{session_file_id, size_in_bytes}]}
    S-->>C: {documents_to_upload: [{upload_file_parts, upload_completion, upload_cancellation}]}
    loop every part
        C->>S: PUT /upload-part/{part_id} (bytes of the range)
    end
    C->>S: POST /upload-sessions/{id}/files/{n}/complete
    S-->>C: DocumentVersion
```

* The UI link is valid for `OPENCDE_DOCUMENTS_SESSION_TTL_SECONDS` (10 minutes);
  once instructions are issued the session lives `OPENCDE_UPLOAD_SESSION_TTL_SECONDS`
  (24 hours) so large files can be uploaded.
* Parts are `OPENCDE_UPLOAD_PART_BYTES` (50 MiB) each, uploaded in any order,
  concurrently if the client likes. A part must be exactly the announced range.
* Completion assembles the parts, verifies the total size, computes the
  SHA-256 and creates the version. If this takes more than 15 seconds the
  response starts with whitespace to keep the connection open.
* `document_id` in a file entry makes the upload a new version of that
  document; the title is kept, the version index increases.
* `base_version_index` in a file entry (an extension) says which version the
  upload builds on: the completion answers `412 version_conflict` when the
  document already has a newer one, and the version's metadata records the base.
* A project may refuse files with validation errors: the completion then
  answers `422 ifc_validation_failed` with the report's address, and
  `POST …/projects/{id}/ifc-precheck` checks a file without storing it.
* A confidential client an administrator has approved for it (*May upload
  documents without the browser page* on the client's page) uploads headless:
  `project_id` in the request, with `title` and `version_number` per file,
  skips the page, and the instructions are at `upload-sessions/{id}/instructions`
  at once; every such upload is in the audit log. 403 for any other client.

## Selection and download

```mermaid
sequenceDiagram
    participant C as Client (bearer token)
    participant S as Server
    participant B as Browser
    C->>S: POST /documents/1.0/select-documents {callback, supported_file_extensions}
    S-->>C: {select_documents_url, expires_in}
    C->>B: open select_documents_url
    B->>S: GET /documents/1.0/select-ui/{token}
    S-->>B: sign-in page if needed, then the document list
    B->>S: POST form (selected document ids, form token)
    S-->>B: 302 callback?selected_documents_url=… (or user_cancelled_selection=true)
    B->>C: callback
    C->>S: GET /selection-sessions/{id}/documents
    S-->>C: {server_context, documents: [DocumentVersion]}
    C->>S: GET links.document_version_download
    S-->>C: the file (attachment)
```

* The list shows the latest version of every document in the user's
  projects, filtered on the client's extensions with a "show all" link.
* Editors and managers can upload a file from the page; it appears in the
  list at once (this is an addition to the specification).
* `POST /documents/1.0/document-versions` answers the latest versions of a
  list of document ids with an `ETag`; `If-None-Match` gives `304`.

[Dataspatium](https://github.com/marwiss/Dataspatium) implements both flows
from the browser (`src/api/families/opencde.js`): it opens the server's
selection page in a popup and imports the chosen files, and uploads datasets,
files and workspace bundles in parts with the server's upload page for the
metadata; its live suites run these flows against the development stack.

## Who may do what

| Action | Needs |
|---|---|
| Start an upload or a selection | a bearer token with the `documents` scope |
| Use the browser pages | a browser session as the same user (`/signin`) |
| Save metadata, complete an upload, upload from the page | the role editor or manager |
| See, select and download documents | membership of the project (any role) |
| Publish a version | the `manager` role |

Documents of other projects do not exist for the caller (404), so neither
their ids nor their existence leaks.
