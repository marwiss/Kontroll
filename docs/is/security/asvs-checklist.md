# OWASP ASVS stigs 2-gátlisti

Sjálfsmat gegn OWASP Application Security Verification Standard 5.0 á stigi
2, skrifað af þróunaraðilum 2026-11-05. Það er ekki ytri staðfesting. Hver
kafli telur upp stigs 2-kröfurnar sem eiga við þennan þjón (umorðaðar),
stöðuna og sönnunargögnin: vörn í [controls.md](controls.md) með prófi sínu,
skjal eða kóða. Þekktum götum er safnað í lokin; þeim er fylgt sem *Síðar* í
verkáætluninni.

Staða: **uppfyllt** (vörn og próf til), **að hluta** (vörn til með skjalfestri
takmörkun), **ekki uppfyllt** (áætlað eða eftirlátið rekstraraðila), **á
ekki við** (þjónninn hefur enga slíka einingu).

## V1 Kóðun og hreinsun

| Krafa | Staða | Sönnun |
|---|---|---|
| Úttakskóðun fyrir HTML; engin DOM-innspýting þjónsgagna | uppfyllt | Jinja2 autoescape, viðbótarskriftur nota aðeins `textContent`, strangt CSP sem dýptarvörn; `tests/ui` fellur á stjórnborðsvillum |
| Gagnagrunnsfyrirspurnir eru aldrei byggðar úr inntaki | uppfyllt | Aðeins Cypher-stikar, framfylgt með lint-prófinu `test_core_helpers::test_dialect_ddl_and_cypher_lint`; IFC-merkimiðar sannreyndir sem auðkenni (`importer._safe`) |
| Fyrirspurnarmál sem biðlurum eru sýnd eru þáttuð, ekki innfelld | uppfyllt | OData: þáttari → AST → hvítlisti sviða → stikar, `test_odata` |
| Skráarheiti og hausagildi hreinsuð og kóðuð | uppfyllt | `sanitize_filename`, RFC 8187 `attachment_header`, `test_bcf_helpers` |
| URL frá biðlurum sannreynd (skema, hýsill) fyrir notkun | uppfyllt | `validate_redirect_uri` (https, loopback, einkaskemu), callback og skjalatilvísanir aðeins http(s) |

## V2 Sannprófun og viðskiptarökfræði

| Krafa | Staða | Sönnun |
|---|---|---|
| Jákvæð sannprófun með mörkum á öllu inntaki | uppfyllt | Pydantic v2-líkön með lengdar-, lista- og dýptarmörkum, endanlegar tölur; óþekkt svið hunsuð samkvæmt Foundation API 1.8 |
| Viðskiptareglum framfylgt þjónsmegin | uppfyllt | Málagildi gegn extensions, nákvæmlega ein myndavél, 409 við eyðingu viewpoint sem vísað er í, tvítekin guid, ein færsla á hvert skrif |
| Varnir gegn sjálfvirkni við auðkenningu og kostnaðarsamar aðgerðir | að hluta | Innskráningar- og tókaendapunktar tíðnitakmarkaðir á hvert vistfang (`test_sign_in_is_rate_limited`), og misheppnaðar innskráningar láta notandanafnið bíða (`test_sign_in_throttle`); upphöl takmörkuð á hverja skrá (`max_upload_bytes`); enginn geymslukvóti á hvern notanda enn |

## V3 Öryggi vefframenda

| Krafa | Staða | Sönnun |
|---|---|---|
| Content Security Policy án `unsafe-inline`, römmun neitað | uppfyllt | `default-src 'none'` á API-svörum, `default-src 'self'; frame-ancestors 'none'` á síðum; engar innfelldar skriftur eða stílar; `X-Frame-Options: DENY` |
| Vefkökur `HttpOnly`, `Secure`, `SameSite=Strict` | að hluta | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it`; vefkakan hefur ekki `__Host-`-forskeyti enn |
| CSRF-vörn við hverja stöðubreytingu frá vafra | uppfyllt | Undirritaðir, tilgangsbundnir eyðublaðstókar auk `Sec-Fetch-Site`/`Origin`-athugana, `test_csrf_protections_on_admin_forms`, `test_cross_site_posts_are_refused_and_next_cannot_leave_the_site` |
| Öryggishausar vafra á hverju svari | uppfyllt | `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy: same-origin` á stjórnunar- og reikningssíðunum (síðurnar sem biðlari opnar í sprettiglugga halda sjálfgefnu vafrans svo sprettiglugginn haldi opener sínum), `test_headers_and_errors` |
| HSTS | uppfyllt | Bætt við af Caddy í framleiðsluyfirlaginu (`Caddyfile`) |
| Engin viðkvæm gögn í URL | að hluta | Tókar og lykilorð ferðast aðeins í hausum og meginmálum; Documents API-forskriftin setur einnota tengilstóka í `upload_ui_url`/`select_documents_url`, svo hann er 256 bitar, geymdur tættur, gildur í 10 mínútur og síðan krefst auk þess vafrasetu sem sami notandi |

## V4 API og vefþjónusta

| Krafa | Staða | Sönnun |
|---|---|---|
| JSON-forritaskil sannreyna innihaldsgerðir og hafna óstuddum aðferðum | uppfyllt | FastAPI-þáttun með villumeginmáli forskriftarinnar, 405 á aðrar aðferðir; Schemathesis `unsupported_method` í næturkeyrslunni |
| CORS takmarkað; aldrei credentials með algildistákni | uppfyllt | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials` |
| Samræmt villusnið án innri upplýsinga | uppfyllt | Aðeins `{"message": …}`, `test_headers_and_errors` |
| Auðkenning á hverri API-aðgerð; aðeins Bearer | uppfyllt | `test_foundation::test_current_user_requires_a_bearer_token`, öryggissvítan |
| Samningsfuzz: ekkert 5xx, svör passa við skjalfest skemu, ógildu inntaki hafnað | uppfyllt | `tests/e2e/test_schemathesis.py` (hver aðgerð, jákvæð og neikvæð myndun) |

## V5 Skráameðhöndlun

| Krafa | Staða | Sönnun |
|---|---|---|
| Stærðarmörk á bætunum sem raunverulega berast | uppfyllt | Streymandi skrif telja bæti; chunked-meginmál klippt; `test_storage_stream_counts_bytes`, `test_chunked_body_over_the_limit_is_cut_off` |
| Skráargerð ákveðin af innihaldi, ekki af biðlara | uppfyllt | Magic bytes fyrir myndir; skjöl geymd og veitt sem `application/octet-stream` |
| Skráarheiti biðlara ná aldrei í skráakerfið | uppfyllt | UUID-geymslulyklar, `test_storage_keys_cannot_escape` |
| Upphlaðið innihald aldrei keyrt eða birt | uppfyllt | Viðhengi með `nosniff`; engin sniðmát úr geymslu |
| Útpökkun safnskráa afmörkuð | uppfyllt | `.ifczip` með nákvæmlega einni `.ifc` og stærðarþaki á útpökkuð bæti |
| Þáttun ótraustra skráa einangruð | uppfyllt | IFC-umbreyting í vinnuferli með tíma-, minnis- og einingamörkum (`test_ifcgraph_convert`) |
| Vírusskönnun upphlaðinna skráa | ekki uppfyllt | Eftirlátið rekstraraðila (skanna geymslurýmið); enginn skanni samþættur |

## V6 Auðkenning

| Krafa | Staða | Sönnun |
|---|---|---|
| Stefna um lengd og styrk lykilorða, engar samsetningarreglur | uppfyllt | `auth/passwords.py`: minnst 12 tákn og zxcvbn-einkunn ≥ 3 með notandanafnið sem þekkt inntak, `test_password_policy_and_hashing` |
| Athugun gegn listum yfir lekin lykilorð | að hluta | Orðabækur zxcvbn yfir algeng lykilorð; engin lifandi uppfletting í lekalistum |
| Argon2id-tæting | uppfyllt | `pwdlib` með Argon2id, `test_password_policy_and_hashing` |
| Vörn gegn brute force með almennum skilaboðum | uppfyllt | Tíðnimörk á hvert vistfang, vaxandi bið á hvert notandanafn, föst skilaboð við rangan notanda eða lykilorð, óvirkum reikningum hafnað (`test_disabled_user_cannot_sign_in_and_loses_tokens`) |
| Fjölþátta auðkenning | ekki uppfyllt | Aðeins lykilorð; TOTP fyrir innskráningarsíðuna er áætlað (*Síðar* í áætluninni). API-biðlarar sjá aldrei lykilorð: þeir auðkenna sig um OAuth2 gegn þessari innskráningarsíðu, svo ein MFA nær yfir allt |
| Örugg endurheimt innskráningarupplýsinga | uppfyllt | Engin sjálfsafgreiðsla endurstillinga; stjórnandi gefur út einnota lykilorð eftir endurauðkenningu, og notandinn þarf að breyta því við næstu innskráningu |
| Endurauðkenning fyrir viðkvæmar aðgerðir | uppfyllt | Eigið lykilorð krafist við lykilorðsbreytingar, endurstillingar, breytingar stjórnandamerkis, skipti leyndarmála og eyðingu (`test_user_management`, `test_client_management_and_secret_rotation`) |
| Að gera reikning óvirkan lýkur aðgangi hans | uppfyllt | Tókar og setur afturkölluð þegar notandi er gerður óvirkur |

## V7 Setustjórnun

| Krafa | Staða | Sönnun |
|---|---|---|
| Setur þjónsmegin með slembnum auðkennum, geymd tætt | uppfyllt | `web/sessions.py`, 256-bita vefkökugildi, SHA-256 í hvíld |
| Ný seta við innskráningu; útskráning eyðir henni | uppfyllt | `test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Aðgerðaleysis- og heildartímamörk | uppfyllt | `web_session_idle_seconds` og heildargildistími, hreinsað af hreinsuninni |
| Notendur geta séð og lokið setum sínum og heimildum | uppfyllt | `/account`: setur, forrit, „skrá út alls staðar“ |
| Stjórnendur geta lokið hverri setu eða heimild | uppfyllt | `/admin/sessions`, `opencde revoke` |

## V8 Heimildir

| Krafa | Staða | Sönnun |
|---|---|---|
| Neita sjálfgefið; athuganir á hlutastigi við hvern aðgang | uppfyllt | Hver fyrirspurn hefst í notandahnútnum og fer um `MEMBER_OF`; þeir sem ekki eru meðlimir fá 404 (`test_topic_authorization_matrix`) |
| Athuganir á aðgerðastigi eftir hlutverki, þjónsmegin | uppfyllt | Hlutverk × aðgerð-fylki fyrir verkefni, mál, athugasemdir, viewpoint, skjöl; `authorization`-hlutir leiddir af sömu reglum |
| Stjórnunaraðgerðir aðskildar og varðar | uppfyllt | `/admin` krefst stjórnandahlutverks á hverri leið (`test_admin_pages_need_the_admin_role`) |
| Heimild ákveðin í sömu færslu og breytingin | uppfyllt | Repository-aðferðir athuga og skrifa í einni færslu |
| Birting á sviðsstigi takmörkuð | uppfyllt | Skýr svarlíkön; tætigildi og geymslulyklar eru í engu svari (`validate_documents`, samræmissvítan) |

## V9 Sjálfstæðir tókar

á ekki við: tókar eru ógegnsæjar tilvísanir geymdar sem tætigildi (ADR 0002);
engin JWT til að sannreyna.

## V10 OAuth og OIDC

| Krafa | Staða | Sönnun |
|---|---|---|
| Aðeins authorization code með PKCE `S256`; engar implicit- eða password-veitingar | uppfyllt | `test_pkce_is_mandatory_and_plain_is_refused` |
| Nákvæm samsvörun redirect-URI; loopback-undantekning samkvæmt RFC 8252 | uppfyllt | `test_unregistered_redirect_uri_is_shown_not_followed`, `test_loopback_port_may_vary_but_host_may_not` |
| `state` krafist; `iss` í svarinu | uppfyllt | `test_state_is_required_and_unknown_scope_is_refused`, `test_public_client_flow_with_pkce` |
| Einnota kóðar bundnir við biðlara, redirect-URI og verifier | uppfyllt | `test_code_is_single_use_and_replay_revokes_tokens`, `test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Skipti endurnýjunartóka með greiningu endurnotkunar | uppfyllt | `test_refresh_rotates_and_reuse_revokes_the_family` |
| Afturköllun (RFC 7009) | uppfyllt | `test_revocation` |
| Auðkenning biðlara; opinberir biðlarar án leyndarmála | uppfyllt | `test_client_authentication_failures` |
| Tókasvör ekki geymanleg í skyndiminni | uppfyllt | `test_token_response_is_never_cached_and_has_spec_fields` |
| Samþykkisskjárinn nefnir biðlarann og áframsendingarmarkið; notandinn getur neitað | uppfyllt | `test_deny_redirects_with_access_denied`, `auth/templates` |
| Kvik skráning takmörkuð | uppfyllt | Óvirk sjálfgefið; aðeins https- eða loopback-áframsendingar þegar virk; opinberar skráningar (RFC 7591 `none`) reiða sig á PKCE og á að samþykkissíðan nefni biðlarann og áframsendingarhýsil hans; tíðnitakmörkuð; upphafsaðgangstóki og samþykki stjórnanda eru valkostir |
| Sendandabundnir tókar (DPoP, mTLS) | ekki uppfyllt | Atriði á stigi 3; talið upp undir *Síðar* í áætluninni |
| Samræmi prófað með ytra tóli | ekki uppfyllt | OAuch-keyrsla lýst í [pentest-howto.md](pentest-howto.md) §4, á að gera fyrir fyrstu framleiðsluuppsetningu |

## V11 Dulritun

| Krafa | Staða | Sönnun |
|---|---|---|
| Viðurkenndir reiknirit og CSPRNG | uppfyllt | `secrets` fyrir kóða, tóka, vefkökur og biðlaraleyndarmál; Argon2id; SHA-256 fyrir tætigildi tóka; HMAC-undirritaðir eyðublaðstókar (`itsdangerous`) |
| Leyndarmál ekki í kóða eða myndum | uppfyllt | `OPENCDE_SECRET_KEY` og lykilorð gagnagrunnsins úr umhverfinu eða Docker secrets, búin til af `opencde init`; `.env` hunsuð af git; gitleaks í CI |
| Lyklaskipti | að hluta | Að skipta um `OPENCDE_SECRET_KEY` ógildir eyðublaðstóka og vafrasetur, ekkert annað; skjalfest sem skref rekstraraðila í `docs/is/deploy/vps-caddy.md`; engin tvílykla yfirfærsla |

## V12 Örugg samskipti

| Krafa | Staða | Sönnun |
|---|---|---|
| Aðeins TLS 1.2 eða 1.3, gild skilríki, HSTS | uppfyllt | Caddy í `compose.prod.yaml`; framleiðsla neitar opinberri http-URL (`test_settings`); testssl.sh-keyrsla í [pentest-howto.md](pentest-howto.md) §5 fyrir framleiðslu |
| Innri tengingar varðar | uppfyllt | Gagnagrunnur aðeins á einkaneti compose; `neo4j+s://` fyrir ytri gagnagrunn (`docs/is/deploy/cloud-aura.md`) |
| Áframsendum hausum aðeins treyst frá þekktum milliþjónum | uppfyllt | `OPENCDE_TRUSTED_PROXIES` |

## V13 Stillingar

| Krafa | Staða | Sönnun |
|---|---|---|
| Öruggar sjálfgefnar stillingar; þjónninn neitar óöruggum framleiðslustillingum | uppfyllt | `test_settings`: https, lykilorð gagnagrunns og leynilykill krafist í framleiðslu, localhost-áframsendingum hafnað |
| Ósjálfstæði fest, endurskoðuð og uppfærð | uppfyllt | `uv.lock`, pip-audit, Dependabot með 7 daga cooldown, actions fest með SHA og athuguð af zizmor |
| Hertur gámur | uppfyllt | Ekki-root, skrifvarið rótarskráakerfi, afnumin capabilities, `no-new-privileges`, Trivy-skönnun með SBOM við útgáfu |
| Rekstrarathuganir | uppfyllt | `opencde doctor` (gagnagrunnur, skema, klukka, opinber URL, hausar, geymsla) |
| Stjórnunarviðmótið má einangra | uppfyllt | Aðskilin innskráning og hlutverk; `OPENCDE_ADMIN_UI_ENABLED=false` fjarlægir það af opinberu tilviki (stjórnaðu um CLI í staðinn), eða takmarkaðu `/admin` við innri vistföng í milliþjóninum |
| Enginn kóði þriðja aðila á framleiðslusíðum | uppfyllt | Síður þjónsins hlaða engu frá öðrum upprunum; gagnvirka API-skjölunin (`/docs`, Swagger UI frá CDN) er aðeins veitt utan framleiðslu nema `OPENCDE_API_DOCS_ENABLED=true` |

## V14 Gagnavernd

| Krafa | Staða | Sönnun |
|---|---|---|
| Engin viðkvæm gögn í atvikaskrám | uppfyllt | Hulningarvinnsla og engin meginmál skráð, `test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Viðkvæm svör ekki geymd í skyndiminni | uppfyllt | `Cache-Control: no-store` á hverju svari sem ekki er kyrrstætt |
| Innskráningarupplýsingar og tókar tættir í hvíld | uppfyllt | Argon2id og SHA-256 |
| Lágmörkun gagna | uppfyllt | Atburðagildi klippt; svarlíkön bera aðeins svið forskriftarinnar |
| Öryggisafrit varin | að hluta | Útflutningur á forritastigi (ADR 0006) í öryggisafritsgeymslu rekstraraðilans; þjónninn dulkóðar hann ekki, svo rekstraraðilinn þarf að dulkóða geymsluna eða safnskrána |
| Notendur má fjarlægja | uppfyllt | Stjórnunarviðmótið eyðir notendum (eftir endurauðkenningu) og afturkallar tóka þeirra |

## V15 Örugg kóðun og hönnun

| Krafa | Staða | Sönnun |
|---|---|---|
| Skjalfest hönnun og ógnarlíkan | uppfyllt | `docs/adr/`, [threat-model.md](threat-model.md), `docs/is/graph-schema.md` |
| Kyrrstæð greining og athuganir ósjálfstæða í CI | uppfyllt | ruff `S`-reglur, Bandit, Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`), pip-audit |
| Engar hættulegar aðgerðir eða afraðgerð ótraustra gagna | uppfyllt | Aðeins JSON; ekkert `pickle`, `eval` eða skeljarinnfelling (Bandit) |
| Kapphlaupsástand um einnota leyndarmál | uppfyllt | Innlausn kóða og endurnýjunartóka eru stakar færslur með greiningu endurnotkunar |
| Aðskilnaður trúnaðarmarka vafraviðmóts og API | uppfyllt | Vefkökur aðeins fyrir síður, bearer-tókar aðeins fyrir forritaskilin; hvorugt tekur við hinu |

## V16 Öryggisskráning og villumeðhöndlun

| Krafa | Staða | Sönnun |
|---|---|---|
| Skipulagðar atvikaskrár með request-auðkenni og tíma í UTC | uppfyllt | structlog JSON, `RequestIDMiddleware` |
| Öryggisatburðir skráðir (innskráning, útgáfa tóka, afturköllun, stjórnunaraðgerðir) | uppfyllt | `AuditEvent`-hnútar, sýndir á `/admin/audit` með CSV-útflutningi |
| Skrá á beiðnastigi til villuleitar án viðkvæmra gagna | uppfyllt | Valkvæð `RequestLog` (aðferð, slóð, aðgerð, staða, tímalengd, request-id, bæti, sá sem kallaði; engir fyrirspurnarstrengir, hausar eða meginmál), afmörkuð varðveisla, aðeins stjórnendur (`/admin/requests`, `/admin/api/requests` með heimildinni `admin`) |
| Villur meðhöndlaðar án þess að leka innri upplýsingum; óvæntar villur skráðar | uppfyllt | `errors.py`: meginmál forskriftarinnar, 5xx skráð með request-id |
| Rétt klukka fyrir gildistímaathuganir | uppfyllt | `opencde doctor` ber klukkuna saman við NTP-uppsprettu |
| Vernd, áframsending og viðvaranir atvikaskráa | ekki uppfyllt | Eftirlátið rekstraraðila (compose-skráarrekill, SIEM) |

## V17 WebRTC

á ekki við.

## Þekkt göt

| Gat | Áætlun |
|---|---|
| Engin fjölþátta auðkenning á innskráningarsíðunni | TOTP (pyotp) sem síðari áfangi; ein útfærsla nær yfir vafranotendur og OAuth2-biðlara |
| Setuvefkaka án `__Host-`-forskeytis | Endurnefna vefkökuna við næstu vefkökubreytingu (krefst https alls staðar, sem framleiðsla hefur) |
| Engin lifandi athugun gegn leknum lykilorðum | Valkvæð k-nafnleyndaruppfletting í leka-API sem stilling |
| Enginn geymslukvóti á hvern notanda | Bæta við `max_storage_bytes_per_user` þegar notkun margra leigjenda hefst |
| Engir sendandabundnir tókar | DPoP (RFC 9449) sem síðari áfangi |
| Engin vírusskönnun | Val rekstraraðila á geymslurýminu |
| Öryggisafrit ekki dulkóðuð af þjóninum | Dulkóða öryggisafritsgeymsluna eða vefja `opencde backup` með `age`/`gpg` í hliðargámnum |
| OAuch og testssl.sh ekki enn keyrð gegn uppsetningu | Keyra fyrir fyrstu framleiðsluuppsetningu; skrá skýrslurnar |
| Engin ytri innbrotsprófun | Valkvæð, að mati eigandans, eftir ofangreint |
