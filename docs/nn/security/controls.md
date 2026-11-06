# Tryggingskontrollar og testane som beviser dei

Kvar kontroll har minst éin automatisert test. "Suite" namngjev testmodulen.

## Foundation API og OAuth2 (etappe 2)

| Kontroll | Standard | Suite |
|---|---|---|
| PKCE `S256` krevst for kvar klient; `plain` og manglande challenge blir avviste | RFC 7636, OAuth 2.1 | `test_security_oauth2::test_pkce_is_mandatory_and_plain_is_refused` |
| Nøyaktig matching av redirect-URI; loopback-porten kan variere; uregistrert URI blir vist, aldri følgd | RFC 9700 §4.1, RFC 8252 §7.3 | `test_security_oauth2::test_unregistered_redirect_uri_is_shown_not_followed`, `::test_loopback_port_may_vary_but_host_may_not` |
| `state` krevst; ukjent scope og ustøtta svartype blir omdirigerte som feil med `state` | RFC 6749 §4.1.2.1 | `test_security_oauth2::test_state_is_required_and_unknown_scope_is_refused` |
| `iss` i autorisasjonssvaret | RFC 9207 | `test_oauth2::test_public_client_flow_with_pkce` |
| Eingongskodar (60 s); replay trekkjer tilbake tokena frå den første innløysinga | RFC 9700 §4.5 | `test_oauth2::test_code_is_single_use_and_replay_revokes_tokens` |
| Koden bunden til klient, redirect-URI og verifier | RFC 6749 §4.1.3 | `test_security_oauth2::test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Opake tokens lagra berre som SHA-256-hashar | ADR 0002 | `test_graph_core` (skjema), kodegjennomgang |
| Rotasjon av refresh-tokens med oppdaging av gjenbruk som trekkjer tilbake familien | RFC 9700 §4.14 | `test_oauth2::test_refresh_rotates_and_reuse_revokes_the_family` |
| Klientautentisering: Basic eller skjema; offentlege klientar viser aldri ein løyndom; 401 med `WWW-Authenticate` | RFC 6749 §2.3 | `test_security_oauth2::test_client_authentication_failures` |
| Tokensvar `Cache-Control: no-store`, `Pragma: no-cache`, status 201 | RFC 6749 §5.1, Foundation API | `test_oauth2::test_token_response_is_never_cached_and_has_spec_fields` |
| Tilbaketrekking av access-tokens og heile refresh-familiar | RFC 7009 | `test_oauth2::test_revocation` |
| Samtykke kan nektast (`access_denied`) | RFC 6749 §4.1.2.1 | `test_oauth2::test_deny_redirects_with_access_denied` |
| Signerte, utgåande, formålsbundne skjematokens; manipulering blir avvist | CSRF | `test_security_oauth2::test_tampered_or_replayed_form_token_is_refused`, `test_auth_primitives` |
| Innlogging takstavgrensa per adresse | OWASP ASVS 2.2.1 | `test_security_oauth2::test_sign_in_is_rate_limited` |
| Mislukka innloggingar får eit brukarnamn til å vente: etter fem på rad ei ventetid som blir dobla frå 30 sekund opp til 15 minutt, i tillegg til grensa per adresse. Ukjende namn tel på same måte, så svaret seier ingenting om kva kontoar som finst, og namn blir lagra som hashverdiar | OWASP ASVS 6.3 | `test_sign_in_throttle` |
| Generisk feilmelding; deaktiverte kontoar kan ikkje logge inn og mistar tokena sine | OWASP ASVS 2.2 | `test_security_oauth2::test_disabled_user_cannot_sign_in_and_loses_tokens` |
| Passord, kodar og tokens opptrer aldri i loggar | OWASP ASVS 7.1 | `test_security_oauth2::test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Argon2id-hashing av passord; policy (lengd, zxcvbn, ikkje brukarnamnet) | OWASP ASVS 2.1 | `test_core_helpers::test_password_policy_and_hashing` |
| Dynamisk registrering av som standard; berre https- eller loopback-omdirigeringar; offentlege klientar (RFC 7591 `token_endpoint_auth_method: "none"`) får ingen løyndom og må bruke PKCE som kvar klient; berre kode- og refresh-grantane kan registrerast | Foundation API 2.2.3, RFC 7591 | `test_oauth2::test_dynamic_registration_when_enabled`, `::test_registration_is_404_when_disabled` |
| Sjølvregistrerte klientar som ikkje utferdar noko token på `dynamic_client_unused_days`, blir sletta med tokena sine (oppryddinga og `opencde client prune`); manuelle klientar går aldri ut | Dataminimering | `test_maintenance::test_unused_self_registered_clients_expire_and_can_be_pruned`, `test_oauth2::test_dynamic_registration_when_enabled` |
| Berre Bearer på API-et; HTTP Basic blir avvist | Foundation API 2.2.1 | `test_foundation::test_current_user_requires_a_bearer_token` |
| Sider: streng CSP, ingen inline-kode, ingen innramming, ingen caching | OWASP ASVS 14.4 | `test_foundation::test_authorize_without_client_shows_an_error_page_and_never_redirects` |

## BCF API (etappe 3)

| Kontroll | Standard | Suite |
|---|---|---|
| Prosjekt og saker blir nådde frå brukarnoden gjennom `MEMBER_OF`; ikkje-medlemer får 404, aldri 403 (ingen eksistenslekkasje) | OWASP API1 (BOLA) | `test_bcf_projects_topics::test_projects_and_extensions`, `::test_topic_authorization_matrix` |
| Rolle × handling-matrise blir handheva på serversida for opprett, oppdater og slett; `authorization`-objekta fortel sanninga | OWASP API5, BCF 1.2 | `test_bcf_projects_topics::test_topic_authorization_matrix`, `::test_project_rename_needs_manager` |
| Saksverdiar blir validerte mot extensions til prosjektet; avgrensa lengder; ukjende felt blir ignorerte | Foundation API 1.8, BCF 3.1.4 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| OData: feltkvitliste, parametrisert Cypher, avgrensa `$top`/`$skip`, 400 ved ukjende felt eller usorterbare kolonnar | OWASP API8 (injeksjon) | `test_odata`, `test_bcf_projects_topics::test_topic_odata_filtering_sorting_and_paging` |
| Klientvalde guid-ar må vere UUID-ar og blir normaliserte; duplikat gjev 409 | Foundation API 1.5.1 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| Hendingsverdiar blir klipte (titlar 128, tekstar 1024 teikn) | Dataminimering | `events.py`, `test_topic_lifecycle_with_events` |

## BCF API: kommentarar, viewpoints, filer og dokument (etappe 4)

| Kontroll | Standard | Suite |
|---|---|---|
| Snapshot- og bitmapdata må vere den deklarerte biletetypen (magic bytes) og under `max_image_bytes`; blir sjekka før noko blir lagra | OWASP ASVS 12.1, 12.2 | `test_bcf_helpers::test_decode_image_rejects`, `test_bcf_comments_viewpoints::test_viewpoint_rules_and_image_checks` |
| Binære opplastingar (dokument, snippets) blir strøymde til lageret under servergenererte nøklar og telde mot `max_upload_bytes`; deklarerte storleikar blir ikkje stolte på | OWASP ASVS 12.1 | `test_bcf_links_documents::test_documents_and_files_information`, `test_core_helpers::test_storage_stream_counts_bytes` |
| Berre dei to binære rutene er unnatekne frå JSON-kroppsgrensa; chunked-kroppar blir telde når dei kjem | OWASP API4 | `test_headers_and_errors::test_chunked_body_over_the_limit_is_cut_off` |
| Nedlastingar er vedlegg med sanerte, RFC 8187-koda filnamn, `application/octet-stream` for dokument, `nosniff`; opplasta innhald blir aldri teikna | OWASP ASVS 12.5 | `test_bcf_helpers::test_filename_from_content_disposition`, `test_documents_and_files_information` |
| Klientfilnamn når aldri ein sti; lagernøklar er UUID-ar | OWASP ASVS 12.3 | `test_bcf_helpers::test_filename_from_content_disposition`, `storage.py` |
| Kommentarar og viewpoints blir nådde gjennom brukar → prosjekt → sak; utanforståande får 404; rollematrise for opprett/oppdater/slett; 409 i staden for stilt datatap ved sletting av eit referert viewpoint | OWASP API1, API5 | `test_viewpoint_lifecycle`, `test_comment_lifecycle_and_events` |
| Dokumentreferansar godtek berre http(s)-URL-ar og må peike på eit dokument i same prosjekt | OWASP ASVS 5.1 | `test_document_references`, `test_bcf_helpers::test_component_comment_and_reference_rules` |
| Relaterte saker må høyre til same prosjekt | OWASP API1 | `test_related_topics_and_files` |
| Numerisk inndata er endeleg (ingen NaN eller uendeleg), lister og strengar avgrensa | OWASP ASVS 5.1 | `test_bcf_helpers::test_viewpoint_rules`, `schemas.py` |

## Documents API og nettlesarinnlogging (etappe 5)

| Kontroll | Standard | Suite |
|---|---|---|
| UI-lenkjer ber eit 256-bits token lagra berre som hash, gyldig i `documents_session_ttl_seconds`; URL-ane på API-sida brukar ein eigen offentleg id og treng eit bearer-token | OWASP ASVS 3.2 | `test_documents_api::test_upload_flow_versions_and_queries` |
| Nettlesaren må vere innlogga som brukaren som starta flyten; andre brukarar får 403, anonyme nettlesarar blir sende til innlogging | OWASP API1 | `test_documents_api` (opplastings- og utvalsflytar) |
| Sesjonscookie: tilfeldig, hasha, `HttpOnly`, `SameSite=Strict`, `Secure` over https, inaktivitets- og absolutt utgang, sletta ved utlogging | OWASP ASVS 3.3, 3.4 | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Signerte skjematokens bundne til sesjonen ved kvar side-POST; `Sec-Fetch-Site`/`Origin` blir òg sjekka | CSRF, OWASP ASVS 4.2.2 | `test_web_signin::test_cross_site_posts_are_refused_and_next_cannot_leave_the_site`, `test_documents_api` |
| `next` etter innlogging er berre ein lokal sti (ingen open omdirigering) | OWASP ASVS 5.1.5 | `test_documents_helpers::test_safe_next_only_accepts_local_paths` |
| Callback-URL-ar er berre http(s) og blir aldri henta av serveren; nettlesaren blir omdirigert med URL-koda parametrar | SSRF, OWASP ASVS 12.6 | `test_documents_helpers::test_callback_and_extensions_rules`, `test_upload_cancelled_in_the_browser` |
| Delar blir strøymde og må matche det annonserte intervallet nøyaktig; filer over `max_upload_bytes` blir avviste ved instruksjonen; den samansette storleiken blir verifisert og hasha | OWASP ASVS 12.1 | `test_upload_flow_versions_and_queries` |
| Opplastingar treng prosjekthandlinga `createDocument`; nedlastingar treng medlemskap; utanforståande får 404 | OWASP API1, API5 | `test_upload_cancelled_in_the_browser`, `test_selection_flow_with_filtering_and_browser_upload` |
| Svarkroppar inneheld berre felta i spesifikasjonen (ingen lagernøklar, ingen hashar) | OWASP API3 | `validate_documents` i kvar Documents API-test |
| Utgåtte sesjonar og delar blir rydda med filene sine | Opprydding | `cleanup.py`, `test_graph_core::test_expired_nodes_are_deleted_in_batches` |

## Admin-UI og kontoside (etappe 6)

| Kontroll | Standard | Suite |
|---|---|---|
| `/admin` treng ein innlogga administrator; andre brukarar får ein HTML 404, anonyme nettlesarar blir sende til innlogging | OWASP API5, ASVS 4.1 | `test_admin_ui::test_admin_pages_need_the_admin_role` |
| Kvar admin-POST treng eit signert token bunde til sesjonen til administratoren og objektet, og ein same-origin-førespurnad frå nettlesaren | CSRF, OWASP ASVS 4.2.2 | `test_admin_ui::test_csrf_protections_on_admin_forms` |
| Tilbakestilling av passord, endring av adminflagget, rotasjon av klientløyndomar og sletting treng administratoren sitt eige passord igjen | OWASP ASVS 2.2.5 | `test_user_management`, `test_project_management_reaches_the_bcf_api`, `test_client_management_and_secret_rotation` |
| Administratorar kan ikkje deaktivere, degradere eller slette sin eigen konto | Førebygging av utestenging | `test_user_management` |
| Genererte passord og klientløyndomar blir viste éin gong; tilbakestilte passord må bytast ved neste innlogging; deaktivering trekkjer tilbake tokens | OWASP ASVS 2.1, 2.5 | `test_user_management`, `test_client_management_and_secret_rotation` |
| Kvar adminhandling blir registrert i revisjonsloggen utan løyndomar | OWASP ASVS 7.1 | `test_sessions_audit_and_settings_pages` |
| Innstillingssida viser aldri løyndomar | OWASP ASVS 14.3 | `test_sessions_audit_and_settings_pages` |
| Sidene ber den strenge CSP-en, ingen inline-kode; forbetringsskripta byggjer DOM berre med `textContent` | OWASP ASVS 14.4 | `test_admin_pages_need_the_admin_role`, `tests/ui` (ingen konsollfeil) |
| Tilgjenge: ingen alvorlege eller kritiske axe-core-brot på nokon adminside | WCAG 2.2 AA | `tests/ui/test_admin_browser.py` |

## IFC-graf (etappe 9)

| Kontroll | Standard | Suite |
|---|---|---|
| IFC-parsing køyrer i ein separat arbeidsprosess med tidsgrense, minnegrense (POSIX) og entitetstak; eit krasj eller ei henging feller modellen, ikkje serveren | OWASP ASVS 12.4 | `test_ifcgraph_convert::test_geometry_can_be_included_and_limits_are_enforced`, `test_ifcgraph` |
| `.ifczip` blir pakka ut berre når ho inneheld nøyaktig éi `.ifc`, med storleikstaket for opplastinga på dei utpakka bytane | Zip-bombe | `service._prepare_input` |
| Etikettar og relasjonstypar frå konverteraren blir validerte som identifikatorar før dei når Cypher; alt anna er ein parameter | OWASP API8 | `importer._safe`, `test_ifcgraph` |
| Konverteringsfeil blir registrerte på `IfcModel`-noden og logga utan innhaldet i fila | OWASP ASVS 7.1 | `test_ifcgraph` |

## Utrulling og tryggingskopiar (etappe 8)

| Kontroll | Suite |
|---|---|
| Containeren køyrer som ikkje-root på eit skriveverna rotfilsystem med fjerna capabilities; databasen berre på det private nettet | `Dockerfile`, `compose.prod.yaml`; Trivy-imageskanning i `release.yml` og `security-nightly.yml` |
| Tryggingskopiering og gjenoppretting tur-retur held på nodar, relasjonar og filer, på Neo4j og Memgraph | `test_backup` |
| Nattleg ZAP-baseline mot den køyrande serveren | `security-nightly.yml`, `.zap/rules.tsv` |

## Plattform (etappe 0–1, kontraktsfuzzing etappe 11)

| Kontroll | Suite |
|---|---|
| Tryggingsheaderar på kvart svar, òg feil | `test_headers_and_errors` |
| Autorisasjons-, utvals- og opplastingssidene legg origin til klienten til `form-action`, sidan Chromium sjekkar han mot omdirigeringa som svarar på skjemaet; alle andre sider held på `form-action 'self'` | `test_security_oauth2::test_the_authorization_page_lets_the_browser_follow_the_redirect_to_the_client`, `tests/ui/test_popup_opener.py::test_the_sign_in_popup_comes_back_to_the_client` |
| `Cross-Origin-Opener-Policy: same-origin` berre på administrasjons- og kontosidene; sidene ein klient opnar i eit popup-vindauge, held på standarden i nettlesaren slik at callback-sida til klienten kan nå openeren sin (verifisert i ein ekte nettlesar) | `test_headers_and_errors::test_opener_policy_isolates_only_the_administration`, `tests/ui/test_popup_opener.py` |
| Sidene fjernar ein service worker som ein annan app har lagt att på adressa til serveren, og lastar på nytt éin gong, fordi han elles svarar med gamle kopiar av sidene; ein worker som ikkje dekkjer sida, får stå. Dette rettar eit uhell og vernar ikkje mot noko: ein fiendtleg worker kan skrive om sida som ber skriptet | `test_foreign_workers` |
| Språkcookien inneheld berre ein kode frå den faste lista på sju og er `HttpOnly` og `SameSite=Lax`; ingen skript les han | `test_headers_and_errors::test_the_language_cookie_holds_only_a_known_language` |
| Berre feilkroppen frå spesifikasjonen; ingen stakkspor eller attgjeven inndata | `test_headers_and_errors`, `errors.py` |
| Storleiksgrense for førespurnadskroppen før parsing | `test_headers_and_errors::test_oversized_body_is_rejected_before_parsing` |
| Request-id blir sanert | `test_headers_and_errors::test_request_id_is_echoed_or_minted` |
| CORS utan credentials, berre på API-stiane; sider blir aldri delte cross-origin | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials`, `::test_pages_are_never_shared_cross_origin` |
| CORS tillèt og eksponerer `Content-Disposition`, slik at nettlesarklientar kan laste opp og ned binærfiler (Foundation API 1.9) | `test_headers_and_errors::test_cors_allows_and_exposes_content_disposition` |
| Uhandterte feil blir 500 frå spesifikasjonen innanfor CORS- og tryggingsheaderlaga, slik at nettlesarklientar ser statusen, ikkje ein nettverksfeil | `test_headers_and_errors::test_unhandled_errors_keep_cors_and_security_headers` |
| Takstavgrensa endepunkt gjev slowapi ein Response for headerane sine (med grenser på feila eit endepunkt som returnerte ein dict) | `test_rate_limit_endpoints`, `test_bcf_links_documents::test_upload_works_with_rate_limits_enabled` |
| Førespurnadslogg (valfri): metode, sti utan spørjestreng, operasjon, status, tid, request-id, bytetal og kallar; aldri kroppar, headerar eller tokens; postar går ut; lesbar berre for administratorar (sesjon på sida, bearer med scopet `admin` på `/admin/api/requests`) | `test_requestlog::test_requests_are_logged_without_bodies_and_served_to_administrators` |
| Grafspørjing (valfri): lesande Cypher for administratorar med scopet `admin`; skrivande klausular og ikkje-skjemaprosedyrar blir avviste før databasen, verna eigenskapar blir avviste og haldne utanfor svara, hashar maskerte, rad- og tidsgrenser, kvart kall revidert; blir ikkje montert om ho ikkje er på | `test_graph_query::test_the_fences_hold`, `test_graph_query (unit)`, `test_capabilities::test_the_graph_query_is_announced_with_its_limits_when_on` |
| Den interaktive API-dokumentasjonen (tredjeparts Swagger UI frå eit CDN) har sin eigen policy og er av i produksjon som standard | `test_headers_and_errors::test_api_docs_have_their_own_policy_and_are_off_in_production` |
| Produksjon nektar å starte utan https, databasepassord og løynd nøkkel | `test_settings` |
| Lagernøklar blir bygde berre av UUID-ar; path traversal umogleg | `test_core_helpers::test_storage_keys_cannot_escape` |
| Strøymande skrivingar tel bytes og handhevar grenser | `test_core_helpers::test_storage_stream_counts_bytes` |
| Cypher held fram parametrisert og portabel | `test_core_helpers::test_dialect_ddl_and_cypher_lint`, Memgraph-kontraktskøyring |
| Utgåtte løyndomar blir sletta på ein timer | `test_graph_core::test_expired_nodes_are_deleted_in_batches` |
| Klokka blir samanlikna med NTP i `opencde doctor` og på innstillingssida (utgangstider er avhengige av henne) | `test_doctor` |
| Avhengnads-cooldown og festa actions | `.github/workflows/ci.yml`, `pyproject.toml` |
| Kvar dokumentert operasjon overlever generert gyldig og ugyldig inndata: ingen 5xx, svara matchar OpenAPI-skjemaa, ugyldig inndata får ein 4xx | `tests/e2e/test_schemathesis.py` (Schemathesis; `OPENCDE_SCHEMATHESIS_EXAMPLES` for den lange nattlege køyringa) |
