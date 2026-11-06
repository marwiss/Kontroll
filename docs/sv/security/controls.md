# Säkerhetskontroller och testerna som bevisar dem

Varje kontroll har minst ett automatiskt test. "Svit" namnger testmodulen.

## Foundation API och OAuth2 (etapp 2)

| Kontroll | Standard | Svit |
|---|---|---|
| PKCE `S256` krävs för varje klient utom en märkt (nästa rad); `plain` och saknad challenge avvisas | RFC 7636, OAuth 2.1 | `test_security_oauth2::test_pkce_is_mandatory_and_plain_is_refused` |
| En konfidentiell klient som en administratör har märkt får utelämna PKCE, som BCF API 2.1 gör: en challenge som den ändå skickar upprätthålls, en verifier utan challenge avvisas, en publik klient kan inte märkas, och en redirect-URI som anges i begäran måste anges igen | RFC 9700 §2.1.1, RFC 6749 §4.1.3 | `test_oauth2_without_pkce` |
| Exakt matchning av redirect-URI; loopback-porten får variera; oregistrerad URI visas, följs aldrig | RFC 9700 §4.1, RFC 8252 §7.3 | `test_security_oauth2::test_unregistered_redirect_uri_is_shown_not_followed`, `::test_loopback_port_may_vary_but_host_may_not` |
| `state` krävs; okänt scope och ostödd svarstyp omdirigeras som fel med `state` | RFC 6749 §4.1.2.1 | `test_security_oauth2::test_state_is_required_and_unknown_scope_is_refused` |
| `iss` i auktoriseringssvaret | RFC 9207 | `test_oauth2::test_public_client_flow_with_pkce` |
| Engångskoder (60 s); replay återkallar tokens från den första inlösningen | RFC 9700 §4.5 | `test_oauth2::test_code_is_single_use_and_replay_revokes_tokens` |
| Koden bunden till klient, redirect-URI och verifier | RFC 6749 §4.1.3 | `test_security_oauth2::test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Opaka tokens lagrade bara som SHA-256-hashar | ADR 0002 | `test_graph_core` (schema), kodgranskning |
| Rotation av refresh-tokens med upptäckt av återanvändning som återkallar familjen | RFC 9700 §4.14 | `test_oauth2::test_refresh_rotates_and_reuse_revokes_the_family` |
| En refresh-token som inte använts på två veckor (`refresh_token_idle_seconds`) slutar fungera och tar sin familj med sig, inom den absoluta livslängden på 30 dagar | RFC 9700 §4.14 | `test_oauth2::test_a_refresh_token_left_unused_stops_working` |
| Klientautentisering: Basic eller formulär; publika klienter visar aldrig någon hemlighet; 401 med `WWW-Authenticate` | RFC 6749 §2.3 | `test_security_oauth2::test_client_authentication_failures` |
| Tokensvar `Cache-Control: no-store`, `Pragma: no-cache`, status 201 | RFC 6749 §5.1, Foundation API | `test_oauth2::test_token_response_is_never_cached_and_has_spec_fields` |
| Återkallning av access-tokens och hela refresh-familjer | RFC 7009 | `test_oauth2::test_revocation` |
| Samtycke kan nekas (`access_denied`) | RFC 6749 §4.1.2.1 | `test_oauth2::test_deny_redirects_with_access_denied` |
| Signerade, utgående, ändamålsbundna formulärtokens; manipulation avvisas | CSRF | `test_security_oauth2::test_tampered_or_replayed_form_token_is_refused`, `test_auth_primitives` |
| Inloggning hastighetsbegränsad per adress | OWASP ASVS 2.2.1 | `test_security_oauth2::test_sign_in_is_rate_limited` |
| Misslyckade inloggningar får ett användarnamn att vänta: efter fem i rad en väntan som fördubblas från 30 sekunder upp till 15 minuter, utöver gränsen per adress. Okända namn räknas likadant, så svaret säger inget om vilka konton som finns, och namnen lagras som hashvärden | OWASP ASVS 6.3 | `test_sign_in_throttle` |
| En gräns per adress på varje anrop (600 i minuten, `OPENCDE_RATE_LIMIT_API`), snävare på administrationen (240 i minuten); hälsokontroller och statiska filer är undantagna; en delad lagring som fallerar stoppar ingenting | OWASP API4 | `test_rate_limits` |
| Generiskt felmeddelande; inaktiverade konton kan inte logga in och förlorar sina tokens | OWASP ASVS 2.2 | `test_security_oauth2::test_disabled_user_cannot_sign_in_and_loses_tokens` |
| Lösenord, koder och tokens förekommer aldrig i loggar | OWASP ASVS 7.1 | `test_security_oauth2::test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Argon2id-lösenordshashning; policy (längd, zxcvbn, inte användarnamnet) | OWASP ASVS 2.1 | `test_core_helpers::test_password_policy_and_hashing` |
| Dynamisk registrering avstängd som standard; bara https- eller loopback-omdirigeringar; publika klienter (RFC 7591 `token_endpoint_auth_method: "none"`) får ingen hemlighet och måste använda PKCE som varje klient; bara kod- och refresh-granten kan registreras | Foundation API 2.2.3, RFC 7591 | `test_oauth2::test_dynamic_registration_when_enabled`, `::test_registration_is_404_when_disabled` |
| Självregistrerade klienter som inte utfärdar någon token på `dynamic_client_unused_days` tas bort med sina tokens (städaren och `opencde client prune`); manuella klienter går aldrig ut | Dataminimering | `test_maintenance::test_unused_self_registered_clients_expire_and_can_be_pruned`, `test_oauth2::test_dynamic_registration_when_enabled` |
| Registreringen kan begränsas ytterligare: `dynamic_client_registration_token` kräver en initial åtkomsttoken (RFC 7591 §3), och `dynamic_client_approval` håller en självregistrerad klient avstängd tills en administratör godkänner den | RFC 7591 §3 | `test_registration_controls` |
| Bara Bearer på API:t; HTTP Basic avvisas | Foundation API 2.2.1 | `test_foundation::test_current_user_requires_a_bearer_token` |
| Sidor: strikt CSP, ingen inline-kod, ingen inramning, ingen cachning | OWASP ASVS 14.4 | `test_foundation::test_authorize_without_client_shows_an_error_page_and_never_redirects` |

## BCF API (etapp 3)

| Kontroll | Standard | Svit |
|---|---|---|
| Projekt och ärenden nås från användarnoden via `MEMBER_OF`; icke-medlemmar får 404, aldrig 403 (ingen existensläcka) | OWASP API1 (BOLA) | `test_bcf_projects_topics::test_projects_and_extensions`, `::test_topic_authorization_matrix` |
| Roll × handling-matris upprätthålls på serversidan för skapa, uppdatera och ta bort; `authorization`-objekten talar sanning | OWASP API5, BCF 1.2 | `test_bcf_projects_topics::test_topic_authorization_matrix`, `::test_project_rename_needs_manager` |
| Ärendevärden valideras mot projektets extensions; begränsade längder; okända fält ignoreras | Foundation API 1.8, BCF 3.1.4 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| OData: fältvitlista, parametriserad Cypher, begränsade `$top`/`$skip`, 400 vid okända fält eller osorterbara kolumner | OWASP API8 (injektion) | `test_odata`, `test_bcf_projects_topics::test_topic_odata_filtering_sorting_and_paging` |
| Klientvalda guid måste vara UUID och normaliseras; dubbletter ger 409 | Foundation API 1.5.1 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| Händelsevärden klipps (titlar 128, texter 1024 tecken) | Dataminimering | `events.py`, `test_topic_lifecycle_with_events` |

## BCF API: kommentarer, viewpoints, filer och dokument (etapp 4)

| Kontroll | Standard | Svit |
|---|---|---|
| Snapshot- och bitmapdata måste vara den deklarerade bildtypen (magic bytes) och under `max_image_bytes`; kontrolleras innan något lagras | OWASP ASVS 12.1, 12.2 | `test_bcf_helpers::test_decode_image_rejects`, `test_bcf_comments_viewpoints::test_viewpoint_rules_and_image_checks` |
| Binära uppladdningar (dokument, snippets) strömmas till lagringen under servergjorda nycklar och räknas mot `max_upload_bytes`; deklarerade storlekar litas inte på | OWASP ASVS 12.1 | `test_bcf_links_documents::test_documents_and_files_information`, `test_core_helpers::test_storage_stream_counts_bytes` |
| Bara de två binära rutterna är undantagna från JSON-kroppsgränsen; chunked-kroppar räknas när de kommer | OWASP API4 | `test_headers_and_errors::test_chunked_body_over_the_limit_is_cut_off` |
| Nedladdningar är bilagor med sanerade, RFC 8187-kodade filnamn, `application/octet-stream` för dokument, `nosniff`; uppladdat innehåll renderas aldrig | OWASP ASVS 12.5 | `test_bcf_helpers::test_filename_from_content_disposition`, `test_documents_and_files_information` |
| Klientfilnamn når aldrig en sökväg; lagringsnycklar är UUID | OWASP ASVS 12.3 | `test_bcf_helpers::test_filename_from_content_disposition`, `storage.py` |
| Kommentarer och viewpoints nås via användare → projekt → ärende; utomstående får 404; rollmatris för skapa/uppdatera/ta bort; 409 i stället för tyst dataförlust när en refererad viewpoint tas bort | OWASP API1, API5 | `test_viewpoint_lifecycle`, `test_comment_lifecycle_and_events` |
| Dokumentreferenser accepterar bara http(s)-URL:er och måste peka på ett dokument i samma projekt | OWASP ASVS 5.1 | `test_document_references`, `test_bcf_helpers::test_component_comment_and_reference_rules` |
| Relaterade ärenden måste tillhöra samma projekt | OWASP API1 | `test_related_topics_and_files` |
| Numerisk indata är finit (inga NaN eller oändligheter), listor och strängar begränsade | OWASP ASVS 5.1 | `test_bcf_helpers::test_viewpoint_rules`, `schemas.py` |

## Documents API och webbläsarinloggning (etapp 5)

| Kontroll | Standard | Svit |
|---|---|---|
| UI-länkar bär en 256-bitars token lagrad bara som hash, giltig i `documents_session_ttl_seconds`; API-sidans URL:er använder ett separat publikt id och kräver en bearer-token | OWASP ASVS 3.2 | `test_documents_api::test_upload_flow_versions_and_queries` |
| Webbläsaren måste vara inloggad som den användare som startade flödet; andra användare får 403, anonyma webbläsare skickas till inloggning | OWASP API1 | `test_documents_api` (uppladdnings- och urvalsflöden) |
| Sessionskaka: slumpmässig, hashad, `HttpOnly`, `SameSite=Strict`, `Secure` över https, inaktivitets- och absolut utgång, tas bort vid utloggning | OWASP ASVS 3.3, 3.4 | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Signerade formulärtokens bundna till sessionen vid varje sid-POST; `Sec-Fetch-Site`/`Origin` kontrolleras också | CSRF, OWASP ASVS 4.2.2 | `test_web_signin::test_cross_site_posts_are_refused_and_next_cannot_leave_the_site`, `test_documents_api` |
| `next` efter inloggning är bara en lokal sökväg (ingen öppen omdirigering) | OWASP ASVS 5.1.5 | `test_documents_helpers::test_safe_next_only_accepts_local_paths` |
| Callback-URL:er är bara http(s) och hämtas aldrig av servern; webbläsaren omdirigeras med URL-kodade parametrar | SSRF, OWASP ASVS 12.6 | `test_documents_helpers::test_callback_and_extensions_rules`, `test_upload_cancelled_in_the_browser` |
| Delar strömmas och måste matcha det annonserade intervallet exakt; filer över `max_upload_bytes` avvisas vid instruktionen; den sammansatta storleken verifieras och hashas | OWASP ASVS 12.1 | `test_upload_flow_versions_and_queries` |
| Uppladdningar kräver projekthandlingen `createDocument`; nedladdningar kräver medlemskap; utomstående får 404 | OWASP API1, API5 | `test_upload_cancelled_in_the_browser`, `test_selection_flow_with_filtering_and_browser_upload` |
| Svarskroppar innehåller bara specifikationens fält (inga lagringsnycklar, inga hashar) | OWASP API3 | `validate_documents` i varje Documents API-test |
| Utgångna sessioner och delar städas med sina filer | Underhåll | `cleanup.py`, `test_graph_core::test_expired_nodes_are_deleted_in_batches` |

## Admin-gränssnitt och kontosida (etapp 6)

| Kontroll | Standard | Svit |
|---|---|---|
| `/admin` kräver en inloggad administratör; andra användare får en HTML 404, anonyma webbläsare skickas till inloggning | OWASP API5, ASVS 4.1 | `test_admin_ui::test_admin_pages_need_the_admin_role` |
| Varje admin-POST kräver en signerad token bunden till administratörens session och objektet, och en same-origin-begäran från webbläsaren | CSRF, OWASP ASVS 4.2.2 | `test_admin_ui::test_csrf_protections_on_admin_forms` |
| Att återställa lösenord, ändra adminflaggan, rotera klienthemligheter och ta bort kräver administratörens eget lösenord igen | OWASP ASVS 2.2.5 | `test_user_management`, `test_project_management_reaches_the_bcf_api`, `test_client_management_and_secret_rotation` |
| Administratörer kan inte inaktivera, degradera eller ta bort sitt eget konto | Skydd mot utelåsning | `test_user_management` |
| Genererade lösenord och klienthemligheter visas en gång; återställda lösenord måste bytas vid nästa inloggning; inaktivering återkallar tokens | OWASP ASVS 2.1, 2.5 | `test_user_management`, `test_client_management_and_secret_rotation`, `test_forced_password_change` |
| Varje adminhandling registreras i revisionsloggen utan hemligheter | OWASP ASVS 7.1 | `test_sessions_audit_and_settings_pages` |
| Inställningssidan visar aldrig hemligheter | OWASP ASVS 14.3 | `test_sessions_audit_and_settings_pages` |
| Sidorna bär den strikta CSP:n, ingen inline-kod; förbättringsskripten bygger DOM bara med `textContent` | OWASP ASVS 14.4 | `test_admin_pages_need_the_admin_role`, `tests/ui` (inga konsolfel) |
| Tillgänglighet: inga allvarliga eller kritiska axe-core-överträdelser på någon adminsida | WCAG 2.2 AA | `tests/ui/test_admin_browser.py` |

## IFC-graf (etapp 9)

| Kontroll | Standard | Svit |
|---|---|---|
| IFC-tolkningen körs i en separat arbetsprocess med tidsgräns, minnesgräns (POSIX) och entitetstak; en krasch eller hängning fäller modellen, inte servern | OWASP ASVS 12.4 | `test_ifcgraph_convert::test_geometry_can_be_included_and_limits_are_enforced`, `test_ifcgraph` |
| `.ifczip` packas upp bara när den innehåller exakt en `.ifc`, med uppladdningens storlekstak på de uppackade bytena | Zip-bomb | `service._prepare_input` |
| Etiketter och relationstyper från konverteraren valideras som identifierare innan de når Cypher; allt annat är en parameter | OWASP API8 | `importer._safe`, `test_ifcgraph` |
| Konverteringsfel registreras på `IfcModel`-noden och loggas utan filens innehåll | OWASP ASVS 7.1 | `test_ifcgraph` |

## Driftsättning och säkerhetskopior (etapp 8)

| Kontroll | Svit |
|---|---|
| Containern körs som icke-root på ett skrivskyddat rotfilsystem med borttagna capabilities; databasen bara på det privata nätet | `Dockerfile`, `compose.prod.yaml`; Trivy-avbildningsskanning i `release.yml` och `security-nightly.yml` |
| Säkerhetskopiering och återställning tur och retur behåller noder, relationer och filer, på Neo4j och Memgraph | `test_backup` |
| Nattlig ZAP-baseline mot den körande servern | `security-nightly.yml`, `.zap/rules.tsv` |

## Plattform (etapp 0–1, kontraktsfuzzning etapp 11)

| Kontroll | Svit |
|---|---|
| Säkerhetshuvuden på varje svar, även fel | `test_headers_and_errors` |
| Auktoriserings-, urvals- och uppladdningssidorna lägger till klientens origin i `form-action`, eftersom Chromium kontrollerar den mot omdirigeringen som svarar på formuläret; varje annan sida behåller `form-action 'self'` | `test_security_oauth2::test_the_authorization_page_lets_the_browser_follow_the_redirect_to_the_client`, `tests/ui/test_popup_opener.py::test_the_sign_in_popup_comes_back_to_the_client` |
| `Cross-Origin-Opener-Policy: same-origin` bara på administrations- och kontosidorna; sidorna en klient öppnar i ett popup-fönster behåller webbläsarens standard så att klientens callback-sida kan nå sin opener (verifierat i en riktig webbläsare) | `test_headers_and_errors::test_opener_policy_isolates_only_the_administration`, `tests/ui/test_popup_opener.py` |
| Webbläsarens kontroll av en service workers skript, på vilken adress som helst, besvaras med ett skript som tar bort workern, tömmer cacheminnena och laddar om fönstren, eftersom en worker som en annan app lämnat på serverns adress annars svarar med gamla kopior av sidorna; servern har ingen egen worker. Det här rättar en olyckshändelse och är ingen säkerhetskontroll | `test_foreign_workers` |
| Språkkakan håller bara en kod ur den fasta listan på sju och är `HttpOnly` och `SameSite=Lax`; inget skript läser den | `test_headers_and_errors::test_the_language_cookie_holds_only_a_known_language` |
| Bara specens felkropp; inga stackspår eller ekad indata | `test_headers_and_errors`, `errors.py` |
| Storleksgräns för begärans kropp före tolkning | `test_headers_and_errors::test_oversized_body_is_rejected_before_parsing` |
| Request-id saneras | `test_headers_and_errors::test_request_id_is_echoed_or_minted` |
| CORS utan credentials, bara på API-sökvägarna; sidor delas aldrig cross-origin | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials`, `::test_pages_are_never_shared_cross_origin` |
| CORS tillåter och exponerar `Content-Disposition`, så att webbläsarklienter kan ladda upp och ned binärer (Foundation API 1.9) | `test_headers_and_errors::test_cors_allows_and_exposes_content_disposition` |
| Ohanterade fel blir specens 500 innanför CORS- och säkerhetshuvudlagren, så att webbläsarklienter ser statusen, inte ett nätverksfel | `test_headers_and_errors::test_unhandled_errors_keep_cors_and_security_headers` |
| Hastighetsbegränsade endpoints ger slowapi ett Response för dess huvuden (med gränser påslagna misslyckades en endpoint som returnerade en dict) | `test_rate_limit_endpoints`, `test_bcf_links_documents::test_upload_works_with_rate_limits_enabled` |
| Begärandelogg (opt-in): metod, sökväg utan frågesträng, operation, status, tid, request-id, bytestorlekar och anropare; aldrig kroppar, huvuden eller tokens; posterna går ut; läsbar bara av administratörer (session på sidan, bearer med scopet `admin` på `/admin/api/requests`) | `test_requestlog::test_requests_are_logged_without_bodies_and_served_to_administrators` |
| Graffråga (opt-in): läsande Cypher för administratörer med scopet `admin`; skrivande satsdelar och icke-schemaprocedurer avvisas före databasen, skyddade egenskaper avvisas och hålls utanför svaren, hashar maskeras, rad- och tidsgränser, varje anrop revideras; monteras inte om den inte är påslagen | `test_graph_query::test_the_fences_hold`, `test_graph_query (unit)`, `test_capabilities::test_the_graph_query_is_announced_with_its_limits_when_on` |
| Den interaktiva API-dokumentationen (tredjeparts Swagger UI från ett CDN) har en egen policy och är avstängd i produktion som standard | `test_headers_and_errors::test_api_docs_have_their_own_policy_and_are_off_in_production` |
| Produktion vägrar starta utan https, databaslösenord och hemlig nyckel | `test_settings` |
| Lagringsnycklar byggs bara av UUID; path traversal omöjlig | `test_core_helpers::test_storage_keys_cannot_escape` |
| Strömmande skrivningar räknar bytes och upprätthåller gränser | `test_core_helpers::test_storage_stream_counts_bytes` |
| Cypher förblir parametriserad och portabel | `test_core_helpers::test_dialect_ddl_and_cypher_lint`, Memgraph-kontraktskörning |
| Utgångna hemligheter tas bort på en timer | `test_graph_core::test_expired_nodes_are_deleted_in_batches` |
| Klockan jämförs med NTP i `opencde doctor` och på inställningssidan (utgångstider beror på den) | `test_doctor` |
| Beroende-cooldown och pinnade actions | `.github/workflows/ci.yml`, `pyproject.toml` |
| Varje dokumenterad operation överlever genererad giltig och ogiltig indata: inga 5xx, svaren matchar OpenAPI-schemana, ogiltig indata får 4xx | `tests/e2e/test_schemathesis.py` (Schemathesis; `OPENCDE_SCHEMATHESIS_EXAMPLES` för den långa nattliga körningen) |
