# Sikkerhedskontroller og de tests, der beviser dem

Hver kontrol har mindst én automatiseret test. "Suite" navngiver testmodulet.

## Foundation API og OAuth2 (etape 2)

| Kontrol | Standard | Suite |
|---|---|---|
| PKCE `S256` kræves for hver klient undtagen en markeret (næste række); `plain` og manglende challenge afvises | RFC 7636, OAuth 2.1 | `test_security_oauth2::test_pkce_is_mandatory_and_plain_is_refused` |
| En fortrolig klient, som en administrator har markeret, må udelade PKCE, som BCF API 2.1 gør: en challenge, den alligevel sender, håndhæves, en verifier uden challenge afvises, en offentlig klient kan ikke markeres, og en redirect-URI, der angives i forespørgslen, skal angives igen | RFC 9700 §2.1.1, RFC 6749 §4.1.3 | `test_oauth2_without_pkce` |
| Nøjagtig matchning af redirect-URI; loopback-porten må variere; uregistreret URI vises, følges aldrig | RFC 9700 §4.1, RFC 8252 §7.3 | `test_security_oauth2::test_unregistered_redirect_uri_is_shown_not_followed`, `::test_loopback_port_may_vary_but_host_may_not` |
| `state` kræves; ukendt scope og ikke-understøttet svartype omdirigeres som fejl med `state` | RFC 6749 §4.1.2.1 | `test_security_oauth2::test_state_is_required_and_unknown_scope_is_refused` |
| `iss` i autorisationssvaret | RFC 9207 | `test_oauth2::test_public_client_flow_with_pkce` |
| Engangskoder (60 s); replay tilbagekalder tokens fra den første indløsning | RFC 9700 §4.5 | `test_oauth2::test_code_is_single_use_and_replay_revokes_tokens` |
| Koden bundet til klient, redirect-URI og verifier | RFC 6749 §4.1.3 | `test_security_oauth2::test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Opake tokens gemt kun som SHA-256-hashes | ADR 0002 | `test_graph_core` (skema), kodegennemgang |
| Rotation af refresh-tokens med registrering af genbrug, der tilbagekalder familien | RFC 9700 §4.14 | `test_oauth2::test_refresh_rotates_and_reuse_revokes_the_family` |
| Et refresh-token, der ikke er brugt i to uger (`refresh_token_idle_seconds`), holder op med at virke og tager sin familie med sig, inden for den absolutte levetid på 30 dage | RFC 9700 §4.14 | `test_oauth2::test_a_refresh_token_left_unused_stops_working` |
| Klientautentificering: Basic eller formular; offentlige klienter fremviser aldrig en hemmelighed; 401 med `WWW-Authenticate` | RFC 6749 §2.3 | `test_security_oauth2::test_client_authentication_failures` |
| Tokensvar `Cache-Control: no-store`, `Pragma: no-cache`, status 201 | RFC 6749 §5.1, Foundation API | `test_oauth2::test_token_response_is_never_cached_and_has_spec_fields` |
| Tilbagekaldelse af access-tokens og hele refresh-familier | RFC 7009 | `test_oauth2::test_revocation` |
| Samtykke kan nægtes (`access_denied`) | RFC 6749 §4.1.2.1 | `test_oauth2::test_deny_redirects_with_access_denied` |
| Signerede, udløbende, formålsbundne formulartokens; manipulation afvises | CSRF | `test_security_oauth2::test_tampered_or_replayed_form_token_is_refused`, `test_auth_primitives` |
| Login hastighedsbegrænset per adresse | OWASP ASVS 2.2.1 | `test_security_oauth2::test_sign_in_is_rate_limited` |
| Mislykkede logins får et brugernavn til at vente: efter fem i træk en ventetid, der fordobles fra 30 sekunder op til 15 minutter, ud over grænsen per adresse. Ukendte navne tæller på samme måde, så svaret siger intet om, hvilke konti der findes, og navne gemmes som hashværdier | OWASP ASVS 6.3 | `test_sign_in_throttle` |
| En grænse per adresse på hver forespørgsel (600 i minuttet, `OPENCDE_RATE_LIMIT_API`), snævrere på administrationen (240 i minuttet); sundhedstjek og statiske filer er undtaget; et delt lager, der fejler, stopper intet | OWASP API4 | `test_rate_limits` |
| Generisk fejlbesked; deaktiverede konti kan ikke logge ind og mister deres tokens | OWASP ASVS 2.2 | `test_security_oauth2::test_disabled_user_cannot_sign_in_and_loses_tokens` |
| Kodeord, koder og tokens optræder aldrig i logs | OWASP ASVS 7.1 | `test_security_oauth2::test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Argon2id-hashing af kodeord; politik (længde, zxcvbn, ikke brugernavnet) | OWASP ASVS 2.1 | `test_core_helpers::test_password_policy_and_hashing` |
| Dynamisk registrering slået fra som standard; kun https- eller loopback-omdirigeringer; offentlige klienter (RFC 7591 `token_endpoint_auth_method: "none"`) får ingen hemmelighed og skal bruge PKCE som enhver klient; kun kode- og refresh-grants kan registreres | Foundation API 2.2.3, RFC 7591 | `test_oauth2::test_dynamic_registration_when_enabled`, `::test_registration_is_404_when_disabled` |
| Selvregistrerede klienter, der ikke udsteder nogen token i `dynamic_client_unused_days`, slettes med deres tokens (oprydningen og `opencde client prune`); manuelle klienter udløber aldrig | Dataminimering | `test_maintenance::test_unused_self_registered_clients_expire_and_can_be_pruned`, `test_oauth2::test_dynamic_registration_when_enabled` |
| Registreringen kan begrænses yderligere: `dynamic_client_registration_token` kræver et indledende adgangstoken (RFC 7591 §3), og `dynamic_client_approval` holder en selvregistreret klient deaktiveret, indtil en administrator godkender den | RFC 7591 §3 | `test_registration_controls` |
| Kun Bearer på API'et; HTTP Basic afvises | Foundation API 2.2.1 | `test_foundation::test_current_user_requires_a_bearer_token` |
| Sider: streng CSP, ingen inline-kode, ingen indramning, ingen caching | OWASP ASVS 14.4 | `test_foundation::test_authorize_without_client_shows_an_error_page_and_never_redirects` |

## BCF API (etape 3)

| Kontrol | Standard | Suite |
|---|---|---|
| Projekter og sager nås fra brugernoden gennem `MEMBER_OF`; ikke-medlemmer får 404, aldrig 403 (ingen eksistenslækage) | OWASP API1 (BOLA) | `test_bcf_projects_topics::test_projects_and_extensions`, `::test_topic_authorization_matrix` |
| Rolle × handling-matrix håndhæves på serversiden for opret, opdatér og slet; `authorization`-objekterne fortæller sandheden | OWASP API5, BCF 1.2 | `test_bcf_projects_topics::test_topic_authorization_matrix`, `::test_project_rename_needs_manager` |
| Sagsværdier valideres mod projektets extensions; begrænsede længder; ukendte felter ignoreres | Foundation API 1.8, BCF 3.1.4 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| OData: felthvidliste, parametriseret Cypher, begrænsede `$top`/`$skip`, 400 ved ukendte felter eller usorterbare kolonner | OWASP API8 (injektion) | `test_odata`, `test_bcf_projects_topics::test_topic_odata_filtering_sorting_and_paging` |
| Klientvalgte guid'er skal være UUID'er og normaliseres; dubletter giver 409 | Foundation API 1.5.1 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| Hændelsesværdier afkortes (titler 128, tekster 1024 tegn) | Dataminimering | `events.py`, `test_topic_lifecycle_with_events` |

## BCF API: kommentarer, viewpoints, filer og dokumenter (etape 4)

| Kontrol | Standard | Suite |
|---|---|---|
| Snapshot- og bitmapdata skal være den deklarerede billedtype (magic bytes) og under `max_image_bytes`; tjekkes, før noget gemmes | OWASP ASVS 12.1, 12.2 | `test_bcf_helpers::test_decode_image_rejects`, `test_bcf_comments_viewpoints::test_viewpoint_rules_and_image_checks` |
| Binære uploads (dokumenter, snippets) streames til lageret under servergenererede nøgler og tælles mod `max_upload_bytes`; deklarerede størrelser stoles der ikke på | OWASP ASVS 12.1 | `test_bcf_links_documents::test_documents_and_files_information`, `test_core_helpers::test_storage_stream_counts_bytes` |
| Kun de to binære ruter er undtaget fra JSON-kropsgrænsen; chunked-kroppe tælles, når de ankommer | OWASP API4 | `test_headers_and_errors::test_chunked_body_over_the_limit_is_cut_off` |
| Downloads er vedhæftninger med sanerede, RFC 8187-kodede filnavne, `application/octet-stream` for dokumenter, `nosniff`; uploadet indhold renderes aldrig | OWASP ASVS 12.5 | `test_bcf_helpers::test_filename_from_content_disposition`, `test_documents_and_files_information` |
| Klientfilnavne når aldrig en sti; lagernøgler er UUID'er | OWASP ASVS 12.3 | `test_bcf_helpers::test_filename_from_content_disposition`, `storage.py` |
| Kommentarer og viewpoints nås gennem bruger → projekt → sag; udenforstående får 404; rollematrix for opret/opdatér/slet; 409 i stedet for stille datatab ved sletning af et refereret viewpoint | OWASP API1, API5 | `test_viewpoint_lifecycle`, `test_comment_lifecycle_and_events` |
| Dokumentreferencer accepterer kun http(s)-URL'er og skal pege på et dokument i samme projekt | OWASP ASVS 5.1 | `test_document_references`, `test_bcf_helpers::test_component_comment_and_reference_rules` |
| Relaterede sager skal tilhøre samme projekt | OWASP API1 | `test_related_topics_and_files` |
| Numerisk input er endeligt (ingen NaN eller uendelighed), lister og strenge begrænsede | OWASP ASVS 5.1 | `test_bcf_helpers::test_viewpoint_rules`, `schemas.py` |

## Documents API og browserlogin (etape 5)

| Kontrol | Standard | Suite |
|---|---|---|
| UI-links bærer en 256-bit token gemt kun som hash, gyldig i `documents_session_ttl_seconds`; API-sidens URL'er bruger et separat offentligt id og kræver en bearer-token | OWASP ASVS 3.2 | `test_documents_api::test_upload_flow_versions_and_queries` |
| Browseren skal være logget ind som den bruger, der startede forløbet; andre brugere får 403, anonyme browsere sendes til login | OWASP API1 | `test_documents_api` (upload- og udvælgelsesforløb) |
| Sessionscookie: tilfældig, hashet, `HttpOnly`, `SameSite=Strict`, `Secure` over https, inaktivitets- og absolut udløb, slettet ved logout | OWASP ASVS 3.3, 3.4 | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Signerede formulartokens bundet til sessionen ved hver side-POST; `Sec-Fetch-Site`/`Origin` tjekkes også | CSRF, OWASP ASVS 4.2.2 | `test_web_signin::test_cross_site_posts_are_refused_and_next_cannot_leave_the_site`, `test_documents_api` |
| `next` efter login er kun en lokal sti (ingen åben omdirigering) | OWASP ASVS 5.1.5 | `test_documents_helpers::test_safe_next_only_accepts_local_paths` |
| Callback-URL'er er kun http(s) og hentes aldrig af serveren; browseren omdirigeres med URL-kodede parametre | SSRF, OWASP ASVS 12.6 | `test_documents_helpers::test_callback_and_extensions_rules`, `test_upload_cancelled_in_the_browser` |
| Dele streames og skal matche det annoncerede interval præcist; filer over `max_upload_bytes` afvises ved instruktionen; den samlede størrelse verificeres og hashes | OWASP ASVS 12.1 | `test_upload_flow_versions_and_queries` |
| Uploads kræver projekthandlingen `createDocument`; downloads kræver medlemskab; udenforstående får 404 | OWASP API1, API5 | `test_upload_cancelled_in_the_browser`, `test_selection_flow_with_filtering_and_browser_upload` |
| Svarkroppe indeholder kun specifikationens felter (ingen lagernøgler, ingen hashes) | OWASP API3 | `validate_documents` i hver Documents API-test |
| Udløbne sessioner og dele ryddes med deres filer | Oprydning | `cleanup.py`, `test_graph_core::test_expired_nodes_are_deleted_in_batches` |

## Admin-UI og kontoside (etape 6)

| Kontrol | Standard | Suite |
|---|---|---|
| `/admin` kræver en logget ind administrator; andre brugere får en HTML 404, anonyme browsere sendes til login | OWASP API5, ASVS 4.1 | `test_admin_ui::test_admin_pages_need_the_admin_role` |
| Hver admin-POST kræver en signeret token bundet til administratorens session og objektet, og en same-origin-browserforespørgsel | CSRF, OWASP ASVS 4.2.2 | `test_admin_ui::test_csrf_protections_on_admin_forms` |
| Nulstilling af kodeord, ændring af adminflaget, rotation af klienthemmeligheder og sletning kræver administratorens eget kodeord igen | OWASP ASVS 2.2.5 | `test_user_management`, `test_project_management_reaches_the_bcf_api`, `test_client_management_and_secret_rotation` |
| Administratorer kan ikke deaktivere, degradere eller slette deres egen konto | Forebyggelse af udelukkelse | `test_user_management` |
| Genererede kodeord og klienthemmeligheder vises én gang; nulstillede kodeord skal skiftes ved næste login; deaktivering tilbagekalder tokens | OWASP ASVS 2.1, 2.5 | `test_user_management`, `test_client_management_and_secret_rotation`, `test_forced_password_change` |
| Hver adminhandling registreres i revisionsloggen uden hemmeligheder | OWASP ASVS 7.1 | `test_sessions_audit_and_settings_pages` |
| Indstillingssiden viser aldrig hemmeligheder | OWASP ASVS 14.3 | `test_sessions_audit_and_settings_pages` |
| Siderne bærer den strenge CSP, ingen inline-kode; forbedringsscripts bygger DOM kun med `textContent` | OWASP ASVS 14.4 | `test_admin_pages_need_the_admin_role`, `tests/ui` (ingen konsolfejl) |
| Tilgængelighed: ingen alvorlige eller kritiske axe-core-overtrædelser på nogen adminside | WCAG 2.2 AA | `tests/ui/test_admin_browser.py` |

## IFC-graf (etape 9)

| Kontrol | Standard | Suite |
|---|---|---|
| IFC-parsing kører i en separat arbejdsproces med tidsgrænse, hukommelsesgrænse (POSIX) og entitetsloft; et nedbrud eller en hængning fælder modellen, ikke serveren | OWASP ASVS 12.4 | `test_ifcgraph_convert::test_geometry_can_be_included_and_limits_are_enforced`, `test_ifcgraph` |
| `.ifczip` pakkes kun ud, når den indeholder præcis én `.ifc`, med uploadens størrelsesloft på de udpakkede bytes | Zip-bombe | `service._prepare_input` |
| Sammenligningen og den tabsfri konvertering læser filer med deres egen læser: det, den ikke kan læse, afviser den, dens mønstre kan ikke backtracke, og indlejringen er begrænset | OWASP ASVS 5.1 | `test_ifcgraph_step` |
| Labels og relationstyper fra konverteren valideres som identifikatorer, før de når Cypher; alt andet er en parameter | OWASP API8 | `importer._safe`, `test_ifcgraph` |
| En uploadet IFC-fil kontrolleres mod IFC-skemaet i samme slags arbejdsproces med de samme grænser og holdes aldrig tilbage af det; rapporten læses kun gennem medlemskab af projektet, og loggen får antallet af anmærkninger, aldrig deres meddelelser | OWASP ASVS 12.4, ASVS 7.1 | `test_ifc_validation`, `test_ifcgraph_service` |
| Konverteringsfejl registreres på `IfcModel`-noden og logges uden filens indhold | OWASP ASVS 7.1 | `test_ifcgraph` |

## Udrulning og sikkerhedskopier (etape 8)

| Kontrol | Suite |
|---|---|
| Containeren kører som ikke-root på et skrivebeskyttet rodfilsystem med fjernede capabilities; databasen kun på det private netværk | `Dockerfile`, `compose.prod.yaml`; Trivy-imagescan i `release.yml` og `security-nightly.yml` |
| Sikkerhedskopiering og gendannelse frem og tilbage bevarer noder, relationer og filer, på Neo4j og Memgraph | `test_backup` |
| Natlig ZAP-baseline mod den kørende server | `security-nightly.yml`, `.zap/rules.tsv` |

## Platform (etape 0–1, kontraktfuzzing etape 11)

| Kontrol | Suite |
|---|---|
| Sikkerhedsheadere på hvert svar, også fejl | `test_headers_and_errors` |
| Autorisations-, udvælgelses- og uploadsiderne tilføjer klientens origin til `form-action`, da Chromium tjekker den mod den omdirigering, der svarer på formularen; alle andre sider beholder `form-action 'self'` | `test_security_oauth2::test_the_authorization_page_lets_the_browser_follow_the_redirect_to_the_client`, `tests/ui/test_popup_opener.py::test_the_sign_in_popup_comes_back_to_the_client` |
| `Cross-Origin-Opener-Policy: same-origin` kun på administrations- og kontosiderne; de sider, en klient åbner i et pop op-vindue, beholder browserens standard, så klientens callback-side kan nå sin opener (verificeret i en rigtig browser) | `test_headers_and_errors::test_opener_policy_isolates_only_the_administration`, `tests/ui/test_popup_opener.py` |
| Browserens tjek af en service workers script, på en hvilken som helst adresse, besvares med et script, der fjerner workeren, tømmer cachene og genindlæser vinduerne, da en worker, som en anden app har efterladt på serverens adresse, ellers svarer med gamle kopier af siderne; serveren har ingen egen worker. Det retter et uheld og er ingen sikkerhedskontrol | `test_foreign_workers` |
| Sprogcookien indeholder kun en kode fra den faste liste på syv og er `HttpOnly` og `SameSite=Lax`; intet script læser den | `test_headers_and_errors::test_the_language_cookie_holds_only_a_known_language` |
| Kun specifikationens fejlkrop; ingen stakspor eller gentaget input | `test_headers_and_errors`, `errors.py` |
| Størrelsesgrænse for forespørgselskroppen før parsing | `test_headers_and_errors::test_oversized_body_is_rejected_before_parsing` |
| Request-id saneres | `test_headers_and_errors::test_request_id_is_echoed_or_minted` |
| CORS uden credentials, kun på API-stierne; sider deles aldrig cross-origin | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials`, `::test_pages_are_never_shared_cross_origin` |
| CORS tillader og eksponerer `Content-Disposition`, så browserklienter kan uploade og downloade binære filer (Foundation API 1.9) | `test_headers_and_errors::test_cors_allows_and_exposes_content_disposition` |
| Uhåndterede fejl bliver specifikationens 500 inden for CORS- og sikkerhedsheaderlagene, så browserklienter ser statussen, ikke en netværksfejl | `test_headers_and_errors::test_unhandled_errors_keep_cors_and_security_headers` |
| Hastighedsbegrænsede endepunkter giver slowapi et Response til dets headere (med grænser slået til fejlede et endepunkt, der returnerede en dict) | `test_rate_limit_endpoints`, `test_bcf_links_documents::test_upload_works_with_rate_limits_enabled` |
| Forespørgselslog (tilvalg): metode, sti uden forespørgselsstreng, operation, status, tid, request-id, bytetal og kalder; aldrig kroppe, headere eller tokens; poster udløber; kun læsbar for administratorer (session på siden, bearer med scopet `admin` på `/admin/api/requests`) | `test_requestlog::test_requests_are_logged_without_bodies_and_served_to_administrators` |
| Grafforespørgsel (tilvalg): læsende Cypher for administratorer med scopet `admin`; skrivende klausuler og ikke-skemaprocedurer afvises før databasen, beskyttede egenskaber afvises og holdes ude af svarene, hashes maskeres, række- og tidsgrænser, hvert kald revideres; monteres ikke, medmindre det er slået til | `test_graph_query::test_the_fences_hold`, `test_graph_query (unit)`, `test_capabilities::test_the_graph_query_is_announced_with_its_limits_when_on` |
| Den interaktive API-dokumentation (tredjeparts Swagger UI fra et CDN) har sin egen politik og er slået fra i produktion som standard | `test_headers_and_errors::test_api_docs_have_their_own_policy_and_are_off_in_production` |
| Produktion nægter at starte uden https, databasekodeord og hemmelig nøgle | `test_settings` |
| Lagernøgler bygges kun af UUID'er; path traversal umulig | `test_core_helpers::test_storage_keys_cannot_escape` |
| Streamende skrivninger tæller bytes og håndhæver grænser | `test_core_helpers::test_storage_stream_counts_bytes` |
| Cypher forbliver parametriseret og portabel | `test_core_helpers::test_dialect_ddl_and_cypher_lint`, Memgraph-kontraktkørsel |
| Udløbne hemmeligheder slettes på en timer | `test_graph_core::test_expired_nodes_are_deleted_in_batches` |
| Uret sammenlignes med NTP i `opencde doctor` og på indstillingssiden (udløbstider afhænger af det) | `test_doctor` |
| Afhængigheds-cooldown og fastgjorte actions | `.github/workflows/ci.yml`, `pyproject.toml` |
| Hver dokumenteret operation overlever genereret gyldigt og ugyldigt input: ingen 5xx, svarene matcher OpenAPI-skemaerne, ugyldigt input får et 4xx | `tests/e2e/test_schemathesis.py` (Schemathesis; `OPENCDE_SCHEMATHESIS_EXAMPLES` til den lange natlige kørsel) |
