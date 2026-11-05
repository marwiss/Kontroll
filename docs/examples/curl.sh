#!/usr/bin/env sh
# This file was generated with the assistance of an AI coding tool.
# The OpenCDE APIs with curl. Discovery needs no token; everything else a bearer token
# obtained through the browser flow (docs/examples/login_pkce.py prints one, or use the
# client CLI: python -m opencde_client --server "$SERVER" --client-id "$CLIENT_ID" login).
#
#   SERVER=https://cde.example TOKEN=... PROJECT=... sh docs/examples/curl.sh
set -eu

: "${SERVER:?set SERVER to the server's base URL}"

echo "# Foundation API: which APIs and versions does the server offer?"
curl -sS "$SERVER/foundation/versions"
echo
echo "# Foundation API: how do I sign in?"
curl -sS "$SERVER/foundation/1.0/auth"
echo

[ -n "${TOKEN:-}" ] || { echo "set TOKEN to continue with authenticated calls"; exit 0; }
AUTH="Authorization: Bearer $TOKEN"

echo "# Who am I?"
curl -sS -H "$AUTH" "$SERVER/foundation/1.0/current-user"
echo
echo "# My projects, with what I may do in them"
curl -sS -H "$AUTH" "$SERVER/bcf/3.0/projects?includeAuthorization=true"
echo

[ -n "${PROJECT:-}" ] || { echo "set PROJECT to a project_id to continue"; exit 0; }

echo "# Allowed values for topics in the project"
curl -sS -H "$AUTH" "$SERVER/bcf/3.0/projects/$PROJECT/extensions"
echo
echo "# Create a topic"
TOPIC=$(curl -sS -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title": "Created with curl", "topic_status": "Open"}' "$SERVER/bcf/3.0/projects/$PROJECT/topics")
echo "$TOPIC"
GUID=$(printf '%s' "$TOPIC" | sed -n 's/.*"guid": *"\([^"]*\)".*/\1/p')
echo
echo "# Open topics, newest first (OData)"
curl -sS -H "$AUTH" "$SERVER/bcf/3.0/projects/$PROJECT/topics?\$filter=topic_status%20eq%20'Open'&\$orderby=creation_date%20desc&\$top=5"
echo
echo "# The topic's events"
curl -sS -H "$AUTH" "$SERVER/bcf/3.0/projects/$PROJECT/topics/$GUID/events"
echo
echo "# Conditional GET: the second request answers 304 Not Modified"
ETAG=$(curl -sSI -H "$AUTH" "$SERVER/bcf/3.0/projects/$PROJECT" | tr -d '\r' | sed -n 's/^etag: *//Ip')
curl -sS -o /dev/null -w '%{http_code}\n' -H "$AUTH" -H "If-None-Match: $ETAG" "$SERVER/bcf/3.0/projects/$PROJECT"
echo "# Upload a BCF project document (binary body, file name in Content-Disposition)"
printf 'hello' > /tmp/opencde-hello.txt
curl -sS -H "$AUTH" -H "Content-Type: application/octet-stream" \
  -H 'Content-Disposition: attachment; filename="hello.txt"' \
  --data-binary @/tmp/opencde-hello.txt "$SERVER/bcf/3.0/projects/$PROJECT/documents"
echo
