# OWASP ASVS nivå 2-sjekkliste

Selvvurdering mot OWASP Application Security Verification Standard 5.0 på
nivå 2, skrevet av utviklerne 2026-11-05. Det er ikke en ekstern
verifisering. Hvert kapittel lister nivå 2-kravene som gjelder denne
serveren (omskrevet), statusen og bevisene: en kontroll i
[controls.md](controls.md) med testen sin, et dokument eller kode. Kjente
hull samles til slutt; de følges som *Senere* i prosjektplanen.

Status: **oppfylt** (kontroll og test finnes), **delvis** (kontroll finnes
med en dokumentert begrensning), **ikke oppfylt** (planlagt eller overlatt
til operatøren), **ikke relevant** (serveren har ingen slik komponent).

## V1 Koding og sanering

| Krav | Status | Bevis |
|---|---|---|
| Utdatakoding for HTML; ingen DOM-injeksjon av serverdata | oppfylt | Jinja2 autoescape, forbedringsskriptene bruker bare `textContent`, streng CSP som forsvar i dybden; `tests/ui` feiler ved konsollfeil |
| Databasespørringer bygges aldri av inndata | oppfylt | Bare Cypher-parametere, håndhevet av lint-testen `test_core_helpers::test_dialect_ddl_and_cypher_lint`; IFC-etiketter valideres som identifikatorer (`importer._safe`) |
| Spørrespråk eksponert for klienter parses, interpoleres ikke | oppfylt | OData: parser → AST → felthvitliste → parametere, `test_odata` |
| Filnavn og headerverdier saneres og kodes | oppfylt | `sanitize_filename`, RFC 8187 `attachment_header`, `test_bcf_helpers` |
| URL-er fra klienter valideres (skjema, vert) før bruk | oppfylt | `validate_redirect_uri` (https, loopback, private skjemaer), callbacks og dokumentreferanser bare http(s) |

## V2 Validering og forretningslogikk

| Krav | Status | Bevis |
|---|---|---|
| Positiv validering med grenser på all inndata | oppfylt | Pydantic v2-modeller med lengde-, liste- og dybdegrenser, endelige tall; ukjente felt ignoreres etter Foundation API 1.8 |
| Forretningsregler håndheves på serversiden | oppfylt | Saksverdier mot extensions, nøyaktig ett kamera, 409 ved sletting av et referert viewpoint, dupliserte guid-er, én transaksjon per skriving |
| Anti-automatisering på autentisering og dyre operasjoner | delvis | Innloggings- og token-endepunkter hastighetsbegrenset per adresse (`test_sign_in_is_rate_limited`), og mislykkede innlogginger får brukernavnet til å vente (`test_sign_in_throttle`); opplastinger begrenset per fil (`max_upload_bytes`); ingen lagerkvote per bruker ennå |

## V3 Webfrontend-sikkerhet

| Krav | Status | Bevis |
|---|---|---|
| Content Security Policy uten `unsafe-inline`, innramming nektet | oppfylt | `default-src 'none'` på API-svar, `default-src 'self'; frame-ancestors 'none'` på sider; ingen inline-skript eller -stiler; `X-Frame-Options: DENY` |
| Cookies `HttpOnly`, `Secure`, `SameSite=Strict` | delvis | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it`; cookien har ennå ikke `__Host-`-prefiks |
| CSRF-beskyttelse ved hver tilstandsendring fra en nettleser | oppfylt | Signerte, formålsbundne skjematokens pluss `Sec-Fetch-Site`/`Origin`-kontroller, `test_csrf_protections_on_admin_forms`, `test_cross_site_posts_are_refused_and_next_cannot_leave_the_site` |
| Nettleserens sikkerhetsheadere på hvert svar | oppfylt | `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy: same-origin` på administrasjons- og kontosidene (sidene en klient åpner i et popup-vindu, beholder nettleserens standard slik at popup-vinduet beholder sin opener), `test_headers_and_errors` |
| HSTS | oppfylt | Legges til av Caddy i produksjonsoverlegget (`Caddyfile`) |
| Ingen sensitive data i URL-er | delvis | Tokens og passord reiser bare i headere og kropper; Documents API-spesifikasjonen legger et engangslenketoken i `upload_ui_url`/`select_documents_url`, så det er 256 bit, lagret hashet, gyldig 10 minutter, og siden krever dessuten en nettlesersesjon som samme bruker |

## V4 API og webtjeneste

| Krav | Status | Bevis |
|---|---|---|
| JSON-API-er validerer innholdstyper og avviser ustøttede metoder | oppfylt | FastAPI-parsing med spesifikasjonens feilkropp, 405 på andre metoder; Schemathesis `unsupported_method` i den nattlige kjøringen |
| CORS begrenset; aldri credentials med wildcard | oppfylt | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials` |
| Konsistent feilformat uten interne detaljer | oppfylt | Bare `{"message": …}`, `test_headers_and_errors` |
| Autentisering på hver API-operasjon; bare Bearer | oppfylt | `test_foundation::test_current_user_requires_a_bearer_token`, sikkerhetssuiten |
| Kontraktsfuzzing: ingen 5xx, svarene matcher de dokumenterte skjemaene, ugyldig inndata avvises | oppfylt | `tests/e2e/test_schemathesis.py` (hver operasjon, positiv og negativ generering) |

## V5 Filhåndtering

| Krav | Status | Bevis |
|---|---|---|
| Størrelsesgrenser på de faktisk mottatte bytene | oppfylt | Strømmende skrivinger teller bytes; chunked-kropper kuttes; `test_storage_stream_counts_bytes`, `test_chunked_body_over_the_limit_is_cut_off` |
| Filtype avgjøres av innholdet, ikke av klienten | oppfylt | Magic bytes for bilder; dokumenter lagres og serveres som `application/octet-stream` |
| Klientfilnavn når aldri filsystemet | oppfylt | UUID-lagernøkler, `test_storage_keys_cannot_escape` |
| Opplastet innhold kjøres eller gjengis aldri | oppfylt | Vedlegg med `nosniff`; ingen maler fra lageret |
| Arkivutpakking begrenset | oppfylt | `.ifczip` med nøyaktig én `.ifc` og størrelsestaket på utpakkede bytes |
| Parsing av ikke-betrodde filer isolert | oppfylt | IFC-konvertering i en arbeidsprosess med tids-, minne- og entitetsgrenser (`test_ifcgraph_convert`) |
| Antivirusskanning av opplastede filer | ikke oppfylt | Overlatt til operatøren (skann lagervolumet); ingen skanner integrert |

## V6 Autentisering

| Krav | Status | Bevis |
|---|---|---|
| Policy for passordlengde og -styrke, ingen sammensetningsregler | oppfylt | `auth/passwords.py`: minst 12 tegn og zxcvbn-score ≥ 3 med brukernavnet som kjent inndata, `test_password_policy_and_hashing` |
| Kontroll mot lister over lekkede passord | delvis | zxcvbns ordbøker over vanlige passord; ingen live-oppslag mot lekkasjelister |
| Argon2id-hashing | oppfylt | `pwdlib` med Argon2id, `test_password_policy_and_hashing` |
| Brute-force-beskyttelse med generiske meldinger | oppfylt | Hastighetsgrense per adresse, en voksende ventetid per brukernavn, konstant melding ved feil bruker eller passord, deaktiverte kontoer avvises (`test_disabled_user_cannot_sign_in_and_loses_tokens`) |
| Multifaktorautentisering | ikke oppfylt | Bare passord; TOTP for innloggingssiden er planlagt (*Senere* i planen). API-klienter ser aldri passord: de autentiserer seg gjennom OAuth2 mot denne innloggingssiden, så én MFA dekker alt |
| Sikker gjenoppretting av påloggingsopplysninger | oppfylt | Ingen selvbetjent tilbakestilling; en administrator utsteder et engangspassord etter reautentisering, og brukeren må bytte det ved neste innlogging |
| Reautentisering ved sensitive operasjoner | oppfylt | Eget passord kreves ved passordbytter, tilbakestillinger, endring av adminflagget, hemmelighetsrotasjon og sletting (`test_user_management`, `test_client_management_and_secret_rotation`) |
| Deaktivering av en konto avslutter tilgangen dens | oppfylt | Tokens og sesjoner trekkes tilbake når en bruker deaktiveres |

## V7 Sesjonshåndtering

| Krav | Status | Bevis |
|---|---|---|
| Serverside-sesjoner med tilfeldige identifikatorer, lagret hashet | oppfylt | `web/sessions.py`, 256-bits cookieverdi, SHA-256 i ro |
| Ny sesjon ved innlogging; utlogging ødelegger den | oppfylt | `test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Inaktivitets- og absolutte tidsavbrudd | oppfylt | `web_session_idle_seconds` og absolutt utløp, ryddet av oppryddingen |
| Brukere kan se og avslutte sesjonene og tildelingene sine | oppfylt | `/account`: sesjoner, applikasjoner, "logg ut overalt" |
| Administratorer kan avslutte enhver sesjon eller tildeling | oppfylt | `/admin/sessions`, `opencde revoke` |

## V8 Autorisasjon

| Krav | Status | Bevis |
|---|---|---|
| Nekt som standard; kontroller på objektnivå ved hver tilgang | oppfylt | Hver spørring starter i brukernoden og går via `MEMBER_OF`; ikke-medlemmer får 404 (`test_topic_authorization_matrix`) |
| Kontroller på funksjonsnivå per rolle, på serversiden | oppfylt | Rolle × handling-matrise for prosjekter, saker, kommentarer, viewpoints, dokumenter; `authorization`-objekter avledet av de samme reglene |
| Administrative funksjoner atskilt og beskyttet | oppfylt | `/admin` krever adminrollen på hver rute (`test_admin_pages_need_the_admin_role`) |
| Autorisasjon avgjøres i samme transaksjon som endringen | oppfylt | Repository-metoder kontrollerer og skriver i én transaksjon |
| Eksponering på feltnivå begrenset | oppfylt | Eksplisitte svarmodeller; hasher og lagernøkler finnes i intet svar (`validate_documents`, conformance-suiten) |

## V9 Selvstendige tokens

ikke relevant: tokens er opake referanser lagret som hasher (ADR 0002); det
finnes ingen JWT-er å validere.

## V10 OAuth og OIDC

| Krav | Status | Bevis |
|---|---|---|
| Bare authorization code med PKCE `S256`; ingen implicit- eller password-grants | oppfylt | `test_pkce_is_mandatory_and_plain_is_refused` |
| Nøyaktig matching av redirect-URI; loopback-unntak etter RFC 8252 | oppfylt | `test_unregistered_redirect_uri_is_shown_not_followed`, `test_loopback_port_may_vary_but_host_may_not` |
| `state` kreves; `iss` i svaret | oppfylt | `test_state_is_required_and_unknown_scope_is_refused`, `test_public_client_flow_with_pkce` |
| Engangskoder bundet til klient, redirect-URI og verifier | oppfylt | `test_code_is_single_use_and_replay_revokes_tokens`, `test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Rotasjon av refresh-tokens med oppdaging av gjenbruk | oppfylt | `test_refresh_rotates_and_reuse_revokes_the_family` |
| Tilbaketrekking (RFC 7009) | oppfylt | `test_revocation` |
| Klientautentisering; offentlige klienter uten hemmeligheter | oppfylt | `test_client_authentication_failures` |
| Tokensvar kan ikke caches | oppfylt | `test_token_response_is_never_cached_and_has_spec_fields` |
| Samtykkeskjermen navngir klienten og omdirigeringsmålet; brukeren kan nekte | oppfylt | `test_deny_redirects_with_access_denied`, `auth/templates` |
| Dynamisk registrering begrenset | oppfylt | Av som standard; bare https- eller loopback-omdirigeringer når på; offentlige registreringer (RFC 7591 `none`) hviler på PKCE og på at samtykkesiden navngir klienten og omdirigeringsverten dens; hastighetsbegrenset; et innledende tilgangstoken og en administrators godkjenning er valgfrie |
| Avsenderbundne tokens (DPoP, mTLS) | ikke oppfylt | Nivå 3-punkt; listet under *Senere* i planen |
| Etterlevelse testet med et eksternt verktøy | ikke oppfylt | OAuch-kjøring beskrevet i [pentest-howto.md](pentest-howto.md) §4, skal gjøres før den første produksjonsutrullingen |

## V11 Kryptografi

| Krav | Status | Bevis |
|---|---|---|
| Godkjente algoritmer og CSPRNG | oppfylt | `secrets` for koder, tokens, cookies og klienthemmeligheter; Argon2id; SHA-256 for tokenhasher; HMAC-signerte skjematokens (`itsdangerous`) |
| Hemmeligheter ikke i kode eller images | oppfylt | `OPENCDE_SECRET_KEY` og databasepassordet fra miljøet eller Docker secrets, generert av `opencde init`; `.env` ignoreres av git; gitleaks i CI |
| Nøkkelrotasjon | delvis | Rotasjon av `OPENCDE_SECRET_KEY` ugyldiggjør skjematokens og nettlesersesjoner, ingenting annet; dokumentert som et operatørtrinn i `docs/nb/deploy/vps-caddy.md`; ingen overgang med dobbel nøkkel |

## V12 Sikker kommunikasjon

| Krav | Status | Bevis |
|---|---|---|
| Bare TLS 1.2 eller 1.3, gyldige sertifikater, HSTS | oppfylt | Caddy i `compose.prod.yaml`; produksjon nekter en offentlig http-URL (`test_settings`); testssl.sh-kjøring i [pentest-howto.md](pentest-howto.md) §5 før produksjon |
| Interne forbindelser beskyttet | oppfylt | Databasen bare på det private compose-nettet; `neo4j+s://` for en ekstern database (`docs/nb/deploy/cloud-aura.md`) |
| Videresendte headere stoles på bare fra kjente proxyer | oppfylt | `OPENCDE_TRUSTED_PROXIES` |

## V13 Konfigurasjon

| Krav | Status | Bevis |
|---|---|---|
| Sikre standardverdier; serveren nekter usikre produksjonsinnstillinger | oppfylt | `test_settings`: https, databasepassord og hemmelig nøkkel kreves i produksjon, localhost-omdirigeringer avvises |
| Avhengigheter festet, revidert og oppdatert | oppfylt | `uv.lock`, pip-audit, Dependabot med 7 dagers cooldown, actions festet med SHA og kontrollert av zizmor |
| Herdet container | oppfylt | Ikke-root, skrivebeskyttet rotfilsystem, fjernede capabilities, `no-new-privileges`, Trivy-skanning med SBOM ved release |
| Driftskontroller | oppfylt | `opencde doctor` (database, skjema, klokke, offentlig URL, headere, lager) |
| Administrasjonsgrensesnittet kan isoleres | oppfylt | Separat innlogging og rolle; `OPENCDE_ADMIN_UI_ENABLED=false` fjerner det fra en offentlig instans (administrer via CLI i stedet), eller begrens `/admin` til interne adresser i proxyen |
| Ingen tredjepartskode på produksjonssider | oppfylt | Serverens sider laster ingenting fra andre origins; den interaktive API-dokumentasjonen (`/docs`, Swagger UI fra et CDN) serveres bare utenfor produksjon med mindre `OPENCDE_API_DOCS_ENABLED=true` |

## V14 Databeskyttelse

| Krav | Status | Bevis |
|---|---|---|
| Ingen sensitive data i logger | oppfylt | Maskeringsprosessor og ingen kropper logges, `test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Sensitive svar caches ikke | oppfylt | `Cache-Control: no-store` på hvert ikke-statisk svar |
| Påloggingsopplysninger og tokens hashet i ro | oppfylt | Argon2id og SHA-256 |
| Dataminimering | oppfylt | Hendelsesverdier klippes; svarmodeller bærer bare spesifikasjonens felt |
| Sikkerhetskopier beskyttet | delvis | Eksport på applikasjonsnivå (ADR 0006) til operatørens backupvolum; serveren krypterer den ikke, så volumet eller arkivet må krypteres av operatøren |
| Brukere kan fjernes | oppfylt | Admin-UI-et sletter brukere (etter reautentisering) og trekker tilbake tokenene deres |

## V15 Sikker koding og arkitektur

| Krav | Status | Bevis |
|---|---|---|
| Dokumentert arkitektur og trusselmodell | oppfylt | `docs/adr/`, [threat-model.md](threat-model.md), `docs/nb/graph-schema.md` |
| Statisk analyse og avhengighetskontroller i CI | oppfylt | ruff `S`-regler, Bandit, Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`), pip-audit |
| Ingen farlige funksjoner eller deserialisering av ikke-betrodde data | oppfylt | Bare JSON; ingen `pickle`, `eval` eller shell-interpolasjon (Bandit) |
| Kappløp rundt engangshemmeligheter | oppfylt | Innløsning av kode og refresh-token er enkelttransaksjoner med oppdaging av gjenbruk |
| Atskillelse av nettleser-UI-ets og API-ets tillitsgrenser | oppfylt | Cookies bare for sider, bearer-tokens bare for API-et; ingen av dem godtar den andre |

## V16 Sikkerhetslogging og feilhåndtering

| Krav | Status | Bevis |
|---|---|---|
| Strukturerte logger med request-identifikator og tid i UTC | oppfylt | structlog JSON, `RequestIDMiddleware` |
| Sikkerhetshendelser logges (innlogging, tokenutstedelse, tilbaketrekking, adminhandlinger) | oppfylt | `AuditEvent`-noder, vist i `/admin/audit` med CSV-eksport |
| Logg på forespørselsnivå for feilsøking uten sensitive data | oppfylt | Valgfri `RequestLog` (metode, sti, operasjon, status, tid, request-id, bytes, kaller; ingen spørrestrenger, headere eller kropper), begrenset oppbevaring, bare administratorer (`/admin/requests`, `/admin/api/requests` med scopet `admin`) |
| Feil håndteres uten å lekke interne detaljer; uventede feil logges | oppfylt | `errors.py`: spesifikasjonens kropp, 5xx logges med request-id |
| Riktig klokke for utløpskontroller | oppfylt | `opencde doctor` sammenligner klokken med en NTP-kilde |
| Loggbeskyttelse, videresending og varsling | ikke oppfylt | Overlatt til operatøren (compose-loggdriver, SIEM) |

## V17 WebRTC

ikke relevant.

## Kjente hull

| Hull | Plan |
|---|---|
| Ingen multifaktorautentisering på innloggingssiden | TOTP (pyotp) som en senere etappe; én implementering dekker nettleserbrukere og OAuth2-klienter |
| Sesjonscookie uten `__Host-`-prefiks | Gi cookien nytt navn ved neste cookieendring (krever https overalt, som produksjon har) |
| Ingen live-kontroll mot lekkede passord | Valgfritt k-anonymitetsoppslag mot et lekkasje-API som innstilling |
| Ingen lagerkvote per bruker | Legg til `max_storage_bytes_per_user` når bruk med flere leietakere begynner |
| Ingen avsenderbundne tokens | DPoP (RFC 9449) som en senere etappe |
| Ingen antivirusskanning | Operatørens valg på lagervolumet |
| Sikkerhetskopier krypteres ikke av serveren | Krypter backupvolumet, eller pakk `opencde backup` inn i `age`/`gpg` i sidevognen |
| OAuch og testssl.sh ennå ikke kjørt mot en utrulling | Kjør før den første produksjonsutrullingen; registrer rapportene |
| Ingen ekstern penetrasjonstest | Valgfri, etter eierens skjønn, etter det ovenstående |
