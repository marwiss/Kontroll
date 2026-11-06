# Turvallisuuskontrollit ja ne todistavat testit

Jokaisella kontrollilla on vähintään yksi automaattitesti. "Sarja" nimeää
testimoduulin.

## Foundation API ja OAuth2 (vaihe 2)

| Kontrolli | Standardi | Sarja |
|---|---|---|
| PKCE `S256` vaaditaan jokaiselta asiakkaalta paitsi merkityltä (seuraava rivi); `plain` ja puuttuva challenge hylätään | RFC 7636, OAuth 2.1 | `test_security_oauth2::test_pkce_is_mandatory_and_plain_is_refused` |
| Luottamuksellinen asiakas, jonka ylläpitäjä on merkinnyt, saa jättää PKCE:n pois, kuten BCF API 2.1 tekee: sen silti lähettämä challenge pannaan täytäntöön, verifier ilman challengea hylätään, julkista asiakasta ei voi merkitä, ja pyynnössä nimetty redirect-URI on nimettävä uudelleen | RFC 9700 §2.1.1, RFC 6749 §4.1.3 | `test_oauth2_without_pkce` |
| Redirect-URIn tarkka vastaavuus; loopback-portti saa vaihdella; rekisteröimätön URI näytetään, sitä ei koskaan seurata | RFC 9700 §4.1, RFC 8252 §7.3 | `test_security_oauth2::test_unregistered_redirect_uri_is_shown_not_followed`, `::test_loopback_port_may_vary_but_host_may_not` |
| `state` vaaditaan; tuntematon scope ja tukematon vastaustyyppi ohjataan virheinä `state`-parametrin kanssa | RFC 6749 §4.1.2.1 | `test_security_oauth2::test_state_is_required_and_unknown_scope_is_refused` |
| `iss` valtuutusvastauksessa | RFC 9207 | `test_oauth2::test_public_client_flow_with_pkce` |
| Kertakäyttöiset koodit (60 s); toisto peruu ensimmäisen lunastuksen tokenit | RFC 9700 §4.5 | `test_oauth2::test_code_is_single_use_and_replay_revokes_tokens` |
| Koodi sidottu asiakkaaseen, redirect-URIin ja verifieriin | RFC 6749 §4.1.3 | `test_security_oauth2::test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Opaakit tokenit tallennettu vain SHA-256-tiivisteinä | ADR 0002 | `test_graph_core` (skeema), koodikatselmointi |
| Refresh-tokenien kierto ja uudelleenkäytön tunnistus, joka peruu perheen | RFC 9700 §4.14 | `test_oauth2::test_refresh_rotates_and_reuse_revokes_the_family` |
| Refresh-token, jota ei ole käytetty kahteen viikkoon (`refresh_token_idle_seconds`), lakkaa toimimasta ja vie perheensä mukanaan, 30 päivän ehdottoman eliniän sisällä | RFC 9700 §4.14 | `test_oauth2::test_a_refresh_token_left_unused_stops_working` |
| Asiakkaan todennus: Basic tai lomake; julkiset asiakkaat eivät koskaan esitä salaisuutta; 401 ja `WWW-Authenticate` | RFC 6749 §2.3 | `test_security_oauth2::test_client_authentication_failures` |
| Tokenvastaukset `Cache-Control: no-store`, `Pragma: no-cache`, tila 201 | RFC 6749 §5.1, Foundation API | `test_oauth2::test_token_response_is_never_cached_and_has_spec_fields` |
| Access-tokenien ja kokonaisten refresh-perheiden peruutus | RFC 7009 | `test_oauth2::test_revocation` |
| Suostumuksen voi evätä (`access_denied`) | RFC 6749 §4.1.2.1 | `test_oauth2::test_deny_redirects_with_access_denied` |
| Allekirjoitetut, vanhenevat, käyttötarkoitukseen sidotut lomaketokenit; peukalointi hylätään | CSRF | `test_security_oauth2::test_tampered_or_replayed_form_token_is_refused`, `test_auth_primitives` |
| Kirjautuminen nopeusrajoitettu osoitetta kohti | OWASP ASVS 2.2.1 | `test_security_oauth2::test_sign_in_is_rate_limited` |
| Epäonnistuneet kirjautumiset saavat käyttäjätunnuksen odottamaan: viiden peräkkäisen jälkeen odotus, joka kaksinkertaistuu 30 sekunnista 15 minuuttiin, osoitekohtaisen rajan lisäksi. Tuntemattomat nimet lasketaan samoin, joten vastaus ei kerro, mitkä tilit ovat olemassa, ja nimet tallennetaan tiivisteinä | OWASP ASVS 6.3 | `test_sign_in_throttle` |
| Osoitekohtainen raja jokaiselle pyynnölle (600 minuutissa, `OPENCDE_RATE_LIMIT_API`), hallinnassa tiukempi (240 minuutissa); terveystarkistukset ja staattiset tiedostot on vapautettu; jaetun tallennuksen vika ei pysäytä mitään | OWASP API4 | `test_rate_limits` |
| Yleinen virheilmoitus; käytöstä poistetut tilit eivät voi kirjautua ja menettävät tokeninsa | OWASP ASVS 2.2 | `test_security_oauth2::test_disabled_user_cannot_sign_in_and_loses_tokens` |
| Salasanat, koodit ja tokenit eivät koskaan esiinny lokeissa | OWASP ASVS 7.1 | `test_security_oauth2::test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Argon2id-salasanatiivistys; käytäntö (pituus, zxcvbn, ei käyttäjätunnusta) | OWASP ASVS 2.1 | `test_core_helpers::test_password_policy_and_hashing` |
| Dynaaminen rekisteröinti oletuksena pois päältä; vain https- tai loopback-uudelleenohjaukset; julkiset asiakkaat (RFC 7591 `token_endpoint_auth_method: "none"`) eivät saa salaisuutta ja niiden on käytettävä PKCE:tä kuten jokaisen asiakkaan; vain koodi- ja refresh-grantit voidaan rekisteröidä | Foundation API 2.2.3, RFC 7591 | `test_oauth2::test_dynamic_registration_when_enabled`, `::test_registration_is_404_when_disabled` |
| Itse rekisteröityneet asiakkaat, jotka eivät myönnä tokenia `dynamic_client_unused_days`-päivään, poistetaan tokeneineen (siivooja ja `opencde client prune`); manuaaliset asiakkaat eivät koskaan vanhene | Tietojen minimointi | `test_maintenance::test_unused_self_registered_clients_expire_and_can_be_pruned`, `test_oauth2::test_dynamic_registration_when_enabled` |
| Rekisteröintiä voi rajoittaa lisää: `dynamic_client_registration_token` vaatii alustavan pääsytunnisteen (RFC 7591 §3), ja `dynamic_client_approval` pitää itse rekisteröityneen asiakkaan pois käytöstä, kunnes järjestelmänvalvoja hyväksyy sen | RFC 7591 §3 | `test_registration_controls` |
| Vain Bearer rajapinnassa; HTTP Basic hylätään | Foundation API 2.2.1 | `test_foundation::test_current_user_requires_a_bearer_token` |
| Sivut: tiukka CSP, ei inline-koodia, ei kehystystä, ei välimuistia | OWASP ASVS 14.4 | `test_foundation::test_authorize_without_client_shows_an_error_page_and_never_redirects` |

## BCF API (vaihe 3)

| Kontrolli | Standardi | Sarja |
|---|---|---|
| Projektit ja asiat tavoitetaan käyttäjäsolmusta `MEMBER_OF`-suhteen kautta; ei-jäsenet saavat 404, eivät koskaan 403 (ei olemassaolovuotoa) | OWASP API1 (BOLA) | `test_bcf_projects_topics::test_projects_and_extensions`, `::test_topic_authorization_matrix` |
| Rooli × toiminto -matriisi pakotetaan palvelinpuolella luonnille, päivitykselle ja poistolle; `authorization`-objektit kertovat totuuden | OWASP API5, BCF 1.2 | `test_bcf_projects_topics::test_topic_authorization_matrix`, `::test_project_rename_needs_manager` |
| Asioiden arvot validoidaan projektin extensions-listoja vasten; rajatut pituudet; tuntemattomat kentät ohitetaan | Foundation API 1.8, BCF 3.1.4 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| OData: kenttien sallittujen lista, parametrisoitu Cypher, rajatut `$top`/`$skip`, 400 tuntemattomista kentistä tai lajittelukelvottomista sarakkeista | OWASP API8 (injektio) | `test_odata`, `test_bcf_projects_topics::test_topic_odata_filtering_sorting_and_paging` |
| Asiakkaan valitsemien guidien on oltava UUID:itä ja ne normalisoidaan; päällekkäisyydet antavat 409 | Foundation API 1.5.1 | `test_bcf_projects_topics::test_topic_values_are_checked_against_extensions_and_guid_conflicts` |
| Tapahtuma-arvot leikataan (otsikot 128, tekstit 1024 merkkiä) | Tietojen minimointi | `events.py`, `test_topic_lifecycle_with_events` |

## BCF API: kommentit, viewpointit, tiedostot ja asiakirjat (vaihe 4)

| Kontrolli | Standardi | Sarja |
|---|---|---|
| Tilannekuva- ja bittikarttadatan on oltava ilmoitettua kuvatyyppiä (magic bytes) ja alle `max_image_bytes`; tarkistetaan ennen kuin mitään tallennetaan | OWASP ASVS 12.1, 12.2 | `test_bcf_helpers::test_decode_image_rejects`, `test_bcf_comments_viewpoints::test_viewpoint_rules_and_image_checks` |
| Binäärilähetykset (asiakirjat, snippetit) suoratoistetaan tallennustilaan palvelimen tekemillä avaimilla ja lasketaan `max_upload_bytes`-rajaa vasten; ilmoitettuihin kokoihin ei luoteta | OWASP ASVS 12.1 | `test_bcf_links_documents::test_documents_and_files_information`, `test_core_helpers::test_storage_stream_counts_bytes` |
| Vain kaksi binäärireittiä on vapautettu JSON-rungon rajasta; chunked-rungot lasketaan saapuessaan | OWASP API4 | `test_headers_and_errors::test_chunked_body_over_the_limit_is_cut_off` |
| Lataukset ovat liitteitä puhdistetuin, RFC 8187 -koodatuin tiedostonimin, `application/octet-stream` asiakirjoille, `nosniff`; lähetettyä sisältöä ei koskaan renderöidä | OWASP ASVS 12.5 | `test_bcf_helpers::test_filename_from_content_disposition`, `test_documents_and_files_information` |
| Asiakkaan tiedostonimet eivät koskaan päädy polkuun; tallennusavaimet ovat UUID:itä | OWASP ASVS 12.3 | `test_bcf_helpers::test_filename_from_content_disposition`, `storage.py` |
| Kommentit ja viewpointit tavoitetaan ketjulla käyttäjä → projekti → asia; ulkopuoliset saavat 404; roolimatriisi luonnille/päivitykselle/poistolle; 409 hiljaisen tietohävikin sijaan, kun viitattu viewpoint poistetaan | OWASP API1, API5 | `test_viewpoint_lifecycle`, `test_comment_lifecycle_and_events` |
| Asiakirjaviittaukset hyväksyvät vain http(s)-URLeja, ja niiden on osoitettava saman projektin asiakirjaan | OWASP ASVS 5.1 | `test_document_references`, `test_bcf_helpers::test_component_comment_and_reference_rules` |
| Liittyvien asioiden on kuuluttava samaan projektiin | OWASP API1 | `test_related_topics_and_files` |
| Numeeriset syötteet ovat äärellisiä (ei NaN:ia tai äärettömyyttä), listat ja merkkijonot rajattuja | OWASP ASVS 5.1 | `test_bcf_helpers::test_viewpoint_rules`, `schemas.py` |

## Documents API ja selainkirjautuminen (vaihe 5)

| Kontrolli | Standardi | Sarja |
|---|---|---|
| Käyttöliittymälinkit kantavat 256-bittistä tokenia, joka tallennetaan vain tiivisteenä ja on voimassa `documents_session_ttl_seconds`; rajapinnan puolen URLit käyttävät erillistä julkista tunnusta ja vaativat bearer-tokenin | OWASP ASVS 3.2 | `test_documents_api::test_upload_flow_versions_and_queries` |
| Selaimen on oltava kirjautunut kulun aloittaneena käyttäjänä; muut käyttäjät saavat 403, anonyymit selaimet lähetetään kirjautumaan | OWASP API1 | `test_documents_api` (lähetys- ja valintakulut) |
| Istuntoeväste: satunnainen, tiivistetty, `HttpOnly`, `SameSite=Strict`, `Secure` https:n yli, joutoajan ja absoluuttinen vanheneminen, poistetaan uloskirjautuessa | OWASP ASVS 3.3, 3.4 | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Istuntoon sidotut allekirjoitetut lomaketokenit jokaisessa sivun POSTissa; myös `Sec-Fetch-Site`/`Origin` tarkistetaan | CSRF, OWASP ASVS 4.2.2 | `test_web_signin::test_cross_site_posts_are_refused_and_next_cannot_leave_the_site`, `test_documents_api` |
| `next` kirjautumisen jälkeen on vain paikallinen polku (ei avointa uudelleenohjausta) | OWASP ASVS 5.1.5 | `test_documents_helpers::test_safe_next_only_accepts_local_paths` |
| Callback-URLit ovat vain http(s), eikä palvelin koskaan hae niitä; selain ohjataan URL-koodatuin parametrein | SSRF, OWASP ASVS 12.6 | `test_documents_helpers::test_callback_and_extensions_rules`, `test_upload_cancelled_in_the_browser` |
| Osat suoratoistetaan, ja niiden on vastattava ilmoitettua aluetta täsmälleen; `max_upload_bytes`-rajan ylittävät tiedostot hylätään ohjeen yhteydessä; koottu koko tarkistetaan ja tiivistetään | OWASP ASVS 12.1 | `test_upload_flow_versions_and_queries` |
| Lähetykset vaativat projektitoiminnon `createDocument`; lataukset vaativat jäsenyyden; ulkopuoliset saavat 404 | OWASP API1, API5 | `test_upload_cancelled_in_the_browser`, `test_selection_flow_with_filtering_and_browser_upload` |
| Vastausrungot sisältävät vain spesifikaation kentät (ei tallennusavaimia, ei tiivisteitä) | OWASP API3 | `validate_documents` jokaisessa Documents API -testissä |
| Vanhentuneet istunnot ja osat siivotaan tiedostoineen | Ylläpito | `cleanup.py`, `test_graph_core::test_expired_nodes_are_deleted_in_batches` |

## Hallintakäyttöliittymä ja tilisivu (vaihe 6)

| Kontrolli | Standardi | Sarja |
|---|---|---|
| `/admin` vaatii kirjautuneen järjestelmänvalvojan; muut käyttäjät saavat HTML 404:n, anonyymit selaimet lähetetään kirjautumaan | OWASP API5, ASVS 4.1 | `test_admin_ui::test_admin_pages_need_the_admin_role` |
| Jokainen hallinnan POST vaatii allekirjoitetun tokenin, joka on sidottu järjestelmänvalvojan istuntoon ja kohteeseen, sekä saman originin selainpyynnön | CSRF, OWASP ASVS 4.2.2 | `test_admin_ui::test_csrf_protections_on_admin_forms` |
| Salasanojen nollaus, hallintamerkinnän muuttaminen, asiakassalaisuuksien kierrätys ja poistaminen vaativat järjestelmänvalvojan oman salasanan uudelleen | OWASP ASVS 2.2.5 | `test_user_management`, `test_project_management_reaches_the_bcf_api`, `test_client_management_and_secret_rotation` |
| Järjestelmänvalvojat eivät voi poistaa käytöstä, alentaa tai poistaa omaa tiliään | Lukituksen esto | `test_user_management` |
| Luodut salasanat ja asiakassalaisuudet näytetään kerran; nollatut salasanat on vaihdettava seuraavassa kirjautumisessa; käytöstä poisto peruu tokenit | OWASP ASVS 2.1, 2.5 | `test_user_management`, `test_client_management_and_secret_rotation`, `test_forced_password_change` |
| Jokainen hallintatoiminto kirjataan tapahtumalokiin ilman salaisuuksia | OWASP ASVS 7.1 | `test_sessions_audit_and_settings_pages` |
| Asetussivu ei koskaan näytä salaisuuksia | OWASP ASVS 14.3 | `test_sessions_audit_and_settings_pages` |
| Sivut kantavat tiukan CSP:n, ei inline-koodia; parannusskriptit rakentavat DOMin vain `textContent`-kutsuilla | OWASP ASVS 14.4 | `test_admin_pages_need_the_admin_role`, `tests/ui` (ei konsolivirheitä) |
| Saavutettavuus: ei vakavia tai kriittisiä axe-core-rikkomuksia millään hallintasivulla | WCAG 2.2 AA | `tests/ui/test_admin_browser.py` |

## IFC-graafi (vaihe 9)

| Kontrolli | Standardi | Sarja |
|---|---|---|
| IFC-jäsennys ajetaan erillisessä työprosessissa aikarajalla, muistirajalla (POSIX) ja entiteettiylärajalla; kaatuminen tai jumiutuminen kaataa mallin, ei palvelinta | OWASP ASVS 12.4 | `test_ifcgraph_convert::test_geometry_can_be_included_and_limits_are_enforced`, `test_ifcgraph` |
| `.ifczip` puretaan vain, kun se sisältää tasan yhden `.ifc`-tiedoston, ja purettuihin tavuihin sovelletaan lähetyksen kokorajaa | Zip-pommi | `service._prepare_input` |
| Muuntimen nimiöt ja suhdetyypit validoidaan tunnisteina ennen kuin ne saavuttavat Cypherin; kaikki muu on parametri | OWASP API8 | `importer._safe`, `test_ifcgraph` |
| Muunnosvirheet kirjataan `IfcModel`-solmuun ja lokiin ilman tiedoston sisältöä | OWASP ASVS 7.1 | `test_ifcgraph` |

## Asennus ja varmuuskopiot (vaihe 8)

| Kontrolli | Sarja |
|---|---|
| Kontti käy ei-root-käyttäjänä vain luku -juuritiedostojärjestelmässä ilman capabilities-oikeuksia; tietokanta vain yksityisessä verkossa | `Dockerfile`, `compose.prod.yaml`; Trivy-kuvaskannaus `release.yml`- ja `security-nightly.yml`-työnkuluissa |
| Varmuuskopiointi ja palautus edestakaisin säilyttää solmut, suhteet ja tiedostot Neo4j:llä ja Memgraphilla | `test_backup` |
| Yöllinen ZAP-baseline käynnissä olevaa palvelinta vasten | `security-nightly.yml`, `.zap/rules.tsv` |

## Alusta (vaiheet 0–1, sopimusfuzzaus vaihe 11)

| Kontrolli | Sarja |
|---|---|
| Turvaotsakkeet jokaisessa vastauksessa, virheet mukaan lukien | `test_headers_and_errors` |
| Valtuutus-, valinta- ja lähetyssivut lisäävät asiakkaan originin `form-action`-käytäntöön, koska Chromium tarkistaa sen lomakkeeseen vastaavaa uudelleenohjausta vasten; jokainen muu sivu säilyttää `form-action 'self'` | `test_security_oauth2::test_the_authorization_page_lets_the_browser_follow_the_redirect_to_the_client`, `tests/ui/test_popup_opener.py::test_the_sign_in_popup_comes_back_to_the_client` |
| `Cross-Origin-Opener-Policy: same-origin` vain hallinta- ja tilisivuilla; sivut, jotka asiakas avaa ponnahdusikkunaan, säilyttävät selaimen oletuksen, jotta asiakkaan callback-sivu tavoittaa openerinsa (todennettu oikealla selaimella) | `test_headers_and_errors::test_opener_policy_isolates_only_the_administration`, `tests/ui/test_popup_opener.py` |
| Selaimen tarkistukseen service workerin komentosarjasta, missä tahansa osoitteessa, vastataan komentosarjalla, joka poistaa workerin, tyhjentää välimuistit ja lataa ikkunat uudelleen, koska toisen sovelluksen palvelimen osoitteeseen jättämä worker muuten vastaa sivujen vanhoilla kopioilla; palvelimella ei ole omaa workeria. Tämä korjaa vahingon eikä ole turvallisuuskontrolli | `test_foreign_workers` |
| Kielieväste sisältää vain koodin seitsemän kielen kiinteästä luettelosta ja on `HttpOnly` ja `SameSite=Lax`; mikään skripti ei lue sitä | `test_headers_and_errors::test_the_language_cookie_holds_only_a_known_language` |
| Vain spesifikaation virherunko; ei pinojälkiä tai toistettua syötettä | `test_headers_and_errors`, `errors.py` |
| Pyynnön rungon kokoraja ennen jäsentämistä | `test_headers_and_errors::test_oversized_body_is_rejected_before_parsing` |
| Request-id puhdistetaan | `test_headers_and_errors::test_request_id_is_echoed_or_minted` |
| CORS ilman credentialseja, vain rajapintapoluilla; sivuja ei koskaan jaeta cross-origin | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials`, `::test_pages_are_never_shared_cross_origin` |
| CORS sallii ja paljastaa `Content-Disposition`-otsakkeen, jotta selainasiakkaat voivat lähettää ja ladata binäärejä (Foundation API 1.9) | `test_headers_and_errors::test_cors_allows_and_exposes_content_disposition` |
| Käsittelemättömistä virheistä tulee spesifikaation 500 CORS- ja turvaotsakekerrosten sisällä, jotta selainasiakkaat näkevät tilan, eivät verkkovirhettä | `test_headers_and_errors::test_unhandled_errors_keep_cors_and_security_headers` |
| Nopeusrajoitetut päätepisteet antavat slowapille Response-olion sen otsakkeita varten (rajojen ollessa päällä dictin palauttava päätepiste epäonnistui) | `test_rate_limit_endpoints`, `test_bcf_links_documents::test_upload_works_with_rate_limits_enabled` |
| Pyyntöloki (valinnainen): metodi, polku ilman kyselymerkkijonoa, operaatio, tila, kesto, request-id, tavumäärät ja kutsuja; ei koskaan runkoja, otsakkeita tai tokeneita; merkinnät vanhenevat; luettavissa vain järjestelmänvalvojille (istunto sivulla, bearer `admin`-scopella osoitteessa `/admin/api/requests`) | `test_requestlog::test_requests_are_logged_without_bodies_and_served_to_administrators` |
| Graafikysely (valinnainen): lukeva Cypher järjestelmänvalvojille, joilla on `admin`-scope; kirjoittavat lausekkeet ja muut kuin skeemaproseduurit hylätään ennen tietokantaa, suojatut ominaisuudet hylätään ja pidetään poissa vastauksista, tiivisteet peitetään, rivi- ja aikarajat, jokainen kutsu kirjataan tapahtumalokiin; ei liitetä, ellei kytketty päälle | `test_graph_query::test_the_fences_hold`, `test_graph_query (unit)`, `test_capabilities::test_the_graph_query_is_announced_with_its_limits_when_on` |
| Interaktiivisella rajapintadokumentaatiolla (kolmannen osapuolen Swagger UI CDN:stä) on oma käytäntönsä, ja se on tuotannossa oletuksena pois päältä | `test_headers_and_errors::test_api_docs_have_their_own_policy_and_are_off_in_production` |
| Tuotanto kieltäytyy käynnistymästä ilman https:ää, tietokannan salasanaa ja salaista avainta | `test_settings` |
| Tallennusavaimet rakennetaan vain UUID:istä; path traversal mahdoton | `test_core_helpers::test_storage_keys_cannot_escape` |
| Suoratoistokirjoitukset laskevat tavut ja pakottavat rajat | `test_core_helpers::test_storage_stream_counts_bytes` |
| Cypher pysyy parametrisoituna ja siirrettävänä | `test_core_helpers::test_dialect_ddl_and_cypher_lint`, Memgraph-sopimusajo |
| Vanhentuneet salaisuudet poistetaan ajastimella | `test_graph_core::test_expired_nodes_are_deleted_in_batches` |
| Kelloa verrataan NTP:hen `opencde doctor`-komennossa ja asetussivulla (vanhenemisajat riippuvat siitä) | `test_doctor` |
| Riippuvuuksien cooldown ja kiinnitetyt actionit | `.github/workflows/ci.yml`, `pyproject.toml` |
| Jokainen dokumentoitu operaatio selviää generoidusta kelvollisesta ja virheellisestä syötteestä: ei 5xx:ää, vastaukset vastaavat OpenAPI-skeemoja, virheellinen syöte saa 4xx:n | `tests/e2e/test_schemathesis.py` (Schemathesis; `OPENCDE_SCHEMATHESIS_EXAMPLES` pitkää yöajoa varten) |
