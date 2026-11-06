# OWASP ASVS nivå 2-sjekkliste

Sjølvvurdering mot OWASP Application Security Verification Standard 5.0 på
nivå 2, skriven av utviklarane 2026-11-05. Det er ikkje ei ekstern
verifisering. Kvart kapittel listar nivå 2-krava som gjeld denne serveren
(omskrivne), statusen og bevisa: ein kontroll i [controls.md](controls.md)
med testen sin, eit dokument eller kode. Kjende hol blir samla til slutt; dei
blir følgde som *Seinare* i prosjektplanen.

Status: **oppfylt** (kontroll og test finst), **delvis** (kontroll finst med
ei dokumentert avgrensing), **ikkje oppfylt** (planlagt eller overlate til
operatøren), **ikkje relevant** (serveren har ingen slik komponent).

## V1 Koding og sanering

| Krav | Status | Bevis |
|---|---|---|
| Utdatakoding for HTML; ingen DOM-injeksjon av serverdata | oppfylt | Jinja2 autoescape, forbetringsskripta brukar berre `textContent`, streng CSP som forsvar i dybda; `tests/ui` feilar ved konsollfeil |
| Databasespørjingar blir aldri bygde av inndata | oppfylt | Berre Cypher-parametrar, handheva av lint-testen `test_core_helpers::test_dialect_ddl_and_cypher_lint`; IFC-etikettar blir validerte som identifikatorar (`importer._safe`) |
| Spørjespråk eksponerte for klientar blir parsa, ikkje interpolerte | oppfylt | OData: parsar → AST → feltkvitliste → parametrar, `test_odata` |
| Filnamn og headerverdiar blir sanerte og koda | oppfylt | `sanitize_filename`, RFC 8187 `attachment_header`, `test_bcf_helpers` |
| URL-ar frå klientar blir validerte (skjema, vert) før bruk | oppfylt | `validate_redirect_uri` (https, loopback, private skjema), callbacks og dokumentreferansar berre http(s) |

## V2 Validering og forretningslogikk

| Krav | Status | Bevis |
|---|---|---|
| Positiv validering med grenser på all inndata | oppfylt | Pydantic v2-modellar med lengd-, liste- og dybdegrenser, endelege tal; ukjende felt blir ignorerte etter Foundation API 1.8 |
| Forretningsreglar blir handheva på serversida | oppfylt | Saksverdiar mot extensions, nøyaktig eitt kamera, 409 ved sletting av eit referert viewpoint, dupliserte guid-ar, éin transaksjon per skriving |
| Anti-automatisering på autentisering og dyre operasjonar | delvis | Innloggings- og token-endepunkt takstavgrensa per adresse (`test_sign_in_is_rate_limited`), og mislukka innloggingar får brukarnamnet til å vente (`test_sign_in_throttle`); opplastingar avgrensa per fil (`max_upload_bytes`); ingen lagerkvote per brukar enno |

## V3 Webfrontend-tryggleik

| Krav | Status | Bevis |
|---|---|---|
| Content Security Policy utan `unsafe-inline`, innramming nekta | oppfylt | `default-src 'none'` på API-svar, `default-src 'self'; frame-ancestors 'none'` på sider; ingen inline-skript eller -stilar; `X-Frame-Options: DENY` |
| Cookies `HttpOnly`, `Secure`, `SameSite=Strict` | delvis | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it`; cookien har enno ikkje `__Host-`-prefiks |
| CSRF-vern ved kvar tilstandsendring frå ein nettlesar | oppfylt | Signerte, formålsbundne skjematokens pluss `Sec-Fetch-Site`/`Origin`-kontrollar, `test_csrf_protections_on_admin_forms`, `test_cross_site_posts_are_refused_and_next_cannot_leave_the_site` |
| Tryggingsheaderane til nettlesaren på kvart svar | oppfylt | `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy: same-origin` på administrasjons- og kontosidene (sidene ein klient opnar i eit popup-vindauge, held på standarden i nettlesaren slik at popup-vindauget held på openeren sin), `test_headers_and_errors` |
| HSTS | oppfylt | Lagt til av Caddy i produksjonsoverlegget (`Caddyfile`) |
| Ingen sensitive data i URL-ar | delvis | Tokens og passord reiser berre i headerar og kroppar; Documents API-spesifikasjonen legg eit eingongslenkjetoken i `upload_ui_url`/`select_documents_url`, så det er 256 bit, lagra hasha, gyldig 10 minutt, og sida krev dessutan ein nettlesarsesjon som same brukar |

## V4 API og webteneste

| Krav | Status | Bevis |
|---|---|---|
| JSON-API-ar validerer innhaldstypar og avviser ustøtta metodar | oppfylt | FastAPI-parsing med feilkroppen frå spesifikasjonen, 405 på andre metodar; Schemathesis `unsupported_method` i den nattlege køyringa |
| CORS avgrensa; aldri credentials med wildcard | oppfylt | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials` |
| Konsistent feilformat utan interne detaljar | oppfylt | Berre `{"message": …}`, `test_headers_and_errors` |
| Autentisering på kvar API-operasjon; berre Bearer | oppfylt | `test_foundation::test_current_user_requires_a_bearer_token`, tryggingssuiten |
| Kontraktsfuzzing: ingen 5xx, svara matchar dei dokumenterte skjemaa, ugyldig inndata blir avvist | oppfylt | `tests/e2e/test_schemathesis.py` (kvar operasjon, positiv og negativ generering) |

## V5 Filhandsaming

| Krav | Status | Bevis |
|---|---|---|
| Storleiksgrenser på dei faktisk mottekne bytane | oppfylt | Strøymande skrivingar tel bytes; chunked-kroppar blir kutta; `test_storage_stream_counts_bytes`, `test_chunked_body_over_the_limit_is_cut_off` |
| Filtype blir avgjord av innhaldet, ikkje av klienten | oppfylt | Magic bytes for bilete; dokument blir lagra og serverte som `application/octet-stream` |
| Klientfilnamn når aldri filsystemet | oppfylt | UUID-lagernøklar, `test_storage_keys_cannot_escape` |
| Opplasta innhald blir aldri køyrt eller teikna | oppfylt | Vedlegg med `nosniff`; ingen malar frå lageret |
| Arkivutpakking avgrensa | oppfylt | `.ifczip` med nøyaktig éi `.ifc` og storleikstaket på utpakka bytes |
| Parsing av ikkje-betrudde filer isolert | oppfylt | IFC-konvertering i ein arbeidsprosess med tids-, minne- og entitetsgrenser (`test_ifcgraph_convert`) |
| Antivirusskanning av opplasta filer | ikkje oppfylt | Overlate til operatøren (skann lagervolumet); ingen skannar integrert |

## V6 Autentisering

| Krav | Status | Bevis |
|---|---|---|
| Policy for passordlengd og -styrke, ingen samansetjingsreglar | oppfylt | `auth/passwords.py`: minst 12 teikn og zxcvbn-score ≥ 3 med brukarnamnet som kjend inndata, `test_password_policy_and_hashing` |
| Kontroll mot lister over lekne passord | delvis | Ordbøkene til zxcvbn over vanlege passord; ingen live-oppslag mot lekkasjelister |
| Argon2id-hashing | oppfylt | `pwdlib` med Argon2id, `test_password_policy_and_hashing` |
| Brute-force-vern med generiske meldingar | oppfylt | Takstgrense per adresse, ei veksande ventetid per brukarnamn, konstant melding ved feil brukar eller passord, deaktiverte kontoar blir avviste (`test_disabled_user_cannot_sign_in_and_loses_tokens`) |
| Multifaktorautentisering | ikkje oppfylt | Berre passord; TOTP for innloggingssida er planlagt (*Seinare* i planen). API-klientar ser aldri passord: dei autentiserer seg gjennom OAuth2 mot denne innloggingssida, så éin MFA dekkjer alt |
| Trygg gjenoppretting av påloggingsopplysningar | oppfylt | Ingen sjølvbetent tilbakestilling; ein administrator utferdar eit eingongspassord etter reautentisering, og brukaren må byte det ved neste innlogging |
| Reautentisering ved sensitive operasjonar | oppfylt | Eige passord krevst ved passordbyte, tilbakestillingar, endring av adminflagget, løyndomsrotasjon og sletting (`test_user_management`, `test_client_management_and_secret_rotation`) |
| Deaktivering av ein konto avsluttar tilgangen hans | oppfylt | Tokens og sesjonar blir trekte tilbake når ein brukar blir deaktivert |

## V7 Sesjonshandsaming

| Krav | Status | Bevis |
|---|---|---|
| Serverside-sesjonar med tilfeldige identifikatorar, lagra hasha | oppfylt | `web/sessions.py`, 256-bits cookieverdi, SHA-256 i ro |
| Ny sesjon ved innlogging; utlogging øydelegg han | oppfylt | `test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Inaktivitets- og absolutte tidsavbrot | oppfylt | `web_session_idle_seconds` og absolutt utgang, rydda av oppryddinga |
| Brukarar kan sjå og avslutte sesjonane og tildelingane sine | oppfylt | `/account`: sesjonar, applikasjonar, "logg ut overalt" |
| Administratorar kan avslutte kvar sesjon eller tildeling | oppfylt | `/admin/sessions`, `opencde revoke` |

## V8 Autorisasjon

| Krav | Status | Bevis |
|---|---|---|
| Nekt som standard; kontrollar på objektnivå ved kvar tilgang | oppfylt | Kvar spørjing startar i brukarnoden og går via `MEMBER_OF`; ikkje-medlemer får 404 (`test_topic_authorization_matrix`) |
| Kontrollar på funksjonsnivå per rolle, på serversida | oppfylt | Rolle × handling-matrise for prosjekt, saker, kommentarar, viewpoints, dokument; `authorization`-objekt avleidde av dei same reglane |
| Administrative funksjonar skilde og verna | oppfylt | `/admin` krev adminrolla på kvar rute (`test_admin_pages_need_the_admin_role`) |
| Autorisasjon blir avgjord i same transaksjon som endringa | oppfylt | Repository-metodar kontrollerer og skriv i éin transaksjon |
| Eksponering på feltnivå avgrensa | oppfylt | Eksplisitte svarmodellar; hashar og lagernøklar finst i inkje svar (`validate_documents`, conformance-suiten) |

## V9 Sjølvstendige tokens

ikkje relevant: tokens er opake referansar lagra som hashar (ADR 0002); det
finst ingen JWT-ar å validere.

## V10 OAuth og OIDC

| Krav | Status | Bevis |
|---|---|---|
| Berre authorization code med PKCE `S256`; ingen implicit- eller password-grants | oppfylt | `test_pkce_is_mandatory_and_plain_is_refused` |
| Nøyaktig matching av redirect-URI; loopback-unntak etter RFC 8252 | oppfylt | `test_unregistered_redirect_uri_is_shown_not_followed`, `test_loopback_port_may_vary_but_host_may_not` |
| `state` krevst; `iss` i svaret | oppfylt | `test_state_is_required_and_unknown_scope_is_refused`, `test_public_client_flow_with_pkce` |
| Eingongskodar bundne til klient, redirect-URI og verifier | oppfylt | `test_code_is_single_use_and_replay_revokes_tokens`, `test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Rotasjon av refresh-tokens med oppdaging av gjenbruk | oppfylt | `test_refresh_rotates_and_reuse_revokes_the_family` |
| Tilbaketrekking (RFC 7009) | oppfylt | `test_revocation` |
| Klientautentisering; offentlege klientar utan løyndomar | oppfylt | `test_client_authentication_failures` |
| Tokensvar kan ikkje cachast | oppfylt | `test_token_response_is_never_cached_and_has_spec_fields` |
| Samtykkeskjermen namngjev klienten og omdirigeringsmålet; brukaren kan nekte | oppfylt | `test_deny_redirects_with_access_denied`, `auth/templates` |
| Dynamisk registrering avgrensa | oppfylt | Av som standard; berre https- eller loopback-omdirigeringar når på; offentlege registreringar (RFC 7591 `none`) kviler på PKCE og på at samtykkesida namngjev klienten og omdirigeringsverten hans; takstavgrensa; eit innleiande tilgangstoken og godkjenning frå ein administrator er valfrie |
| Avsendarbundne tokens (DPoP, mTLS) | ikkje oppfylt | Nivå 3-punkt; lista under *Seinare* i planen |
| Etterleving testa med eit eksternt verktøy | ikkje oppfylt | OAuch-køyring skildra i [pentest-howto.md](pentest-howto.md) §4, skal gjerast før den første produksjonsutrullinga |

## V11 Kryptografi

| Krav | Status | Bevis |
|---|---|---|
| Godkjende algoritmar og CSPRNG | oppfylt | `secrets` for kodar, tokens, cookies og klientløyndomar; Argon2id; SHA-256 for tokenhashar; HMAC-signerte skjematokens (`itsdangerous`) |
| Løyndomar ikkje i kode eller images | oppfylt | `OPENCDE_SECRET_KEY` og databasepassordet frå miljøet eller Docker secrets, genererte av `opencde init`; `.env` blir ignorert av git; gitleaks i CI |
| Nøkkelrotasjon | delvis | Rotasjon av `OPENCDE_SECRET_KEY` gjer skjematokens og nettlesarsesjonar ugyldige, ingenting anna; dokumentert som eit operatørsteg i `docs/nn/deploy/vps-caddy.md`; ingen overgang med dobbel nøkkel |

## V12 Trygg kommunikasjon

| Krav | Status | Bevis |
|---|---|---|
| Berre TLS 1.2 eller 1.3, gyldige sertifikat, HSTS | oppfylt | Caddy i `compose.prod.yaml`; produksjon nektar ein offentleg http-URL (`test_settings`); testssl.sh-køyring i [pentest-howto.md](pentest-howto.md) §5 før produksjon |
| Interne samband verna | oppfylt | Databasen berre på det private compose-nettet; `neo4j+s://` for ein ekstern database (`docs/nn/deploy/cloud-aura.md`) |
| Vidaresende headerar blir stolte på berre frå kjende proxyar | oppfylt | `OPENCDE_TRUSTED_PROXIES` |

## V13 Konfigurasjon

| Krav | Status | Bevis |
|---|---|---|
| Trygge standardverdiar; serveren nektar utrygge produksjonsinnstillingar | oppfylt | `test_settings`: https, databasepassord og løynd nøkkel krevst i produksjon, localhost-omdirigeringar blir avviste |
| Avhengnader festa, reviderte og oppdaterte | oppfylt | `uv.lock`, pip-audit, Dependabot med 7 dagars cooldown, actions festa med SHA og kontrollerte av zizmor |
| Herda container | oppfylt | Ikkje-root, skriveverna rotfilsystem, fjerna capabilities, `no-new-privileges`, Trivy-skanning med SBOM ved release |
| Driftskontrollar | oppfylt | `opencde doctor` (database, skjema, klokke, offentleg URL, headerar, lager) |
| Administrasjonsgrensesnittet kan isolerast | oppfylt | Separat innlogging og rolle; `OPENCDE_ADMIN_UI_ENABLED=false` fjernar det frå ein offentleg instans (administrer via CLI i staden), eller avgrens `/admin` til interne adresser i proxyen |
| Ingen tredjepartskode på produksjonssider | oppfylt | Sidene til serveren lastar ingenting frå andre origins; den interaktive API-dokumentasjonen (`/docs`, Swagger UI frå eit CDN) blir servert berre utanfor produksjon med mindre `OPENCDE_API_DOCS_ENABLED=true` |

## V14 Datavern

| Krav | Status | Bevis |
|---|---|---|
| Ingen sensitive data i loggar | oppfylt | Maskeringsprosessor og ingen kroppar blir logga, `test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Sensitive svar blir ikkje cacha | oppfylt | `Cache-Control: no-store` på kvart ikkje-statisk svar |
| Påloggingsopplysningar og tokens hasha i ro | oppfylt | Argon2id og SHA-256 |
| Dataminimering | oppfylt | Hendingsverdiar blir klipte; svarmodellar ber berre felta i spesifikasjonen |
| Tryggingskopiar verna | delvis | Eksport på applikasjonsnivå (ADR 0006) til backupvolumet til operatøren; serveren krypterer det ikkje, så volumet eller arkivet må krypterast av operatøren |
| Brukarar kan fjernast | oppfylt | Admin-UI-et slettar brukarar (etter reautentisering) og trekkjer tilbake tokena deira |

## V15 Trygg koding og arkitektur

| Krav | Status | Bevis |
|---|---|---|
| Dokumentert arkitektur og trugsmålsmodell | oppfylt | `docs/adr/`, [threat-model.md](threat-model.md), `docs/nn/graph-schema.md` |
| Statisk analyse og avhengnadskontrollar i CI | oppfylt | ruff `S`-reglar, Bandit, Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`), pip-audit |
| Ingen farlege funksjonar eller deserialisering av ikkje-betrudde data | oppfylt | Berre JSON; ingen `pickle`, `eval` eller shell-interpolasjon (Bandit) |
| Kappløp rundt eingongsløyndomar | oppfylt | Innløysing av kode og refresh-token er enkelttransaksjonar med oppdaging av gjenbruk |
| Skilje mellom tillitsgrensene til nettlesar-UI-et og API-et | oppfylt | Cookies berre for sider, bearer-tokens berre for API-et; ingen av dei godtek den andre |

## V16 Tryggingslogging og feilhandsaming

| Krav | Status | Bevis |
|---|---|---|
| Strukturerte loggar med request-identifikator og tid i UTC | oppfylt | structlog JSON, `RequestIDMiddleware` |
| Tryggingshendingar blir logga (innlogging, tokenutferding, tilbaketrekking, adminhandlingar) | oppfylt | `AuditEvent`-nodar, viste i `/admin/audit` med CSV-eksport |
| Logg på førespurnadsnivå for feilsøking utan sensitive data | oppfylt | Valfri `RequestLog` (metode, sti, operasjon, status, tid, request-id, bytes, kallar; ingen spørjestrengar, headerar eller kroppar), avgrensa lagringstid, berre administratorar (`/admin/requests`, `/admin/api/requests` med scopet `admin`) |
| Feil blir handsama utan å leke interne detaljar; uventa feil blir logga | oppfylt | `errors.py`: kroppen frå spesifikasjonen, 5xx blir logga med request-id |
| Rett klokke for utgangskontrollar | oppfylt | `opencde doctor` samanliknar klokka med ei NTP-kjelde |
| Loggvern, vidaresending og varsling | ikkje oppfylt | Overlate til operatøren (compose-loggdrivar, SIEM) |

## V17 WebRTC

ikkje relevant.

## Kjende hol

| Hol | Plan |
|---|---|
| Ingen multifaktorautentisering på innloggingssida | TOTP (pyotp) som ei seinare etappe; éi implementering dekkjer nettlesarbrukarar og OAuth2-klientar |
| Sesjonscookie utan `__Host-`-prefiks | Gje cookien nytt namn ved neste cookieendring (krev https overalt, som produksjon har) |
| Ingen live-kontroll mot lekne passord | Valfritt k-anonymitetsoppslag mot eit lekkasje-API som innstilling |
| Ingen lagerkvote per brukar | Legg til `max_storage_bytes_per_user` når bruk med fleire leigetakarar byrjar |
| Ingen avsendarbundne tokens | DPoP (RFC 9449) som ei seinare etappe |
| Ingen antivirusskanning | Valet til operatøren på lagervolumet |
| Tryggingskopiar blir ikkje krypterte av serveren | Krypter backupvolumet, eller pakk `opencde backup` inn i `age`/`gpg` i sidevogna |
| OAuch og testssl.sh enno ikkje køyrde mot ei utrulling | Køyr før den første produksjonsutrullinga; registrer rapportane |
| Ingen ekstern penetrasjonstest | Valfri, etter eigaren sitt skjøn, etter det ovanståande |
