# Sikkerhetskontroller og testene som beviser dem

Hver kontroll har minst én automatisert test. "Suite" navngir testmodulen.

## Foundation API og OAuth2 (etappe 2)

| Kontroll | Standard | Suite |
|---|---|---|
| PKCE `S256` kreves for hver klient; `plain` og manglende challenge avvises | RFC 7636, OAuth 2.1 | `test_security_oauth2::test_pkce_is_mandatory_and_plain_is_refused` |
| Nøyaktig matching av redirect-URI; loopback-porten kan variere; uregistrert URI vises, følges aldri | RFC 9700 §4.1, RFC 8252 §7.3 | `test_security_oauth2::test_unregistered_redirect_uri_is_shown_not_followed`, `::test_loopback_port_may_vary_but_host_may_not` |
| `state` kreves; ukjent scope og ustøttet svartype omdirigeres som feil med `state` | RFC 6749 §4.1.2.1 | `test_security_oauth2::test_state_is_required_and_unknown_scope_is_refused` |
| `iss` i autorisasjonssvaret | RFC 9207 | `test_oauth2::test_public_client_flow_with_pkce` |
| Engangskoder (60 s); replay trekker tilbake tokenene fra den første innløsningen | RFC 9700 §4.5 | `test_oauth2::test_code_is_single_use_and_replay_revokes_tokens` |
| Koden bundet til klient, redirect-URI og verifier | RFC 6749 §4.1.3 | `test_security_oauth2::test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Opake tokens lagret bare som SHA-256-hasher | ADR 0002 | `test_graph_core` (skjema), kodegjennomgang |
| Rotasjon av refresh-tokens med oppdaging av gjenbruk som trekker tilbake familien | RFC 9700 §4.14 | `test_oauth2::test_refresh_rotates_and_reuse_revokes_the_family` |
| Klientautentisering: Basic eller skjema; offentlige klienter viser aldri en hemmelighet; 401 med `WWW-Authenticate` | RFC 6749 §2.3 | `test_security_oauth2::test_client_authentication_failures` |
| Tokensvar `Cache-Control: no-store`, `Pragma: no-cache`, status 201 | RFC 6749 §5.1, Foundation API | `test_oauth2::test_token_response_is_never_cached_and_has_spec_fields` |
| Tilbaketrekking av access-tokens og hele refresh-familier | RFC 7009 | `test_oauth2::test_revocation` |
| Samtykke kan nektes (`access_denied`) | RFC 6749 §4.1.2.1 | `test_oauth2::test_deny_redirects_with_access_denied` |
| Signerte, utløpende, formålsbundne skjematokens; manipulering avvises | CSRF | `test_security_oauth2::test_tampered_or_replayed_form_token_is_refused`, `test_auth_primitives` |
| Innlogging hastighetsbegrenset per adresse | OWASP ASVS 2.2.1 | `test_security_oauth2::test_sign_in_is_rate_limited` |
| Generisk feilmelding; deaktiverte kontoer kan ikke logge inn og mister tokenene sine | OWASP ASVS 2.2 | `test_security_oauth2::test_disabled_user_cannot_sign_in_and_loses_tokens` |
| Passord, koder og tokens opptrer aldri i logger | OWASP ASVS 7.1 | `test_security_oauth2::test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Argon2id-hashing av passord; policy (lengde, zxcvbn, ikke brukernavnet) | OWASP ASVS 2.1 | `test_core_helpers::test_password_policy_and_hashing` |
| Dynamisk registrering av som standard; bare https- eller loopback-omdirigeringer; offentlige klienter (RFC 7591 `token_endpoint_auth_method: "none"`) får ingen hemmelighet og må bruke PKCE som enhver klient; bare kode- og refresh-grantene kan registreres | Foundation API 2.2.3, RFC 7591 | `test_oauth2::test_dynamic_registration_when_enabled`, `::test_registration_is_404_when_disabled` |
| Selvregistrerte klienter som ikke utsteder noe token på `dynamic_client_unused_days`, slettes med tokenene sine (oppryddingen og `opencde client prune`); manuelle klienter utløper aldri | Dataminimering | `test_maintenance::test_unused_self_registered_clients_expire_and_can_be_pruned`, `test_oauth2::test_dynamic_registration_when_enabled` |
| Bare Bearer på API-et; HTTP Basic avvises | Foundation API 2.2.1 | `test_foundation::test_current_user_requires_a_bearer_token` |
| Sider: streng CSP, ingen inline-kode, ingen innramming, ingen caching | OWASP ASVS 14.4 | `test_foundation::test_authorize_without_client_shows_an_error_page_and_never_redirects` |

## BCF API (etappe 3)

| Kontroll | Standard | Suite |
|---|---|---|
| Prosjekter og saker nås fra brukernoden gjennom `MEMBER_OF`; ikke-medlemmer får 404, aldri 403 (ingen eksistenslekkasje) | OWASP API1 (BOLA) | `test_bcf_projects_topics::test_projects_and_extensions`, `::test_topic_authorization_matrix` |
| Rolle × handling-matrise håndheves på serversiden for opprett, oppdater og slett; `authorization`-objektene forteller sannheten | OWASP API5, BCF 1.2 | `test_bcf_projects_topics::test_topic_authorization_matrix`, `::test_project_rename_needs_manager` |
| Saksverdier valideres mot prosjektets extensions; begrensede lengder; ukjente felt ignoreres | Foundation API 1.8, BCF 3.1.4 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| OData: felthvitliste, parametrisert Cypher, begrensede `$top`/`$skip`, 400 ved ukjente felt eller usorterbare kolonner | OWASP API8 (injeksjon) | `test_odata`, `test_bcf_projects_topics::test_topic_odata_filtering_sorting_and_paging` |
| Klientvalgte guid-er må være UUID-er og normaliseres; duplikater gir 409 | Foundation API 1.5.1 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| Hendelsesverdier klippes (titler 128, tekster 1024 tegn) | Dataminimering | `events.py`, `test_topic_lifecycle_with_events` |

## BCF API: kommentarer, viewpoints, filer og dokumenter (etappe 4)

| Kontroll | Standard | Suite |
|---|---|---|
| Snapshot- og bitmapdata må være den deklarerte bildetypen (magic bytes) og under `max_image_bytes`; sjekkes før noe lagres | OWASP ASVS 12.1, 12.2 | `test_bcf_helpers::test_decode_image_rejects`, `test_bcf_comments_viewpoints::test_viewpoint_rules_and_image_checks` |
| Binære opplastinger (dokumenter, snippets) strømmes til lageret under servergenererte nøkler og telles mot `max_upload_bytes`; deklarerte størrelser stoles ikke på | OWASP ASVS 12.1 | `test_bcf_links_documents::test_documents_and_files_information`, `test_core_helpers::test_storage_stream_counts_bytes` |
| Bare de to binære rutene er unntatt fra JSON-kroppsgrensen; chunked-kropper telles når de kommer | OWASP API4 | `test_headers_and_errors::test_chunked_body_over_the_limit_is_cut_off` |
| Nedlastinger er vedlegg med sanerte, RFC 8187-kodede filnavn, `application/octet-stream` for dokumenter, `nosniff`; opplastet innhold gjengis aldri | OWASP ASVS 12.5 | `test_bcf_helpers::test_filename_from_content_disposition`, `test_documents_and_files_information` |
| Klientfilnavn når aldri en sti; lagernøkler er UUID-er | OWASP ASVS 12.3 | `test_bcf_helpers::test_filename_from_content_disposition`, `storage.py` |
| Kommentarer og viewpoints nås gjennom bruker → prosjekt → sak; utenforstående får 404; rollematrise for opprett/oppdater/slett; 409 i stedet for stille datatap ved sletting av et referert viewpoint | OWASP API1, API5 | `test_viewpoint_lifecycle`, `test_comment_lifecycle_and_events` |
| Dokumentreferanser godtar bare http(s)-URL-er og må peke på et dokument i samme prosjekt | OWASP ASVS 5.1 | `test_document_references`, `test_bcf_helpers::test_component_comment_and_reference_rules` |
| Relaterte saker må tilhøre samme prosjekt | OWASP API1 | `test_related_topics_and_files` |
| Numerisk inndata er endelig (ingen NaN eller uendelig), lister og strenger begrenset | OWASP ASVS 5.1 | `test_bcf_helpers::test_viewpoint_rules`, `schemas.py` |

## Documents API og nettleserinnlogging (etappe 5)

| Kontroll | Standard | Suite |
|---|---|---|
| UI-lenker bærer et 256-bits token lagret bare som hash, gyldig i `documents_session_ttl_seconds`; API-sidens URL-er bruker en egen offentlig id og trenger et bearer-token | OWASP ASVS 3.2 | `test_documents_api::test_upload_flow_versions_and_queries` |
| Nettleseren må være innlogget som brukeren som startet flyten; andre brukere får 403, anonyme nettlesere sendes til innlogging | OWASP API1 | `test_documents_api` (opplastings- og utvalgsflyter) |
| Sesjonscookie: tilfeldig, hashet, `HttpOnly`, `SameSite=Strict`, `Secure` over https, inaktivitets- og absolutt utløp, slettet ved utlogging | OWASP ASVS 3.3, 3.4 | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Signerte skjematokens bundet til sesjonen ved hver side-POST; `Sec-Fetch-Site`/`Origin` sjekkes også | CSRF, OWASP ASVS 4.2.2 | `test_web_signin::test_cross_site_posts_are_refused_and_next_cannot_leave_the_site`, `test_documents_api` |
| `next` etter innlogging er bare en lokal sti (ingen åpen omdirigering) | OWASP ASVS 5.1.5 | `test_documents_helpers::test_safe_next_only_accepts_local_paths` |
| Callback-URL-er er bare http(s) og hentes aldri av serveren; nettleseren omdirigeres med URL-kodede parametere | SSRF, OWASP ASVS 12.6 | `test_documents_helpers::test_callback_and_extensions_rules`, `test_upload_cancelled_in_the_browser` |
| Deler strømmes og må matche det annonserte intervallet nøyaktig; filer over `max_upload_bytes` avvises ved instruksjonen; den sammensatte størrelsen verifiseres og hashes | OWASP ASVS 12.1 | `test_upload_flow_versions_and_queries` |
| Opplastinger trenger prosjekthandlingen `createDocument`; nedlastinger trenger medlemskap; utenforstående får 404 | OWASP API1, API5 | `test_upload_cancelled_in_the_browser`, `test_selection_flow_with_filtering_and_browser_upload` |
| Svarkropper inneholder bare spesifikasjonens felt (ingen lagernøkler, ingen hasher) | OWASP API3 | `validate_documents` i hver Documents API-test |
| Utløpte sesjoner og deler ryddes med filene sine | Opprydding | `cleanup.py`, `test_graph_core::test_expired_nodes_are_deleted_in_batches` |

## Admin-UI og kontoside (etappe 6)

| Kontroll | Standard | Suite |
|---|---|---|
| `/admin` trenger en innlogget administrator; andre brukere får en HTML 404, anonyme nettlesere sendes til innlogging | OWASP API5, ASVS 4.1 | `test_admin_ui::test_admin_pages_need_the_admin_role` |
| Hver admin-POST trenger et signert token bundet til administratorens sesjon og objektet, og en same-origin-nettleserforespørsel | CSRF, OWASP ASVS 4.2.2 | `test_admin_ui::test_csrf_protections_on_admin_forms` |
| Tilbakestilling av passord, endring av adminflagget, rotasjon av klienthemmeligheter og sletting trenger administratorens eget passord igjen | OWASP ASVS 2.2.5 | `test_user_management`, `test_project_management_reaches_the_bcf_api`, `test_client_management_and_secret_rotation` |
| Administratorer kan ikke deaktivere, degradere eller slette sin egen konto | Forebygging av utestengelse | `test_user_management` |
| Genererte passord og klienthemmeligheter vises én gang; tilbakestilte passord må byttes ved neste innlogging; deaktivering trekker tilbake tokens | OWASP ASVS 2.1, 2.5 | `test_user_management`, `test_client_management_and_secret_rotation` |
| Hver adminhandling registreres i revisjonsloggen uten hemmeligheter | OWASP ASVS 7.1 | `test_sessions_audit_and_settings_pages` |
| Innstillingssiden viser aldri hemmeligheter | OWASP ASVS 14.3 | `test_sessions_audit_and_settings_pages` |
| Sidene bærer den strenge CSP-en, ingen inline-kode; forbedringsskriptene bygger DOM bare med `textContent` | OWASP ASVS 14.4 | `test_admin_pages_need_the_admin_role`, `tests/ui` (ingen konsollfeil) |
| Tilgjengelighet: ingen alvorlige eller kritiske axe-core-brudd på noen adminside | WCAG 2.2 AA | `tests/ui/test_admin_browser.py` |

## IFC-graf (etappe 9)

| Kontroll | Standard | Suite |
|---|---|---|
| IFC-parsing kjører i en separat arbeidsprosess med tidsgrense, minnegrense (POSIX) og entitetstak; et krasj eller en henging feller modellen, ikke serveren | OWASP ASVS 12.4 | `test_ifcgraph_convert::test_geometry_can_be_included_and_limits_are_enforced`, `test_ifcgraph` |
| `.ifczip` pakkes ut bare når den inneholder nøyaktig én `.ifc`, med opplastingens størrelsestak på de utpakkede bytene | Zip-bombe | `service._prepare_input` |
| Etiketter og relasjonstyper fra konvertereren valideres som identifikatorer før de når Cypher; alt annet er en parameter | OWASP API8 | `importer._safe`, `test_ifcgraph` |
| Konverteringsfeil registreres på `IfcModel`-noden og logges uten filens innhold | OWASP ASVS 7.1 | `test_ifcgraph` |

## Utrulling og sikkerhetskopier (etappe 8)

| Kontroll | Suite |
|---|---|
| Containeren kjører som ikke-root på et skrivebeskyttet rotfilsystem med fjernede capabilities; databasen bare på det private nettet | `Dockerfile`, `compose.prod.yaml`; Trivy-imageskanning i `release.yml` og `security-nightly.yml` |
| Sikkerhetskopiering og gjenoppretting tur-retur beholder noder, relasjoner og filer, på Neo4j og Memgraph | `test_backup` |
| Nattlig ZAP-baseline mot den kjørende serveren | `security-nightly.yml`, `.zap/rules.tsv` |

## Plattform (etappe 0–1, kontraktsfuzzing etappe 11)

| Kontroll | Suite |
|---|---|
| Sikkerhetsheadere på hvert svar, også feil | `test_headers_and_errors` |
| Autorisasjons-, utvalgs- og opplastingssidene legger klientens origin til `form-action`, siden Chromium sjekker den mot omdirigeringen som svarer på skjemaet; alle andre sider beholder `form-action 'self'` | `test_security_oauth2::test_the_authorization_page_lets_the_browser_follow_the_redirect_to_the_client`, `tests/ui/test_popup_opener.py::test_the_sign_in_popup_comes_back_to_the_client` |
| `Cross-Origin-Opener-Policy: same-origin` bare på administrasjons- og kontosidene; sidene en klient åpner i et popup-vindu, beholder nettleserens standard slik at klientens callback-side kan nå sin opener (verifisert i en ekte nettleser) | `test_headers_and_errors::test_opener_policy_isolates_only_the_administration`, `tests/ui/test_popup_opener.py` |
| Bare spesifikasjonens feilkropp; ingen stakkspor eller gjentatt inndata | `test_headers_and_errors`, `errors.py` |
| Størrelsesgrense for forespørselskroppen før parsing | `test_headers_and_errors::test_oversized_body_is_rejected_before_parsing` |
| Request-id saneres | `test_headers_and_errors::test_request_id_is_echoed_or_minted` |
| CORS uten credentials, bare på API-stiene; sider deles aldri cross-origin | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials`, `::test_pages_are_never_shared_cross_origin` |
| CORS tillater og eksponerer `Content-Disposition`, slik at nettleserklienter kan laste opp og ned binærfiler (Foundation API 1.9) | `test_headers_and_errors::test_cors_allows_and_exposes_content_disposition` |
| Uhåndterte feil blir spesifikasjonens 500 innenfor CORS- og sikkerhetsheaderlagene, slik at nettleserklienter ser statusen, ikke en nettverksfeil | `test_headers_and_errors::test_unhandled_errors_keep_cors_and_security_headers` |
| Hastighetsbegrensede endepunkter gir slowapi en Response for headerne dens (med grenser på feilet et endepunkt som returnerte en dict) | `test_rate_limit_endpoints`, `test_bcf_links_documents::test_upload_works_with_rate_limits_enabled` |
| Forespørselslogg (valgfri): metode, sti uten spørrestreng, operasjon, status, tid, request-id, bytetall og kaller; aldri kropper, headere eller tokens; poster utløper; lesbar bare for administratorer (sesjon på siden, bearer med scopet `admin` på `/admin/api/requests`) | `test_requestlog::test_requests_are_logged_without_bodies_and_served_to_administrators` |
| Grafspørring (valgfri): lesende Cypher for administratorer med scopet `admin`; skrivende klausuler og ikke-skjemaprosedyrer avvises før databasen, beskyttede egenskaper avvises og holdes utenfor svarene, hasher maskeres, rad- og tidsgrenser, hvert kall revideres; monteres ikke med mindre den er på | `test_graph_query::test_the_fences_hold`, `test_graph_query (unit)`, `test_capabilities::test_the_graph_query_is_announced_with_its_limits_when_on` |
| Den interaktive API-dokumentasjonen (tredjeparts Swagger UI fra et CDN) har sin egen policy og er av i produksjon som standard | `test_headers_and_errors::test_api_docs_have_their_own_policy_and_are_off_in_production` |
| Produksjon nekter å starte uten https, databasepassord og hemmelig nøkkel | `test_settings` |
| Lagernøkler bygges bare av UUID-er; path traversal umulig | `test_core_helpers::test_storage_keys_cannot_escape` |
| Strømmende skrivinger teller bytes og håndhever grenser | `test_core_helpers::test_storage_stream_counts_bytes` |
| Cypher forblir parametrisert og portabel | `test_core_helpers::test_dialect_ddl_and_cypher_lint`, Memgraph-kontraktskjøring |
| Utløpte hemmeligheter slettes på en timer | `test_graph_core::test_expired_nodes_are_deleted_in_batches` |
| Klokken sammenlignes med NTP i `opencde doctor` og på innstillingssiden (utløpstider avhenger av den) | `test_doctor` |
| Avhengighets-cooldown og festede actions | `.github/workflows/ci.yml`, `pyproject.toml` |
| Hver dokumentert operasjon overlever generert gyldig og ugyldig inndata: ingen 5xx, svarene matcher OpenAPI-skjemaene, ugyldig inndata får en 4xx | `tests/e2e/test_schemathesis.py` (Schemathesis; `OPENCDE_SCHEMATHESIS_EXAMPLES` for den lange nattlige kjøringen) |
