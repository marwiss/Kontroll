# Öryggisvarnir og prófin sem sanna þær

Hver vörn hefur að minnsta kosti eitt sjálfvirkt próf. „Svíta“ nefnir
prófunareininguna.

## Foundation API og OAuth2 (áfangi 2)

| Vörn | Staðall | Svíta |
|---|---|---|
| PKCE `S256` krafist fyrir hvern biðlara nema merktan (næsta lína); `plain` og vantandi challenge hafnað | RFC 7636, OAuth 2.1 | `test_security_oauth2::test_pkce_is_mandatory_and_plain_is_refused` |
| Trúnaðarbiðlari sem stjórnandi hefur merkt má sleppa PKCE, eins og BCF API 2.1 gerir: challenge sem hann sendir samt er framfylgt, verifier án challenge er hafnað, opinberan biðlara er ekki hægt að merkja, og redirect-URI sem er nefnt í beiðninni verður að nefna aftur | RFC 9700 §2.1.1, RFC 6749 §4.1.3 | `test_oauth2_without_pkce` |
| Nákvæm samsvörun redirect-URI; loopback-gátt má vera breytileg; óskráð URI sýnd, aldrei fylgt | RFC 9700 §4.1, RFC 8252 §7.3 | `test_security_oauth2::test_unregistered_redirect_uri_is_shown_not_followed`, `::test_loopback_port_may_vary_but_host_may_not` |
| `state` krafist; óþekktri heimild og óstuddri svargerð áframsent sem villum með `state` | RFC 6749 §4.1.2.1 | `test_security_oauth2::test_state_is_required_and_unknown_scope_is_refused` |
| `iss` í heimildarsvarinu | RFC 9207 | `test_oauth2::test_public_client_flow_with_pkce` |
| Einnota kóðar (60 s); endurspilun afturkallar tókana úr fyrstu innlausn | RFC 9700 §4.5 | `test_oauth2::test_code_is_single_use_and_replay_revokes_tokens` |
| Kóði bundinn við biðlara, redirect-URI og verifier | RFC 6749 §4.1.3 | `test_security_oauth2::test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Ógegnsæir tókar geymdir aðeins sem SHA-256-tætigildi | ADR 0002 | `test_graph_core` (skema), kóðayfirferð |
| Skipti endurnýjunartóka með greiningu endurnotkunar sem afturkallar fjölskylduna | RFC 9700 §4.14 | `test_oauth2::test_refresh_rotates_and_reuse_revokes_the_family` |
| Refresh-tóki sem ekki hefur verið notaður í tvær vikur (`refresh_token_idle_seconds`) hættir að virka og tekur fjölskyldu sína með sér, innan 30 daga algjörs líftíma | RFC 9700 §4.14 | `test_oauth2::test_a_refresh_token_left_unused_stops_working` |
| Auðkenning biðlara: Basic eða eyðublað; opinberir biðlarar sýna aldrei leyndarmál; 401 með `WWW-Authenticate` | RFC 6749 §2.3 | `test_security_oauth2::test_client_authentication_failures` |
| Tókasvör `Cache-Control: no-store`, `Pragma: no-cache`, staða 201 | RFC 6749 §5.1, Foundation API | `test_oauth2::test_token_response_is_never_cached_and_has_spec_fields` |
| Afturköllun aðgangstóka og heilla endurnýjunarfjölskyldna | RFC 7009 | `test_oauth2::test_revocation` |
| Samþykki má neita (`access_denied`) | RFC 6749 §4.1.2.1 | `test_oauth2::test_deny_redirects_with_access_denied` |
| Undirritaðir, útrennandi, tilgangsbundnir eyðublaðstókar; átt við hafnað | CSRF | `test_security_oauth2::test_tampered_or_replayed_form_token_is_refused`, `test_auth_primitives` |
| Innskráning tíðnitakmörkuð á hvert vistfang | OWASP ASVS 2.2.1 | `test_security_oauth2::test_sign_in_is_rate_limited` |
| Misheppnaðar innskráningar láta notandanafn bíða: eftir fimm í röð bið sem tvöfaldast frá 30 sekúndum upp í 15 mínútur, til viðbótar við mörkin á hvert vistfang. Óþekkt nöfn teljast eins, svo að svarið segir ekkert um hvaða reikningar eru til, og nöfn eru geymd sem tætigildi | OWASP ASVS 6.3 | `test_sign_in_throttle` |
| Mörk á hvert vistfang á hverja beiðni (600 á mínútu, `OPENCDE_RATE_LIMIT_API`), þrengri á stjórnuninni (240 á mínútu); heilsufarsathuganir og fastar skrár eru undanskildar; sameiginleg geymsla sem bilar stöðvar ekkert | OWASP API4 | `test_rate_limits` |
| Almenn villuboð; óvirkir reikningar geta ekki skráð sig inn og tapa tókum sínum | OWASP ASVS 2.2 | `test_security_oauth2::test_disabled_user_cannot_sign_in_and_loses_tokens` |
| Lykilorð, kóðar og tókar koma aldrei fram í atvikaskrám | OWASP ASVS 7.1 | `test_security_oauth2::test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Argon2id-tæting lykilorða; stefna (lengd, zxcvbn, ekki notandanafn) | OWASP ASVS 2.1 | `test_core_helpers::test_password_policy_and_hashing` |
| Kvik skráning óvirk sjálfgefið; aðeins https- eða loopback-áframsendingar; opinberir biðlarar (RFC 7591 `token_endpoint_auth_method: "none"`) fá ekkert leyndarmál og þurfa PKCE eins og hver biðlari; aðeins kóða- og endurnýjunarveitingar má skrá | Foundation API 2.2.3, RFC 7591 | `test_oauth2::test_dynamic_registration_when_enabled`, `::test_registration_is_404_when_disabled` |
| Sjálfskráðum biðlurum sem gefa út engan tóka í `dynamic_client_unused_days` er eytt með tókum sínum (hreinsunin og `opencde client prune`); handvirkir biðlarar renna aldrei út | Lágmörkun gagna | `test_maintenance::test_unused_self_registered_clients_expire_and_can_be_pruned`, `test_oauth2::test_dynamic_registration_when_enabled` |
| Skráningu má takmarka frekar: `dynamic_client_registration_token` krefst upphafsaðgangstóka (RFC 7591 §3), og `dynamic_client_approval` heldur sjálfskráðum biðlara óvirkum þar til stjórnandi samþykkir hann | RFC 7591 §3 | `test_registration_controls` |
| Aðeins Bearer á forritaskilunum; HTTP Basic hafnað | Foundation API 2.2.1 | `test_foundation::test_current_user_requires_a_bearer_token` |
| Síður: strangt CSP, enginn innfelldur kóði, engin römmun, ekkert skyndiminni | OWASP ASVS 14.4 | `test_foundation::test_authorize_without_client_shows_an_error_page_and_never_redirects` |

## BCF API (áfangi 3)

| Vörn | Staðall | Svíta |
|---|---|---|
| Verkefni og mál eru nálguð frá notandahnútnum um `MEMBER_OF`; þeir sem ekki eru meðlimir fá 404, aldrei 403 (enginn tilvistarleki) | OWASP API1 (BOLA) | `test_bcf_projects_topics::test_projects_and_extensions`, `::test_topic_authorization_matrix` |
| Hlutverk × aðgerð-fylki framfylgt þjónsmegin fyrir stofnun, uppfærslu og eyðingu; `authorization`-hlutirnir segja satt | OWASP API5, BCF 1.2 | `test_bcf_projects_topics::test_topic_authorization_matrix`, `::test_project_rename_needs_manager` |
| Málagildi sannreynd gegn extensions verkefnisins; afmarkaðar lengdir; óþekkt svið hunsuð | Foundation API 1.8, BCF 3.1.4 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| OData: hvítlisti sviða, stikað Cypher, afmörkuð `$top`/`$skip`, 400 við óþekkt svið eða óraðanlega dálka | OWASP API8 (innspýting) | `test_odata`, `test_bcf_projects_topics::test_topic_odata_filtering_sorting_and_paging` |
| Guid valin af biðlara þurfa að vera UUID og eru stöðluð; tvítekningar gefa 409 | Foundation API 1.5.1 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| Atburðagildi klippt (titlar 128, textar 1024 tákn) | Lágmörkun gagna | `events.py`, `test_topic_lifecycle_with_events` |

## BCF API: athugasemdir, viewpoint, skrár og skjöl (áfangi 4)

| Vörn | Staðall | Svíta |
|---|---|---|
| Skyndimynda- og bitamyndagögn þurfa að vera uppgefin myndgerð (magic bytes) og undir `max_image_bytes`; athugað áður en nokkuð er geymt | OWASP ASVS 12.1, 12.2 | `test_bcf_helpers::test_decode_image_rejects`, `test_bcf_comments_viewpoints::test_viewpoint_rules_and_image_checks` |
| Tvíundarupphöl (skjöl, snippets) streyma í geymslu undir lyklum sem þjónninn býr til og eru talin gegn `max_upload_bytes`; uppgefnum stærðum er ekki treyst | OWASP ASVS 12.1 | `test_bcf_links_documents::test_documents_and_files_information`, `test_core_helpers::test_storage_stream_counts_bytes` |
| Aðeins tvíundarleiðirnar tvær eru undanþegnar JSON-meginmálsmörkunum; chunked-meginmál talin þegar þau berast | OWASP API4 | `test_headers_and_errors::test_chunked_body_over_the_limit_is_cut_off` |
| Niðurhöl eru viðhengi með hreinsuðum, RFC 8187-kóðuðum skráarheitum, `application/octet-stream` fyrir skjöl, `nosniff`; upphlaðið innihald er aldrei birt | OWASP ASVS 12.5 | `test_bcf_helpers::test_filename_from_content_disposition`, `test_documents_and_files_information` |
| Skráarheiti biðlara ná aldrei í slóð; geymslulyklar eru UUID | OWASP ASVS 12.3 | `test_bcf_helpers::test_filename_from_content_disposition`, `storage.py` |
| Athugasemdir og viewpoint eru nálguð um notandi → verkefni → mál; utanaðkomandi fá 404; hlutverkafylki fyrir stofnun/uppfærslu/eyðingu; 409 í stað hljóðláts gagnataps þegar viewpoint sem vísað er í er eytt | OWASP API1, API5 | `test_viewpoint_lifecycle`, `test_comment_lifecycle_and_events` |
| Skjalatilvísanir taka aðeins við http(s)-URL og þurfa að vísa á skjal sama verkefnis | OWASP ASVS 5.1 | `test_document_references`, `test_bcf_helpers::test_component_comment_and_reference_rules` |
| Tengd mál þurfa að tilheyra sama verkefni | OWASP API1 | `test_related_topics_and_files` |
| Töluleg inntök eru endanleg (ekkert NaN eða óendanleiki), listar og strengir afmarkaðir | OWASP ASVS 5.1 | `test_bcf_helpers::test_viewpoint_rules`, `schemas.py` |

## Documents API og vafrainnskráning (áfangi 5)

| Vörn | Staðall | Svíta |
|---|---|---|
| UI-tenglar bera 256-bita tóka geymdan aðeins sem tætigildi, gildan í `documents_session_ttl_seconds`; URL á API-hlið nota sérstakt opinbert auðkenni og þurfa bearer-tóka | OWASP ASVS 3.2 | `test_documents_api::test_upload_flow_versions_and_queries` |
| Vafrinn þarf að vera innskráður sem notandinn sem hóf ferlið; aðrir notendur fá 403, nafnlausir vafrar eru sendir í innskráningu | OWASP API1 | `test_documents_api` (upphals- og valferli) |
| Setuvefkaka: slembin, tætt, `HttpOnly`, `SameSite=Strict`, `Secure` yfir https, aðgerðaleysis- og heildargildistími, eytt við útskráningu | OWASP ASVS 3.3, 3.4 | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Undirritaðir eyðublaðstókar bundnir við setuna á hverju POST síðu; `Sec-Fetch-Site`/`Origin` athugað líka | CSRF, OWASP ASVS 4.2.2 | `test_web_signin::test_cross_site_posts_are_refused_and_next_cannot_leave_the_site`, `test_documents_api` |
| `next` eftir innskráningu er aðeins staðbundin slóð (engin opin áframsending) | OWASP ASVS 5.1.5 | `test_documents_helpers::test_safe_next_only_accepts_local_paths` |
| Callback-URL eru aðeins http(s) og þjónninn sækir þær aldrei; vafranum er áframsent með URL-kóðuðum stikum | SSRF, OWASP ASVS 12.6 | `test_documents_helpers::test_callback_and_extensions_rules`, `test_upload_cancelled_in_the_browser` |
| Hlutar streyma og þurfa að passa nákvæmlega við tilkynnt bil; skrám yfir `max_upload_bytes` er hafnað þegar fyrirmæli eru gefin; samsett stærð sannreynd og tætt | OWASP ASVS 12.1 | `test_upload_flow_versions_and_queries` |
| Upphöl þurfa verkefnisaðgerðina `createDocument`; niðurhöl þurfa aðild; utanaðkomandi fá 404 | OWASP API1, API5 | `test_upload_cancelled_in_the_browser`, `test_selection_flow_with_filtering_and_browser_upload` |
| Svarmeginmál innihalda aðeins svið forskriftarinnar (engir geymslulyklar, engin tætigildi) | OWASP API3 | `validate_documents` í hverju Documents API-prófi |
| Útrunnar setur og hlutar hreinsuð með skrám sínum | Umhirða | `cleanup.py`, `test_graph_core::test_expired_nodes_are_deleted_in_batches` |

## Stjórnunarviðmót og reikningssíða (áfangi 6)

| Vörn | Staðall | Svíta |
|---|---|---|
| `/admin` þarf innskráðan stjórnanda; aðrir notendur fá HTML 404, nafnlausir vafrar eru sendir í innskráningu | OWASP API5, ASVS 4.1 | `test_admin_ui::test_admin_pages_need_the_admin_role` |
| Hvert POST stjórnunar þarf undirritaðan tóka bundinn við setu stjórnandans og hlutinn, og vafrabeiðni frá sama uppruna | CSRF, OWASP ASVS 4.2.2 | `test_admin_ui::test_csrf_protections_on_admin_forms` |
| Endurstilling lykilorða, breyting stjórnandamerkis, skipti biðlaraleyndarmála og eyðing þurfa eigið lykilorð stjórnandans aftur | OWASP ASVS 2.2.5 | `test_user_management`, `test_project_management_reaches_the_bcf_api`, `test_client_management_and_secret_rotation` |
| Stjórnendur geta ekki gert eigin reikning óvirkan, lækkað hann eða eytt | Varnir gegn útilokun | `test_user_management` |
| Mynduð lykilorð og biðlaraleyndarmál sýnd einu sinni; endurstilltum lykilorðum þarf að breyta við næstu innskráningu; að gera óvirkan afturkallar tóka | OWASP ASVS 2.1, 2.5 | `test_user_management`, `test_client_management_and_secret_rotation`, `test_forced_password_change` |
| Hver stjórnunaraðgerð skráð í endurskoðunarskrána án leyndarmála | OWASP ASVS 7.1 | `test_sessions_audit_and_settings_pages` |
| Stillingasíðan sýnir aldrei leyndarmál | OWASP ASVS 14.3 | `test_sessions_audit_and_settings_pages` |
| Síðurnar bera stranga CSP, engan innfelldan kóða; viðbótarskrifturnar byggja DOM aðeins með `textContent` | OWASP ASVS 14.4 | `test_admin_pages_need_the_admin_role`, `tests/ui` (engar stjórnborðsvillur) |
| Aðgengi: engin alvarleg eða krítísk axe-core-brot á nokkurri stjórnunarsíðu | WCAG 2.2 AA | `tests/ui/test_admin_browser.py` |

## IFC-graf (áfangi 9)

| Vörn | Staðall | Svíta |
|---|---|---|
| IFC-þáttun keyrir í sérstöku vinnuferli með tímamörkum, minnismörkum (POSIX) og einingahámarki; hrun eða frysting fellir líkanið, ekki þjóninn | OWASP ASVS 12.4 | `test_ifcgraph_convert::test_geometry_can_be_included_and_limits_are_enforced`, `test_ifcgraph` |
| `.ifczip` er aðeins pakkað upp þegar hún geymir nákvæmlega eina `.ifc`, með stærðarþaki upphalsins á útpökkuðu bætin | Zip-sprengja | `service._prepare_input` |
| Samanburðurinn og taplausa umbreytingin lesa skrár með eigin lesara: hann hafnar því sem hann getur ekki lesið, mynstur hans geta ekki bakkað, og hreiðrun er takmörkuð | OWASP ASVS 5.1 | `test_ifcgraph_step` |
| Merkimiðar og venslagerðir úr umbreytinum eru sannreynd sem auðkenni áður en þau ná Cypher; allt annað er stiki | OWASP API8 | `importer._safe`, `test_ifcgraph` |
| Upphlaðin IFC-skrá er prófuð gagnvart IFC-skemanu og, þar sem þær eru settar upp, ifc-gherkin-rules frá buildingSMART í sams konar vinnsluferli, með sömu mörkum, og prófunin heldur henni aldrei aftur; skýrslan er aðeins lesin í gegnum aðild að verkefninu, og atvikaskráin fær fjölda athugasemda, aldrei skilaboð þeirra | OWASP ASVS 12.4, ASVS 7.1 | `test_ifc_validation`, `test_ifcgraph_service` |
| Umhverfi reglna buildingSMART er aðeins búið til úr niðurhölum sem eru fest með SHA-256 og pökkum sem eru settir upp með tætigildum sínum, og safnfærslu sem myndi lenda utan möppu sinnar er hafnað; í myndinni á root það, og reglurnar keyra án stillinga og leyndarmála þjónsins | OWASP ASVS 14.2, ASVS 10.3 | `test_ifcgraph_gherkin` |
| Umbreytingarbilanir skráðar á `IfcModel`-hnútinn og í atvikaskrá án innihalds skrárinnar | OWASP ASVS 7.1 | `test_ifcgraph` |

## Uppsetning og öryggisafrit (áfangi 8)

| Vörn | Svíta |
|---|---|
| Gámurinn keyrir sem ekki-root á skrifvörðu rótarskráakerfi með afnumdum capabilities; gagnagrunnur aðeins á einkanetinu | `Dockerfile`, `compose.prod.yaml`; Trivy-myndskönnun í `release.yml` og `security-nightly.yml` |
| Öryggisafrit og endurheimt fram og aftur heldur hnútum, venslum og skrám, á Neo4j og Memgraph | `test_backup` |
| Nætur-ZAP-baseline gegn keyrandi þjóni | `security-nightly.yml`, `.zap/rules.tsv` |

## Vettvangur (áfangi 0–1, samningsfuzz áfangi 11)

| Vörn | Svíta |
|---|---|
| Öryggishausar á hverju svari, villur meðtaldar | `test_headers_and_errors` |
| Heimildar-, val- og upphalssíðurnar bæta uppruna biðlarans við `form-action`, því Chromium athugar hann gegn áframsendingunni sem svarar eyðublaðinu; hver önnur síða heldur `form-action 'self'` | `test_security_oauth2::test_the_authorization_page_lets_the_browser_follow_the_redirect_to_the_client`, `tests/ui/test_popup_opener.py::test_the_sign_in_popup_comes_back_to_the_client` |
| `Cross-Origin-Opener-Policy: same-origin` aðeins á stjórnunar- og reikningssíðunum; síðurnar sem biðlari opnar í sprettiglugga halda sjálfgefnu vafrans svo callback-síða biðlarans nái opener sínum (sannreynt í raunverulegum vafra) | `test_headers_and_errors::test_opener_policy_isolates_only_the_administration`, `tests/ui/test_popup_opener.py` |
| Athugun vafrans á forskrift service worker, á hvaða vistfangi sem er, er svarað með forskrift sem fjarlægir workerinn, tæmir skyndiminnin og endurhleður gluggana, því annars svarar worker sem annað forrit hefur skilið eftir á vistfangi þjónsins með gömlum afritum af síðunum; þjónninn hefur engan eigin worker. Þetta lagar óhapp og er ekki öryggisvörn | `test_foreign_workers` |
| Tungumálavefkakan geymir aðeins kóða úr föstum lista sjö tungumála og er `HttpOnly` og `SameSite=Lax`; engin skrifta les hana | `test_headers_and_errors::test_the_language_cookie_holds_only_a_known_language` |
| Aðeins villumeginmál forskriftarinnar; engar staflarakningar eða endurómað inntak | `test_headers_and_errors`, `errors.py` |
| Stærðarmörk meginmáls beiðni fyrir þáttun | `test_headers_and_errors::test_oversized_body_is_rejected_before_parsing` |
| Request-id hreinsað | `test_headers_and_errors::test_request_id_is_echoed_or_minted` |
| CORS án credentials, aðeins á API-slóðunum; síðum er aldrei deilt cross-origin | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials`, `::test_pages_are_never_shared_cross_origin` |
| CORS leyfir og sýnir `Content-Disposition`, svo vafrabiðlarar geti hlaðið upp og niður tvíundarskrám (Foundation API 1.9) | `test_headers_and_errors::test_cors_allows_and_exposes_content_disposition` |
| Ómeðhöndlaðar villur verða 500 forskriftarinnar innan CORS- og öryggishausalaganna, svo vafrabiðlarar sjái stöðuna, ekki netvillu | `test_headers_and_errors::test_unhandled_errors_keep_cors_and_security_headers` |
| Tíðnitakmarkaðir endapunktar gefa slowapi Response fyrir hausa þess (með mörk virk féll endapunktur sem skilaði dict) | `test_rate_limit_endpoints`, `test_bcf_links_documents::test_upload_works_with_rate_limits_enabled` |
| Beiðnaskrá (valkvæð): aðferð, slóð án fyrirspurnarstrengs, aðgerð, staða, tímalengd, request-id, bætafjöldi og sá sem kallaði; aldrei meginmál, hausar eða tókar; færslur renna út; aðeins læsileg stjórnendum (seta á síðunni, bearer með heimildinni `admin` á `/admin/api/requests`) | `test_requestlog::test_requests_are_logged_without_bodies_and_served_to_administrators` |
| Graffyrirspurn (valkvæð): lesandi Cypher fyrir stjórnendur með heimildinni `admin`; skrifandi setningarliðum og öðrum stefjum en skemastefjum hafnað fyrir gagnagrunninn, vernduðum eiginleikum hafnað og haldið utan svara, tætigildi hulin, raða- og tímamörk, hvert kall endurskoðað; ekki tengt nema virkjað | `test_graph_query::test_the_fences_hold`, `test_graph_query (unit)`, `test_capabilities::test_the_graph_query_is_announced_with_its_limits_when_on` |
| Gagnvirka API-skjölunin (Swagger UI þriðja aðila frá CDN) hefur eigin stefnu og er óvirk í framleiðslu sjálfgefið | `test_headers_and_errors::test_api_docs_have_their_own_policy_and_are_off_in_production` |
| Framleiðsla neitar að ræsa án https, lykilorðs gagnagrunns og leynilykils | `test_settings` |
| Geymslulyklar byggðir aðeins úr UUID; path traversal ómöguleg | `test_core_helpers::test_storage_keys_cannot_escape` |
| Streymandi skrif telja bæti og framfylgja mörkum | `test_core_helpers::test_storage_stream_counts_bytes` |
| Cypher er áfram stikað og flytjanlegt | `test_core_helpers::test_dialect_ddl_and_cypher_lint`, Memgraph-samningskeyrsla |
| Útrunnum leyndarmálum eytt á tímamæli | `test_graph_core::test_expired_nodes_are_deleted_in_batches` |
| Klukkan borin saman við NTP í `opencde doctor` og á stillingasíðunni (gildistímar ráðast af henni) | `test_doctor` |
| Cooldown ósjálfstæða og festar actions | `.github/workflows/ci.yml`, `pyproject.toml` |
| Hver skjalfest aðgerð lifir af myndað gilt og ógilt inntak: ekkert 5xx, svör passa við OpenAPI-skemu, ógilt inntak fær 4xx | `tests/e2e/test_schemathesis.py` (Schemathesis; `OPENCDE_SCHEMATHESIS_EXAMPLES` fyrir löngu næturkeyrsluna) |
