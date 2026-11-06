# opencde-client

A small Python client for buildingSMART OpenCDE servers: Foundation API 1.0
(discovery, OAuth2 authorization code with PKCE), BCF API 3.0 and 2.1, and
Documents API 1.0. It depends on `httpx` only and returns the specification's
JSON objects as dictionaries. LGPL-3.0-or-later.

```python
from opencde_client import OpenCdeClient

with OpenCdeClient("https://cde.example", client_id="my-app") as cde:
    cde.login()  # opens the browser, loopback redirect, PKCE S256
    me = cde.foundation.current_user()
    project = cde.bcf.projects()[0]
    topic = cde.bcf.create_topic(project["project_id"], {"title": "Door D-204 lacks a closer"})
    for event in cde.bcf.topic_events(project["project_id"], topic["guid"]):
        print(event["date"], [a["type"] for a in event["actions"]])
```

It speaks BCF API 3.0 unless told otherwise. `bcf_version="2.1"` speaks 2.1, and
`bcf_version="auto"` takes the newest the server offers, also on a server that has
2.1 alone and no Foundation API. The methods are the same, and what goes in and
out is what the version in use says: in 2.1 a file has `file_name` and not `filename`,
the extensions have `user_id_type` and not `users`, a comment can have a
`reply_to_comment_guid`, and a camera has no `aspect_ratio`. A topic has no
`server_assigned_id`. There is no `files_information` or `delete_viewpoint`, which
raise `NotInThisVersion`. `cde.current_user()` finds the user in either version.

Documents API flows are link-driven and involve the user's browser:

```python
started = cde.documents.start_upload(
    [{"file_name": "walls.ifc", "session_file_id": "f1"}], callback_url="http://127.0.0.1:8765/cb"
)
# open started["upload_ui_url"] in the browser; your callback receives ?upload_documents_url=...
plan = cde.documents.upload_instructions(upload_documents_url, {"f1": len(data)})
version = cde.documents.upload_file(plan["documents_to_upload"][0], data)
latest, etag = cde.documents.query_versions([version["document_id"]])
```

Command line: `python -m opencde_client --server https://cde.example --client-id my-app login`,
then `projects` or `topics PROJECT_ID`. Tokens are stored in a file only you can read.

`opencde_client.testing` drives a Kontroll server's pages headlessly for
automated tests; real applications never handle a user's password.
