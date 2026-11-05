# This file was generated with the assistance of an AI coding tool.
"""Upload a file through the Documents API, then download it again and compare checksums.

    uv run python docs/examples/upload_document.py https://cde.example my-client-id model.ifc

The Documents API hands part of the flow to the browser: the server's page
asks for a title, a version number and the project. This script runs a tiny
loopback web server as the client's callback, opens the browser on the
server's page and waits to be called back with ``upload_documents_url``.
"""

import hashlib
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from opencde_client import OpenCdeClient


class Callback(HTTPServer):
    """Receives the browser once the user has finished on the server's page."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.params: dict[str, str] = {}
        self.done = threading.Event()
        self.url = f"http://127.0.0.1:{self.server_address[1]}/callback"
        threading.Thread(target=self.serve_forever, daemon=True).start()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        server: Callback = self.server  # type: ignore[assignment]
        server.params = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Thanks, you can close this window.")
        server.done.set()

    def log_message(self, *args: object) -> None:
        return


def main(server: str, client_id: str, path: Path) -> None:
    data = path.read_bytes()
    with OpenCdeClient(server, client_id=client_id) as cde:
        cde.login()
        callback = Callback()
        started = cde.documents.start_upload(
            [{"file_name": path.name, "session_file_id": "file-1"}], callback_url=callback.url
        )
        print(f"finish the upload in the browser (max {started['max_size_in_bytes']} bytes)…")
        webbrowser.open(started["upload_ui_url"])
        callback.done.wait(timeout=started["expires_in"])
        callback.shutdown()
        if "upload_documents_url" not in callback.params:
            sys.exit("the upload was cancelled in the browser")

        plan = cde.documents.upload_instructions(callback.params["upload_documents_url"], {"file-1": len(data)})
        instructions = plan["documents_to_upload"][0]
        print(f"uploading {len(instructions['upload_file_parts'])} part(s)")
        version = cde.documents.upload_file(instructions, data)
        print(f"document {version['document_id']} version {version['version_number']} ({version['title']})")

        downloaded = cde.documents.download(version)
        same = hashlib.sha256(downloaded).hexdigest() == hashlib.sha256(data).hexdigest()
        print("round trip ok" if same else "CHECKSUM MISMATCH")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
