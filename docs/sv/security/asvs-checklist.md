# OWASP ASVS nivå 2-checklista

Självskattning mot OWASP Application Security Verification Standard 5.0 på
nivå 2, skriven av utvecklarna 2026-11-05. Det är inte en extern
verifiering. Varje kapitel listar de nivå 2-krav som gäller den här servern
(omskrivna), statusen och bevisen: en kontroll i [controls.md](controls.md)
med sitt test, ett dokument eller kod. Kända luckor samlas i slutet; de följs
som *Senare* i projektplanen.

Status: **uppfyllt** (kontroll och test finns), **delvis** (kontroll finns
med en dokumenterad begränsning), **ej uppfyllt** (planerat eller lämnat till
operatören), **ej tillämpligt** (servern har ingen sådan komponent).

## V1 Kodning och sanering

| Krav | Status | Bevis |
|---|---|---|
| Utdatakodning för HTML; ingen DOM-injektion av serverdata | uppfyllt | Jinja2 autoescape, förbättringsskripten använder bara `textContent`, strikt CSP som djupförsvar; `tests/ui` misslyckas vid konsolfel |
| Databasfrågor byggs aldrig av indata | uppfyllt | Bara Cypher-parametrar, upprätthållet av lint-testet `test_core_helpers::test_dialect_ddl_and_cypher_lint`; IFC-etiketter valideras som identifierare (`importer._safe`) |
| Frågespråk exponerade för klienter tolkas, interpoleras inte | uppfyllt | OData: parser → AST → fältvitlista → parametrar, `test_odata` |
| Filnamn och huvudvärden saneras och kodas | uppfyllt | `sanitize_filename`, RFC 8187 `attachment_header`, `test_bcf_helpers` |
| URL:er från klienter valideras (schema, värd) före användning | uppfyllt | `validate_redirect_uri` (https, loopback, privata scheman), callbacks och dokumentreferenser bara http(s) |

## V2 Validering och affärslogik

| Krav | Status | Bevis |
|---|---|---|
| Positiv validering med gränser på varje indata | uppfyllt | Pydantic v2-modeller med längd-, list- och djupgränser, finita tal; okända fält ignoreras enligt Foundation API 1.8 |
| Affärsregler upprätthålls på serversidan | uppfyllt | Ärendevärden mot extensions, exakt en kamera, 409 vid borttagning av refererad viewpoint, dubblerade guid, en transaktion per skrivning |
| Anti-automatisering vid autentisering och dyra operationer | delvis | Inloggnings- och token-endpoints hastighetsbegränsade per adress (`test_sign_in_is_rate_limited`); uppladdningar begränsade per fil (`max_upload_bytes`); ingen lagringskvot per användare ännu |

## V3 Webbfrontendens säkerhet

| Krav | Status | Bevis |
|---|---|---|
| Content Security Policy utan `unsafe-inline`, inramning nekad | uppfyllt | `default-src 'none'` på API-svar, `default-src 'self'; frame-ancestors 'none'` på sidor; inga inline-skript eller -stilar; `X-Frame-Options: DENY` |
| Kakor `HttpOnly`, `Secure`, `SameSite=Strict` | delvis | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it`; kakan har inget `__Host-`-prefix ännu |
| CSRF-skydd vid varje tillståndsändring från en webbläsare | uppfyllt | Signerade, ändamålsbundna formulärtokens plus `Sec-Fetch-Site`/`Origin`-kontroller, `test_csrf_protections_on_admin_forms`, `test_cross_site_posts_are_refused_and_next_cannot_leave_the_site` |
| Webbläsarens säkerhetshuvuden på varje svar | uppfyllt | `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy: same-origin` på administrations- och kontosidorna (sidorna en klient öppnar i ett popup-fönster behåller webbläsarens standard så att popup-fönstret behåller sin opener), `test_headers_and_errors` |
| HSTS | uppfyllt | Läggs till av Caddy i produktionsöverlagringen (`Caddyfile`) |
| Inga känsliga data i URL:er | delvis | Tokens och lösenord färdas bara i huvuden och kroppar; Documents API-specifikationen lägger en engångslänktoken i `upload_ui_url`/`select_documents_url`, så den är 256 bitar, lagrad hashad, giltig 10 minuter och sidan kräver dessutom en webbläsarsession som samma användare |

## V4 API och webbtjänst

| Krav | Status | Bevis |
|---|---|---|
| JSON-API:er validerar innehållstyper och avvisar ostödda metoder | uppfyllt | FastAPI-tolkning med specens felkropp, 405 på andra metoder; Schemathesis `unsupported_method` i den nattliga körningen |
| CORS begränsat; aldrig credentials med jokertecken | uppfyllt | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials` |
| Enhetligt felformat utan interna detaljer | uppfyllt | Bara `{"message": …}`, `test_headers_and_errors` |
| Autentisering på varje API-operation; bara Bearer | uppfyllt | `test_foundation::test_current_user_requires_a_bearer_token`, säkerhetssviten |
| Kontraktsfuzzning: inga 5xx, svaren matchar de dokumenterade schemana, ogiltig indata avvisas | uppfyllt | `tests/e2e/test_schemathesis.py` (varje operation, positiv och negativ generering) |

## V5 Filhantering

| Krav | Status | Bevis |
|---|---|---|
| Storleksgränser på de faktiskt mottagna bytena | uppfyllt | Strömmande skrivningar räknar bytes; chunked-kroppar klipps; `test_storage_stream_counts_bytes`, `test_chunked_body_over_the_limit_is_cut_off` |
| Filtyp avgörs av innehållet, inte av klienten | uppfyllt | Magic bytes för bilder; dokument lagras och serveras som `application/octet-stream` |
| Klientfilnamn når aldrig filsystemet | uppfyllt | UUID-lagringsnycklar, `test_storage_keys_cannot_escape` |
| Uppladdat innehåll körs eller renderas aldrig | uppfyllt | Bilagor med `nosniff`; inga mallar från lagringen |
| Arkivuppackning begränsad | uppfyllt | `.ifczip` med exakt en `.ifc` och storlekstaket på uppackade bytes |
| Tolkning av obetrodda filer isolerad | uppfyllt | IFC-konvertering i en arbetsprocess med tids-, minnes- och entitetsgränser (`test_ifcgraph_convert`) |
| Antivirusskanning av uppladdade filer | ej uppfyllt | Lämnat till operatören (skanna lagringsvolymen); ingen skanner integrerad |

## V6 Autentisering

| Krav | Status | Bevis |
|---|---|---|
| Policy för lösenordslängd och -styrka, inga sammansättningsregler | uppfyllt | `auth/passwords.py`: minst 12 tecken och zxcvbn-poäng ≥ 3 med användarnamnet som känd indata, `test_password_policy_and_hashing` |
| Kontroll mot listor över läckta lösenord | delvis | zxcvbn:s ordlistor över vanliga lösenord; ingen live-uppslagning mot läcklistor |
| Argon2id-hashning | uppfyllt | `pwdlib` med Argon2id, `test_password_policy_and_hashing` |
| Skydd mot brute force med generiska meddelanden | uppfyllt | Hastighetsgräns per adress, konstant meddelande för fel användare eller lösenord, inaktiverade konton avvisas (`test_disabled_user_cannot_sign_in_and_loses_tokens`) |
| Flerfaktorsautentisering | ej uppfyllt | Bara lösenord; TOTP för inloggningssidan är planerat (*Senare* i planen). API-klienter ser aldrig lösenord: de autentiserar sig via OAuth2 mot den här inloggningssidan, så en MFA täcker allt |
| Säker återställning av inloggningsuppgifter | uppfyllt | Ingen självbetjäningsåterställning; en administratör utfärdar ett engångslösenord efter förnyad autentisering, och användaren måste byta det vid nästa inloggning |
| Förnyad autentisering för känsliga operationer | uppfyllt | Eget lösenord krävs för lösenordsbyten, återställningar, ändring av adminflaggan, hemlighetsrotation och borttagning (`test_user_management`, `test_client_management_and_secret_rotation`) |
| Inaktivering av ett konto avslutar dess åtkomst | uppfyllt | Tokens och sessioner återkallas när en användare inaktiveras |

## V7 Sessionshantering

| Krav | Status | Bevis |
|---|---|---|
| Sessioner på serversidan med slumpmässiga identifierare, lagrade hashade | uppfyllt | `web/sessions.py`, 256-bitars kakvärde, SHA-256 i vila |
| Ny session vid inloggning; utloggning förstör den | uppfyllt | `test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Inaktivitets- och absoluta tidsgränser | uppfyllt | `web_session_idle_seconds` och absolut utgång, städas av städaren |
| Användare kan se och avsluta sina sessioner och medgivanden | uppfyllt | `/account`: sessioner, applikationer, "logga ut överallt" |
| Administratörer kan avsluta vilken session eller vilket medgivande som helst | uppfyllt | `/admin/sessions`, `opencde revoke` |

## V8 Behörighet

| Krav | Status | Bevis |
|---|---|---|
| Neka som standard; objektnivåkontroller vid varje åtkomst | uppfyllt | Varje fråga startar i användarnoden och går via `MEMBER_OF`; icke-medlemmar får 404 (`test_topic_authorization_matrix`) |
| Funktionsnivåkontroller per roll, på serversidan | uppfyllt | Roll × handling-matris för projekt, ärenden, kommentarer, viewpoints, dokument; `authorization`-objekt härledda ur samma regler |
| Administrativa funktioner åtskilda och skyddade | uppfyllt | `/admin` kräver adminrollen på varje rutt (`test_admin_pages_need_the_admin_role`) |
| Behörighet avgörs i samma transaktion som ändringen | uppfyllt | Repository-metoder kontrollerar och skriver i en transaktion |
| Exponering på fältnivå begränsad | uppfyllt | Explicita svarsmodeller; hashar och lagringsnycklar finns i inget svar (`validate_documents`, conformance-sviten) |

## V9 Självständiga tokens

ej tillämpligt: tokens är opaka referenser lagrade som hashar (ADR 0002); det
finns inga JWT:er att validera.

## V10 OAuth och OIDC

| Krav | Status | Bevis |
|---|---|---|
| Bara authorization code med PKCE `S256`; inga implicit- eller password-grants | uppfyllt | `test_pkce_is_mandatory_and_plain_is_refused` |
| Exakt matchning av redirect-URI; loopback-undantag enligt RFC 8252 | uppfyllt | `test_unregistered_redirect_uri_is_shown_not_followed`, `test_loopback_port_may_vary_but_host_may_not` |
| `state` krävs; `iss` i svaret | uppfyllt | `test_state_is_required_and_unknown_scope_is_refused`, `test_public_client_flow_with_pkce` |
| Engångskoder bundna till klient, redirect-URI och verifier | uppfyllt | `test_code_is_single_use_and_replay_revokes_tokens`, `test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Rotation av refresh-tokens med upptäckt av återanvändning | uppfyllt | `test_refresh_rotates_and_reuse_revokes_the_family` |
| Återkallning (RFC 7009) | uppfyllt | `test_revocation` |
| Klientautentisering; publika klienter utan hemligheter | uppfyllt | `test_client_authentication_failures` |
| Tokensvar inte cachebara | uppfyllt | `test_token_response_is_never_cached_and_has_spec_fields` |
| Samtyckesskärmen namnger klienten och omdirigeringsmålet; användaren kan neka | uppfyllt | `test_deny_redirects_with_access_denied`, `auth/templates` |
| Dynamisk registrering begränsad | uppfyllt | Avstängd som standard; bara https- eller loopback-omdirigeringar när påslagen; publika registreringar (RFC 7591 `none`) förlitar sig på PKCE och på att samtyckessidan namnger klienten och dess omdirigeringsvärd; hastighetsbegränsad |
| Avsändarbundna tokens (DPoP, mTLS) | ej uppfyllt | Nivå 3-punkt; listad under *Senare* i planen |
| Efterlevnad testad med ett externt verktyg | ej uppfyllt | OAuch-körning beskriven i [pentest-howto.md](pentest-howto.md) §4, att göra före den första produktionsdriftsättningen |

## V11 Kryptografi

| Krav | Status | Bevis |
|---|---|---|
| Godkända algoritmer och CSPRNG | uppfyllt | `secrets` för koder, tokens, kakor och klienthemligheter; Argon2id; SHA-256 för tokenhashar; HMAC-signerade formulärtokens (`itsdangerous`) |
| Hemligheter inte i kod eller avbildningar | uppfyllt | `OPENCDE_SECRET_KEY` och databaslösenordet från miljön eller Docker secrets, genererade av `opencde init`; `.env` ignoreras av git; gitleaks i CI |
| Nyckelrotation | delvis | Att rotera `OPENCDE_SECRET_KEY` ogiltigförklarar formulärtokens och webbläsarsessioner, inget annat; dokumenterat som ett operatörssteg i `docs/sv/deploy/vps-caddy.md`; ingen övergång med dubbla nycklar |

## V12 Säker kommunikation

| Krav | Status | Bevis |
|---|---|---|
| Bara TLS 1.2 eller 1.3, giltiga certifikat, HSTS | uppfyllt | Caddy i `compose.prod.yaml`; produktion vägrar en publik http-URL (`test_settings`); testssl.sh-körning i [pentest-howto.md](pentest-howto.md) §5 före produktion |
| Interna anslutningar skyddade | uppfyllt | Databasen bara på det privata compose-nätet; `neo4j+s://` för en extern databas (`docs/sv/deploy/cloud-aura.md`) |
| Vidarebefordrade huvuden litas på bara från kända proxyer | uppfyllt | `OPENCDE_TRUSTED_PROXIES` |

## V13 Konfiguration

| Krav | Status | Bevis |
|---|---|---|
| Säkra standardvärden; servern vägrar osäkra produktionsinställningar | uppfyllt | `test_settings`: https, databaslösenord och hemlig nyckel krävs i produktion, localhost-omdirigeringar avvisas |
| Beroenden pinnade, granskade och uppdaterade | uppfyllt | `uv.lock`, pip-audit, Dependabot med 7 dagars cooldown, actions pinnade med SHA och kontrollerade av zizmor |
| Härdad container | uppfyllt | Icke-root, skrivskyddat rotfilsystem, borttagna capabilities, `no-new-privileges`, Trivy-skanning med SBOM vid release |
| Driftkontroller | uppfyllt | `opencde doctor` (databas, schema, klocka, publik URL, huvuden, lagring) |
| Administrationsgränssnittet kan isoleras | uppfyllt | Separat inloggning och roll; `OPENCDE_ADMIN_UI_ENABLED=false` tar bort det från en publik instans (administrera via CLI i stället), eller begränsa `/admin` till interna adresser i proxyn |
| Ingen tredjepartskod på produktionssidor | uppfyllt | Serverns sidor laddar inget från andra origins; den interaktiva API-dokumentationen (`/docs`, Swagger UI från ett CDN) serveras bara utanför produktion om inte `OPENCDE_API_DOCS_ENABLED=true` |

## V14 Dataskydd

| Krav | Status | Bevis |
|---|---|---|
| Inga känsliga data i loggar | uppfyllt | Maskeringsprocessor och inga kroppar loggas, `test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Känsliga svar cachas inte | uppfyllt | `Cache-Control: no-store` på varje icke-statiskt svar |
| Inloggningsuppgifter och tokens hashade i vila | uppfyllt | Argon2id och SHA-256 |
| Dataminimering | uppfyllt | Händelsevärden klipps; svarsmodeller bär bara specifikationens fält |
| Säkerhetskopior skyddade | delvis | Export på applikationsnivå (ADR 0006) till operatörens backupvolym; servern krypterar den inte, så volymen eller arkivet måste krypteras av operatören |
| Användare kan tas bort | uppfyllt | Admin-gränssnittet tar bort användare (efter förnyad autentisering) och återkallar deras tokens |

## V15 Säker kodning och arkitektur

| Krav | Status | Bevis |
|---|---|---|
| Dokumenterad arkitektur och hotmodell | uppfyllt | `docs/adr/`, [threat-model.md](threat-model.md), `docs/sv/graph-schema.md` |
| Statisk analys och beroendekontroller i CI | uppfyllt | ruff `S`-regler, Bandit, Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`), pip-audit |
| Inga farliga funktioner eller deserialisering av obetrodda data | uppfyllt | Bara JSON; ingen `pickle`, `eval` eller skalinterpolation (Bandit) |
| Kapplöpningar kring engångshemligheter | uppfyllt | Inlösen av kod och refresh-token är enskilda transaktioner med upptäckt av återanvändning |
| Åtskillnad mellan webbläsargränssnittets och API:ets förtroendegränser | uppfyllt | Kakor bara för sidor, bearer-tokens bara för API:t; ingen av dem accepterar den andra |

## V16 Säkerhetsloggning och felhantering

| Krav | Status | Bevis |
|---|---|---|
| Strukturerade loggar med request-identifierare och tid i UTC | uppfyllt | structlog JSON, `RequestIDMiddleware` |
| Säkerhetshändelser loggas (inloggning, tokenutfärdande, återkallning, adminhandlingar) | uppfyllt | `AuditEvent`-noder, visade i `/admin/audit` med CSV-export |
| Logg på begärandenivå för felsökning utan känsliga data | uppfyllt | Opt-in `RequestLog` (metod, sökväg, operation, status, tid, request-id, bytes, anropare; inga frågesträngar, huvuden eller kroppar), begränsad lagringstid, bara administratörer (`/admin/requests`, `/admin/api/requests` med scopet `admin`) |
| Fel hanteras utan att läcka interna detaljer; oväntade fel loggas | uppfyllt | `errors.py`: specens kropp, 5xx loggas med request-id |
| Korrekt klocka för utgångskontroller | uppfyllt | `opencde doctor` jämför klockan med en NTP-källa |
| Loggskydd, vidarebefordran och larm | ej uppfyllt | Lämnat till operatören (compose-loggdrivrutin, SIEM) |

## V17 WebRTC

ej tillämpligt.

## Kända luckor

| Lucka | Plan |
|---|---|
| Ingen flerfaktorsautentisering på inloggningssidan | TOTP (pyotp) som en senare etapp; en implementation täcker webbläsaranvändare och OAuth2-klienter |
| Sessionskaka utan `__Host-`-prefix | Byt namn på kakan vid nästa kakändring (kräver https överallt, vilket produktion har) |
| Ingen live-kontroll mot läckta lösenord | Valfri k-anonymitetsuppslagning mot ett läck-API som inställning |
| Ingen lagringskvot per användare | Lägg till `max_storage_bytes_per_user` när användning med flera hyresgäster börjar |
| Inga avsändarbundna tokens | DPoP (RFC 9449) som en senare etapp |
| Ingen antivirusskanning | Operatörens val på lagringsvolymen |
| Säkerhetskopior krypteras inte av servern | Kryptera backupvolymen eller omslut `opencde backup` med `age`/`gpg` i sidovagnen |
| OAuch och testssl.sh ännu inte körda mot en driftsättning | Kör före den första produktionsdriftsättningen; dokumentera rapporterna |
| Ingen extern penetrationstest | Valfri, efter ägarens gottfinnande, efter ovanstående |
