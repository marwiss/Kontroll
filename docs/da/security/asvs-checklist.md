# OWASP ASVS niveau 2-tjekliste

Selvevaluering mod OWASP Application Security Verification Standard 5.0 på
niveau 2, skrevet af udviklerne 2026-11-05. Det er ikke en ekstern
verifikation. Hvert kapitel lister de niveau 2-krav, der gælder for denne
server (omskrevet), status og beviserne: en kontrol i [controls.md](controls.md)
med sin test, et dokument eller kode. Kendte huller samles til sidst; de
følges som *Senere* i projektplanen.

Status: **opfyldt** (kontrol og test findes), **delvist** (kontrol findes med
en dokumenteret begrænsning), **ikke opfyldt** (planlagt eller overladt til
operatøren), **ikke relevant** (serveren har ingen sådan komponent).

## V1 Kodning og sanering

| Krav | Status | Bevis |
|---|---|---|
| Outputkodning for HTML; ingen DOM-injektion af serverdata | opfyldt | Jinja2 autoescape, forbedringsscripts bruger kun `textContent`, streng CSP som forsvar i dybden; `tests/ui` fejler ved konsolfejl |
| Databaseforespørgsler bygges aldrig af input | opfyldt | Kun Cypher-parametre, håndhævet af lint-testen `test_core_helpers::test_dialect_ddl_and_cypher_lint`; IFC-labels valideres som identifikatorer (`importer._safe`) |
| Forespørgselssprog eksponeret for klienter parses, interpoleres ikke | opfyldt | OData: parser → AST → felthvidliste → parametre, `test_odata` |
| Filnavne og headerværdier saneres og kodes | opfyldt | `sanitize_filename`, RFC 8187 `attachment_header`, `test_bcf_helpers` |
| URL'er fra klienter valideres (skema, vært) før brug | opfyldt | `validate_redirect_uri` (https, loopback, private skemaer), callbacks og dokumentreferencer kun http(s) |

## V2 Validering og forretningslogik

| Krav | Status | Bevis |
|---|---|---|
| Positiv validering med grænser på alt input | opfyldt | Pydantic v2-modeller med længde-, liste- og dybdegrænser, endelige tal; ukendte felter ignoreres jf. Foundation API 1.8 |
| Forretningsregler håndhæves på serversiden | opfyldt | Sagsværdier mod extensions, præcis ét kamera, 409 ved sletning af et refereret viewpoint, dublerede guid'er, én transaktion per skrivning |
| Anti-automatisering på autentificering og dyre operationer | delvist | Login- og token-endepunkter hastighedsbegrænset per adresse (`test_sign_in_is_rate_limited`), og mislykkede logins får brugernavnet til at vente (`test_sign_in_throttle`); uploads begrænset per fil (`max_upload_bytes`); ingen lagerkvote per bruger endnu |

## V3 Webfrontend-sikkerhed

| Krav | Status | Bevis |
|---|---|---|
| Content Security Policy uden `unsafe-inline`, indramning nægtet | opfyldt | `default-src 'none'` på API-svar, `default-src 'self'; frame-ancestors 'none'` på sider; ingen inline-scripts eller -stilarter; `X-Frame-Options: DENY` |
| Cookies `HttpOnly`, `Secure`, `SameSite=Strict` | delvist | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it`; cookien har endnu intet `__Host-`-præfiks |
| CSRF-beskyttelse ved hver tilstandsændring fra en browser | opfyldt | Signerede, formålsbundne formulartokens plus `Sec-Fetch-Site`/`Origin`-kontroller, `test_csrf_protections_on_admin_forms`, `test_cross_site_posts_are_refused_and_next_cannot_leave_the_site` |
| Browsersikkerhedsheadere på hvert svar | opfyldt | `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy: same-origin` på administrations- og kontosiderne (de sider, en klient åbner i et pop op-vindue, beholder browserens standard, så pop op-vinduet beholder sin opener), `test_headers_and_errors` |
| HSTS | opfyldt | Tilføjes af Caddy i produktionsoverlejringen (`Caddyfile`) |
| Ingen følsomme data i URL'er | delvist | Tokens og kodeord rejser kun i headere og kroppe; Documents API-specifikationen lægger en engangslinktoken i `upload_ui_url`/`select_documents_url`, så den er 256 bit, gemt hashet, gyldig 10 minutter, og siden kræver desuden en browsersession som samme bruger |

## V4 API og webservice

| Krav | Status | Bevis |
|---|---|---|
| JSON-API'er validerer indholdstyper og afviser ikke-understøttede metoder | opfyldt | FastAPI-parsing med specifikationens fejlkrop, 405 på andre metoder; Schemathesis `unsupported_method` i den natlige kørsel |
| CORS begrænset; aldrig credentials med wildcard | opfyldt | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials` |
| Konsistent fejlformat uden interne detaljer | opfyldt | Kun `{"message": …}`, `test_headers_and_errors` |
| Autentificering på hver API-operation; kun Bearer | opfyldt | `test_foundation::test_current_user_requires_a_bearer_token`, sikkerhedssuiten |
| Kontraktfuzzing: ingen 5xx, svarene matcher de dokumenterede skemaer, ugyldigt input afvises | opfyldt | `tests/e2e/test_schemathesis.py` (hver operation, positiv og negativ generering) |

## V5 Filhåndtering

| Krav | Status | Bevis |
|---|---|---|
| Størrelsesgrænser på de faktisk modtagne bytes | opfyldt | Streamende skrivninger tæller bytes; chunked-kroppe afskæres; `test_storage_stream_counts_bytes`, `test_chunked_body_over_the_limit_is_cut_off` |
| Filtype afgøres af indholdet, ikke af klienten | opfyldt | Magic bytes for billeder; dokumenter gemmes og serveres som `application/octet-stream` |
| Klientfilnavne når aldrig filsystemet | opfyldt | UUID-lagernøgler, `test_storage_keys_cannot_escape` |
| Uploadet indhold udføres eller renderes aldrig | opfyldt | Vedhæftninger med `nosniff`; ingen templates fra lageret |
| Arkivudpakning begrænset | opfyldt | `.ifczip` med præcis én `.ifc` og størrelsesloftet på udpakkede bytes |
| Parsing af ikke-betroede filer isoleret | opfyldt | IFC-konvertering i en arbejdsproces med tids-, hukommelses- og entitetsgrænser (`test_ifcgraph_convert`) |
| Antivirusscanning af uploadede filer | ikke opfyldt | Overladt til operatøren (scan lagervolumen); ingen scanner integreret |

## V6 Autentificering

| Krav | Status | Bevis |
|---|---|---|
| Politik for kodeordslængde og -styrke, ingen sammensætningsregler | opfyldt | `auth/passwords.py`: mindst 12 tegn og zxcvbn-score ≥ 3 med brugernavnet som kendt input, `test_password_policy_and_hashing` |
| Kontrol mod lister over lækkede kodeord | delvist | zxcvbn's ordbøger over almindelige kodeord; intet live-opslag mod læklister |
| Argon2id-hashing | opfyldt | `pwdlib` med Argon2id, `test_password_policy_and_hashing` |
| Brute-force-beskyttelse med generiske beskeder | opfyldt | Hastighedsgrænse per adresse, en voksende ventetid per brugernavn, konstant besked ved forkert bruger eller kodeord, deaktiverede konti afvises (`test_disabled_user_cannot_sign_in_and_loses_tokens`) |
| Multifaktorautentificering | ikke opfyldt | Kun kodeord; TOTP til loginsiden er planlagt (*Senere* i planen). API-klienter ser aldrig kodeord: de autentificerer sig gennem OAuth2 mod denne loginside, så én MFA dækker alt |
| Sikker gendannelse af legitimationsoplysninger | opfyldt | Ingen selvbetjeningsnulstilling; en administrator udsteder et engangskodeord efter genautentificering, og brugeren skal skifte det ved næste login |
| Genautentificering ved følsomme operationer | opfyldt | Eget kodeord kræves ved kodeordsskift, nulstillinger, ændring af adminflaget, hemmelighedsrotation og sletning (`test_user_management`, `test_client_management_and_secret_rotation`) |
| Deaktivering af en konto afslutter dens adgang | opfyldt | Tokens og sessioner tilbagekaldes, når en bruger deaktiveres |

## V7 Sessionshåndtering

| Krav | Status | Bevis |
|---|---|---|
| Serverside-sessioner med tilfældige identifikatorer, gemt hashet | opfyldt | `web/sessions.py`, 256-bit cookieværdi, SHA-256 i hvile |
| Ny session ved login; logout ødelægger den | opfyldt | `test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Inaktivitets- og absolutte timeouts | opfyldt | `web_session_idle_seconds` og absolut udløb, ryddet af oprydningen |
| Brugere kan se og afslutte deres sessioner og tildelinger | opfyldt | `/account`: sessioner, applikationer, "log ud overalt" |
| Administratorer kan afslutte enhver session eller tildeling | opfyldt | `/admin/sessions`, `opencde revoke` |

## V8 Autorisation

| Krav | Status | Bevis |
|---|---|---|
| Nægt som standard; kontroller på objektniveau ved hver adgang | opfyldt | Hver forespørgsel starter i brugernoden og går via `MEMBER_OF`; ikke-medlemmer får 404 (`test_topic_authorization_matrix`) |
| Kontroller på funktionsniveau per rolle, på serversiden | opfyldt | Rolle × handling-matrix for projekter, sager, kommentarer, viewpoints, dokumenter; `authorization`-objekter afledt af de samme regler |
| Administrative funktioner adskilt og beskyttet | opfyldt | `/admin` kræver adminrollen på hver rute (`test_admin_pages_need_the_admin_role`) |
| Autorisation afgøres i samme transaktion som ændringen | opfyldt | Repository-metoder kontrollerer og skriver i én transaktion |
| Eksponering på feltniveau begrænset | opfyldt | Eksplicitte svarmodeller; hashes og lagernøgler findes i intet svar (`validate_documents`, conformance-suiten) |

## V9 Selvstændige tokens

ikke relevant: tokens er opake referencer gemt som hashes (ADR 0002); der er
ingen JWT'er at validere.

## V10 OAuth og OIDC

| Krav | Status | Bevis |
|---|---|---|
| Kun authorization code med PKCE `S256`; ingen implicit- eller password-grants | opfyldt | `test_pkce_is_mandatory_and_plain_is_refused` |
| Nøjagtig matchning af redirect-URI; loopback-undtagelse jf. RFC 8252 | opfyldt | `test_unregistered_redirect_uri_is_shown_not_followed`, `test_loopback_port_may_vary_but_host_may_not` |
| `state` kræves; `iss` i svaret | opfyldt | `test_state_is_required_and_unknown_scope_is_refused`, `test_public_client_flow_with_pkce` |
| Engangskoder bundet til klient, redirect-URI og verifier | opfyldt | `test_code_is_single_use_and_replay_revokes_tokens`, `test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Rotation af refresh-tokens med registrering af genbrug | opfyldt | `test_refresh_rotates_and_reuse_revokes_the_family` |
| Tilbagekaldelse (RFC 7009) | opfyldt | `test_revocation` |
| Klientautentificering; offentlige klienter uden hemmeligheder | opfyldt | `test_client_authentication_failures` |
| Tokensvar kan ikke caches | opfyldt | `test_token_response_is_never_cached_and_has_spec_fields` |
| Samtykkeskærmen nævner klienten og omdirigeringsmålet; brugeren kan nægte | opfyldt | `test_deny_redirects_with_access_denied`, `auth/templates` |
| Dynamisk registrering begrænset | opfyldt | Slået fra som standard; kun https- eller loopback-omdirigeringer, når slået til; offentlige registreringer (RFC 7591 `none`) hviler på PKCE og på, at samtykkesiden nævner klienten og dens omdirigeringsvært; hastighedsbegrænset |
| Afsenderbundne tokens (DPoP, mTLS) | ikke opfyldt | Niveau 3-punkt; listet under *Senere* i planen |
| Overholdelse testet med et eksternt værktøj | ikke opfyldt | OAuch-kørsel beskrevet i [pentest-howto.md](pentest-howto.md) §4, skal gøres før den første produktionsudrulning |

## V11 Kryptografi

| Krav | Status | Bevis |
|---|---|---|
| Godkendte algoritmer og CSPRNG | opfyldt | `secrets` til koder, tokens, cookies og klienthemmeligheder; Argon2id; SHA-256 til tokenhashes; HMAC-signerede formulartokens (`itsdangerous`) |
| Hemmeligheder ikke i kode eller images | opfyldt | `OPENCDE_SECRET_KEY` og databasekodeordet fra miljøet eller Docker secrets, genereret af `opencde init`; `.env` ignoreres af git; gitleaks i CI |
| Nøglerotation | delvist | Rotation af `OPENCDE_SECRET_KEY` ugyldiggør formulartokens og browsersessioner, intet andet; dokumenteret som et operatørtrin i `docs/da/deploy/vps-caddy.md`; ingen overgang med dobbelt nøgle |

## V12 Sikker kommunikation

| Krav | Status | Bevis |
|---|---|---|
| Kun TLS 1.2 eller 1.3, gyldige certifikater, HSTS | opfyldt | Caddy i `compose.prod.yaml`; produktion nægter en offentlig http-URL (`test_settings`); testssl.sh-kørsel i [pentest-howto.md](pentest-howto.md) §5 før produktion |
| Interne forbindelser beskyttet | opfyldt | Databasen kun på det private compose-netværk; `neo4j+s://` til en ekstern database (`docs/da/deploy/cloud-aura.md`) |
| Videresendte headere stoles kun på fra kendte proxyer | opfyldt | `OPENCDE_TRUSTED_PROXIES` |

## V13 Konfiguration

| Krav | Status | Bevis |
|---|---|---|
| Sikre standardværdier; serveren nægter usikre produktionsindstillinger | opfyldt | `test_settings`: https, databasekodeord og hemmelig nøgle kræves i produktion, localhost-omdirigeringer afvises |
| Afhængigheder fastgjort, auditeret og opdateret | opfyldt | `uv.lock`, pip-audit, Dependabot med 7 dages cooldown, actions fastgjort med SHA og kontrolleret af zizmor |
| Hærdet container | opfyldt | Ikke-root, skrivebeskyttet rodfilsystem, fjernede capabilities, `no-new-privileges`, Trivy-scan med SBOM ved release |
| Driftskontroller | opfyldt | `opencde doctor` (database, skema, ur, offentlig URL, headere, lager) |
| Administrationsgrænsefladen kan isoleres | opfyldt | Separat login og rolle; `OPENCDE_ADMIN_UI_ENABLED=false` fjerner den fra en offentlig instans (administrér via CLI i stedet), eller begræns `/admin` til interne adresser i proxyen |
| Ingen tredjepartskode på produktionssider | opfyldt | Serverens sider indlæser intet fra andre origins; den interaktive API-dokumentation (`/docs`, Swagger UI fra et CDN) serveres kun uden for produktion, medmindre `OPENCDE_API_DOCS_ENABLED=true` |

## V14 Databeskyttelse

| Krav | Status | Bevis |
|---|---|---|
| Ingen følsomme data i logs | opfyldt | Maskeringsprocessor og ingen kroppe logges, `test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Følsomme svar caches ikke | opfyldt | `Cache-Control: no-store` på hvert ikke-statisk svar |
| Legitimationsoplysninger og tokens hashet i hvile | opfyldt | Argon2id og SHA-256 |
| Dataminimering | opfyldt | Hændelsesværdier afkortes; svarmodeller bærer kun specifikationens felter |
| Sikkerhedskopier beskyttet | delvist | Eksport på applikationsniveau (ADR 0006) til operatørens backupvolumen; serveren krypterer den ikke, så volumen eller arkivet skal krypteres af operatøren |
| Brugere kan fjernes | opfyldt | Admin-UI'et sletter brugere (efter genautentificering) og tilbagekalder deres tokens |

## V15 Sikker kodning og arkitektur

| Krav | Status | Bevis |
|---|---|---|
| Dokumenteret arkitektur og trusselsmodel | opfyldt | `docs/adr/`, [threat-model.md](threat-model.md), `docs/da/graph-schema.md` |
| Statisk analyse og afhængighedskontrol i CI | opfyldt | ruff `S`-regler, Bandit, Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`), pip-audit |
| Ingen farlige funktioner eller deserialisering af ikke-betroede data | opfyldt | Kun JSON; ingen `pickle`, `eval` eller shell-interpolation (Bandit) |
| Race conditions omkring engangshemmeligheder | opfyldt | Indløsning af kode og refresh-token er enkelte transaktioner med registrering af genbrug |
| Adskillelse af browser-UI'ets og API'ets tillidsgrænser | opfyldt | Cookies kun til sider, bearer-tokens kun til API'et; ingen af dem accepterer den anden |

## V16 Sikkerhedslogning og fejlhåndtering

| Krav | Status | Bevis |
|---|---|---|
| Strukturerede logs med request-identifikator og tid i UTC | opfyldt | structlog JSON, `RequestIDMiddleware` |
| Sikkerhedshændelser logges (login, tokenudstedelse, tilbagekaldelse, adminhandlinger) | opfyldt | `AuditEvent`-noder, vist i `/admin/audit` med CSV-eksport |
| Log på forespørgselsniveau til fejlsøgning uden følsomme data | opfyldt | Tilvalgs-`RequestLog` (metode, sti, operation, status, tid, request-id, bytes, kalder; ingen forespørgselsstrenge, headere eller kroppe), begrænset opbevaring, kun administratorer (`/admin/requests`, `/admin/api/requests` med scopet `admin`) |
| Fejl håndteres uden at lække interne detaljer; uventede fejl logges | opfyldt | `errors.py`: specifikationens krop, 5xx logges med request-id |
| Korrekt ur til udløbskontroller | opfyldt | `opencde doctor` sammenligner uret med en NTP-kilde |
| Logbeskyttelse, videresendelse og alarmering | ikke opfyldt | Overladt til operatøren (compose-logdriver, SIEM) |

## V17 WebRTC

ikke relevant.

## Kendte huller

| Hul | Plan |
|---|---|
| Ingen multifaktorautentificering på loginsiden | TOTP (pyotp) som en senere etape; én implementering dækker browserbrugere og OAuth2-klienter |
| Sessionscookie uden `__Host-`-præfiks | Omdøb cookien ved næste cookieændring (kræver https overalt, hvilket produktion har) |
| Ingen live-kontrol mod lækkede kodeord | Valgfrit k-anonymitetsopslag mod et læk-API som indstilling |
| Ingen lagerkvote per bruger | Tilføj `max_storage_bytes_per_user`, når brug med flere lejere begynder |
| Ingen afsenderbundne tokens | DPoP (RFC 9449) som en senere etape |
| Ingen antivirusscanning | Operatørens valg på lagervolumen |
| Sikkerhedskopier krypteres ikke af serveren | Kryptér backupvolumen, eller pak `opencde backup` ind i `age`/`gpg` i sidecaren |
| OAuch og testssl.sh endnu ikke kørt mod en udrulning | Kør før den første produktionsudrulning; registrér rapporterne |
| Ingen ekstern penetrationstest | Valgfri, efter ejerens skøn, efter ovenstående |
