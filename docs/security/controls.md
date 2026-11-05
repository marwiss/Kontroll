# Security controls and the tests that prove them

Every control has at least one automated test. "Suite" names the test module.

## Foundation API and OAuth2 (stage 2)

| Control | Standard | Suite |
|---|---|---|
| PKCE `S256` required for every client; `plain` and missing challenge refused | RFC 7636, OAuth 2.1 | `test_security_oauth2::test_pkce_is_mandatory_and_plain_is_refused` |
| Redirect URI exact match; loopback port may vary; unregistered URI shown, never followed | RFC 9700 §4.1, RFC 8252 §7.3 | `test_security_oauth2::test_unregistered_redirect_uri_is_shown_not_followed`, `::test_loopback_port_may_vary_but_host_may_not` |
| `state` required; unknown scope and unsupported response type redirected as errors with `state` | RFC 6749 §4.1.2.1 | `test_security_oauth2::test_state_is_required_and_unknown_scope_is_refused` |
| `iss` in the authorization response | RFC 9207 | `test_oauth2::test_public_client_flow_with_pkce` |
| One-time codes (60 s); replay revokes the tokens of the first redemption | RFC 9700 §4.5 | `test_oauth2::test_code_is_single_use_and_replay_revokes_tokens` |
| Code bound to client, redirect URI and verifier | RFC 6749 §4.1.3 | `test_security_oauth2::test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Opaque tokens stored only as SHA-256 hashes | ADR 0002 | `test_graph_core` (schema), code review |
| Refresh token rotation with reuse detection revoking the family | RFC 9700 §4.14 | `test_oauth2::test_refresh_rotates_and_reuse_revokes_the_family` |
| Client authentication: Basic or form; public clients never present a secret; 401 with `WWW-Authenticate` | RFC 6749 §2.3 | `test_security_oauth2::test_client_authentication_failures` |
| Token responses `Cache-Control: no-store`, `Pragma: no-cache`, status 201 | RFC 6749 §5.1, Foundation API | `test_oauth2::test_token_response_is_never_cached_and_has_spec_fields` |
| Revocation of access tokens and whole refresh families | RFC 7009 | `test_oauth2::test_revocation` |
| Consent can be denied (`access_denied`) | RFC 6749 §4.1.2.1 | `test_oauth2::test_deny_redirects_with_access_denied` |
| Signed, expiring, purpose-bound form tokens; tampering refused | CSRF | `test_security_oauth2::test_tampered_or_replayed_form_token_is_refused`, `test_auth_primitives` |
| Sign-in rate limited per address | OWASP ASVS 2.2.1 | `test_security_oauth2::test_sign_in_is_rate_limited` |
| Generic failure message; disabled accounts cannot sign in and lose tokens | OWASP ASVS 2.2 | `test_security_oauth2::test_disabled_user_cannot_sign_in_and_loses_tokens` |
| Passwords, codes and tokens never appear in logs | OWASP ASVS 7.1 | `test_security_oauth2::test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Argon2id password hashing; policy (length, zxcvbn, no user name) | OWASP ASVS 2.1 | `test_core_helpers::test_password_policy_and_hashing` |
| Dynamic registration off by default; https or loopback redirects only | Foundation API 2.2.3 | `test_oauth2::test_dynamic_registration_when_enabled`, `::test_registration_is_404_when_disabled` |
| Bearer only on the API; HTTP Basic refused | Foundation API 2.2.1 | `test_foundation::test_current_user_requires_a_bearer_token` |
| Pages: strict CSP, no inline code, no framing, no caching | OWASP ASVS 14.4 | `test_foundation::test_authorize_without_client_shows_an_error_page_and_never_redirects` |

## BCF API (stage 3)

| Control | Standard | Suite |
|---|---|---|
| Projects and topics are reached from the user node through `MEMBER_OF`; non-members get 404, never 403 (no existence leak) | OWASP API1 (BOLA) | `test_bcf_projects_topics::test_projects_and_extensions`, `::test_topic_authorization_matrix` |
| Role × action matrix enforced server-side for create, update and delete; `authorization` objects tell the truth | OWASP API5, BCF 1.2 | `test_bcf_projects_topics::test_topic_authorization_matrix`, `::test_project_rename_needs_manager` |
| Topic values validated against the project's extensions; bounded lengths; unknown fields ignored | Foundation API 1.8, BCF 3.1.4 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| OData: field whitelist, parameterised Cypher, bounded `$top`/`$skip`, 400 on unknown fields or unsortable columns | OWASP API8 (injection) | `test_odata`, `test_bcf_projects_topics::test_topic_odata_filtering_sorting_and_paging` |
| Client-chosen guids must be UUIDs and are normalised; duplicates give 409 | Foundation API 1.5.1 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| Event values clipped (titles 128, texts 1024 characters) | Data minimisation | `events.py`, `test_topic_lifecycle_with_events` |

## BCF API: comments, viewpoints, files and documents (stage 4)

| Control | Standard | Suite |
|---|---|---|
| Snapshot and bitmap data must be the declared image type (magic bytes) and under `max_image_bytes`; checked before anything is stored | OWASP ASVS 12.1, 12.2 | `test_bcf_helpers::test_decode_image_rejects`, `test_bcf_comments_viewpoints::test_viewpoint_rules_and_image_checks` |
| Binary uploads (documents, snippets) stream into storage under server-made keys and are counted against `max_upload_bytes`; declared sizes are not trusted | OWASP ASVS 12.1 | `test_bcf_links_documents::test_documents_and_files_information`, `test_core_helpers::test_storage_stream_counts_bytes` |
| Only the two binary routes are exempt from the JSON body limit; chunked bodies are counted as they arrive | OWASP API4 | `test_headers_and_errors::test_chunked_body_over_the_limit_is_cut_off` |
| Downloads are attachments with sanitised, RFC 8187 encoded file names, `application/octet-stream` for documents, `nosniff`; uploaded content is never rendered | OWASP ASVS 12.5 | `test_bcf_helpers::test_filename_from_content_disposition`, `test_documents_and_files_information` |
| Client file names never reach a path; storage keys are UUIDs | OWASP ASVS 12.3 | `test_bcf_helpers::test_filename_from_content_disposition`, `storage.py` |
| Comments and viewpoints are reached through user → project → topic; outsiders get 404; role matrix for create/update/delete; 409 instead of silent data loss when deleting a referenced viewpoint | OWASP API1, API5 | `test_viewpoint_lifecycle`, `test_comment_lifecycle_and_events` |
| Document references accept http(s) URLs only and must point at a document of the same project | OWASP ASVS 5.1 | `test_document_references`, `test_bcf_helpers::test_component_comment_and_reference_rules` |
| Related topics must belong to the same project | OWASP API1 | `test_related_topics_and_files` |
| Numeric inputs are finite (no NaN or infinity), lists and strings bounded | OWASP ASVS 5.1 | `test_bcf_helpers::test_viewpoint_rules`, `schemas.py` |

## Documents API and browser sign-in (stage 5)

| Control | Standard | Suite |
|---|---|---|
| UI links carry a 256-bit token stored only as a hash, valid for `documents_session_ttl_seconds`; API-side URLs use a separate public id and need a bearer token | OWASP ASVS 3.2 | `test_documents_api::test_upload_flow_versions_and_queries` |
| The browser must be signed in as the user who started the flow; other users get 403, anonymous browsers are sent to sign in | OWASP API1 | `test_documents_api` (upload and selection flows) |
| Session cookie: random, hashed, `HttpOnly`, `SameSite=Strict`, `Secure` on https, idle and absolute expiry, deleted on sign-out | OWASP ASVS 3.3, 3.4 | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Signed form tokens bound to the session on every page POST; `Sec-Fetch-Site`/`Origin` checked as well | CSRF, OWASP ASVS 4.2.2 | `test_web_signin::test_cross_site_posts_are_refused_and_next_cannot_leave_the_site`, `test_documents_api` |
| `next` after sign-in is a local path only (no open redirect) | OWASP ASVS 5.1.5 | `test_documents_helpers::test_safe_next_only_accepts_local_paths` |
| Callback URLs are http(s) only and never fetched by the server; the browser is redirected with URL-encoded parameters | SSRF, OWASP ASVS 12.6 | `test_documents_helpers::test_callback_and_extensions_rules`, `test_upload_cancelled_in_the_browser` |
| Parts are streamed and must match the announced range exactly; files above `max_upload_bytes` are refused at instruction time; assembled size is verified and hashed | OWASP ASVS 12.1 | `test_upload_flow_versions_and_queries` |
| Uploads need the `createDocument` project action; downloads need membership; outsiders get 404 | OWASP API1, API5 | `test_upload_cancelled_in_the_browser`, `test_selection_flow_with_filtering_and_browser_upload` |
| Response bodies contain only the specification's fields (no storage keys, no hashes) | OWASP API3 | `validate_documents` in every Documents API test |
| Expired sessions and parts are swept with their files | Housekeeping | `cleanup.py`, `test_graph_core::test_expired_nodes_are_deleted_in_batches` |

## Admin UI and account page (stage 6)

| Control | Standard | Suite |
|---|---|---|
| `/admin` needs a signed-in administrator; other users get an HTML 404, anonymous browsers are sent to sign in | OWASP API5, ASVS 4.1 | `test_admin_ui::test_admin_pages_need_the_admin_role` |
| Every admin POST needs a signed token bound to the admin's session and the object, and a same-origin browser request | CSRF, OWASP ASVS 4.2.2 | `test_admin_ui::test_csrf_protections_on_admin_forms` |
| Resetting passwords, changing the admin flag, rotating client secrets and deleting need the admin's own password again | OWASP ASVS 2.2.5 | `test_user_management`, `test_project_management_reaches_the_bcf_api`, `test_client_management_and_secret_rotation` |
| Administrators cannot disable, demote or delete their own account | Lock-out prevention | `test_user_management` |
| Generated passwords and client secrets are shown once; reset passwords must be changed at the next sign-in; disabling revokes tokens | OWASP ASVS 2.1, 2.5 | `test_user_management`, `test_client_management_and_secret_rotation` |
| Every admin action is recorded in the audit log without secrets | OWASP ASVS 7.1 | `test_sessions_audit_and_settings_pages` |
| The settings page never shows secrets | OWASP ASVS 14.3 | `test_sessions_audit_and_settings_pages` |
| Pages carry the strict CSP, no inline code; the enhancement scripts build DOM with `textContent` only | OWASP ASVS 14.4 | `test_admin_pages_need_the_admin_role`, `tests/ui` (no console errors) |
| Accessibility: no serious or critical axe-core violations on any admin page | WCAG 2.2 AA | `tests/ui/test_admin_browser.py` |

## IFC-graph (stage 9)

| Control | Standard | Suite |
|---|---|---|
| IFC parsing runs in a separate worker process with a time limit, a memory limit (POSIX) and an entity cap; a crash or hang fails the model, not the server | OWASP ASVS 12.4 | `test_ifcgraph_convert::test_geometry_can_be_included_and_limits_are_enforced`, `test_ifcgraph` |
| `.ifczip` is unpacked only when it holds exactly one `.ifc`, with the upload size cap on the unpacked bytes | Zip bomb | `service._prepare_input` |
| Labels and relationship types from the converter are validated as identifiers before they reach Cypher; everything else is a parameter | OWASP API8 | `importer._safe`, `test_ifcgraph` |
| Conversion failures are recorded on the `IfcModel` node and logged without the file's content | OWASP ASVS 7.1 | `test_ifcgraph` |

## Deployment and backups (stage 8)

| Control | Suite |
|---|---|
| Container runs as non-root on a read-only root file system with dropped capabilities; database on the private network only | `Dockerfile`, `compose.prod.yaml`; Trivy image scan in `release.yml` and `security-nightly.yml` |
| Backup and restore round trip keeps nodes, relationships and files, on Neo4j and Memgraph | `test_backup` |
| Nightly ZAP baseline against the running server | `security-nightly.yml`, `.zap/rules.tsv` |

## Platform (stage 0–1, contract fuzzing stage 11)

| Control | Suite |
|---|---|
| Security headers on every response, including errors | `test_headers_and_errors` |
| Spec error body only; no stack traces or echoed input | `test_headers_and_errors`, `errors.py` |
| Request body size limit before parsing | `test_headers_and_errors::test_oversized_body_is_rejected_before_parsing` |
| Request id sanitised | `test_headers_and_errors::test_request_id_is_echoed_or_minted` |
| CORS without credentials, on the API paths only; pages are never shared cross-origin | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials`, `::test_pages_are_never_shared_cross_origin` |
| The interactive API documentation (third-party Swagger UI from a CDN) has a policy of its own and is off in production by default | `test_headers_and_errors::test_api_docs_have_their_own_policy_and_are_off_in_production` |
| Production refuses to start without https, database password and secret key | `test_settings` |
| Storage keys built from UUIDs only; path traversal impossible | `test_core_helpers::test_storage_keys_cannot_escape` |
| Streaming writes count bytes and enforce limits | `test_core_helpers::test_storage_stream_counts_bytes` |
| Cypher stays parameterised and portable | `test_core_helpers::test_dialect_ddl_and_cypher_lint`, Memgraph contract run |
| Expired secrets are deleted on a timer | `test_graph_core::test_expired_nodes_are_deleted_in_batches` |
| The clock is compared with NTP in `opencde doctor` and on the settings page (expiry times depend on it) | `test_doctor` |
| Dependency cooldown and pinned actions | `.github/workflows/ci.yml`, `pyproject.toml` |
| Every documented operation survives generated valid and invalid input: no 5xx, responses match the OpenAPI schemas, invalid input gets a 4xx | `tests/e2e/test_schemathesis.py` (Schemathesis; `OPENCDE_SCHEMATHESIS_EXAMPLES` for the long nightly run) |
