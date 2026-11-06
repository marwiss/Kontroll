# OWASP ASVS tason 2 tarkistuslista

Itsearviointi OWASP Application Security Verification Standard 5.0:n tasoa 2
vasten, kehittäjien kirjoittama 2026-11-05. Se ei ole ulkoinen todennus.
Jokainen luku luettelee tätä palvelinta koskevat tason 2 vaatimukset
(mukaillen), tilan ja todisteet: kontrollin tiedostossa
[controls.md](controls.md) testinsä kanssa, dokumentin tai koodin. Tunnetut
puutteet on koottu loppuun; niitä seurataan projektisuunnitelman kohdassa
*Myöhemmin*.

Tila: **täyttyy** (kontrolli ja testi ovat olemassa), **osittain** (kontrolli
on olemassa dokumentoidulla rajoituksella), **ei täyty** (suunniteltu tai
jätetty ylläpitäjälle), **ei sovellu** (palvelimella ei ole tällaista
komponenttia).

## V1 Koodaus ja puhdistus

| Vaatimus | Tila | Todiste |
|---|---|---|
| HTML:n tulostekoodaus; ei palvelindatan DOM-injektiota | täyttyy | Jinja2 autoescape, parannusskriptit käyttävät vain `textContent`-kutsua, tiukka CSP syvyyspuolustuksena; `tests/ui` epäonnistuu konsolivirheistä |
| Tietokantakyselyjä ei koskaan rakenneta syötteestä | täyttyy | Vain Cypher-parametrit, pakotettu lint-testillä `test_core_helpers::test_dialect_ddl_and_cypher_lint`; IFC-nimiöt validoidaan tunnisteina (`importer._safe`) |
| Asiakkaille näkyvät kyselykielet jäsennetään, ei interpoloida | täyttyy | OData: jäsennin → AST → kenttien sallittujen lista → parametrit, `test_odata` |
| Tiedostonimet ja otsakearvot puhdistetaan ja koodataan | täyttyy | `sanitize_filename`, RFC 8187 `attachment_header`, `test_bcf_helpers` |
| Asiakkaiden URLit validoidaan (skeema, isäntä) ennen käyttöä | täyttyy | `validate_redirect_uri` (https, loopback, yksityiset skeemat), callbackit ja asiakirjaviittaukset vain http(s) |

## V2 Validointi ja liiketoimintalogiikka

| Vaatimus | Tila | Todiste |
|---|---|---|
| Positiivinen validointi rajoin jokaiselle syötteelle | täyttyy | Pydantic v2 -mallit pituus-, lista- ja syvyysrajoin, äärelliset luvut; tuntemattomat kentät ohitetaan Foundation API 1.8:n mukaan |
| Liiketoimintasäännöt pakotetaan palvelinpuolella | täyttyy | Asioiden arvot extensions-listoja vasten, tasan yksi kamera, 409 viitatun viewpointin poistossa, päällekkäiset guidit, yksi transaktio kirjoitusta kohti |
| Automaation esto todennuksessa ja kalliissa operaatioissa | osittain | Kirjautumis- ja token-päätepisteet nopeusrajoitettu osoitetta kohti (`test_sign_in_is_rate_limited`), ja epäonnistuneet kirjautumiset saavat käyttäjätunnuksen odottamaan (`test_sign_in_throttle`); lähetykset rajattu tiedostoa kohti (`max_upload_bytes`); ei vielä käyttäjäkohtaista tallennuskiintiötä |

## V3 Web-käyttöliittymän turvallisuus

| Vaatimus | Tila | Todiste |
|---|---|---|
| Content Security Policy ilman `unsafe-inline`-arvoa, kehystys estetty | täyttyy | `default-src 'none'` rajapintavastauksissa, `default-src 'self'; frame-ancestors 'none'` sivuilla; ei inline-skriptejä tai -tyylejä; `X-Frame-Options: DENY` |
| Evästeet `HttpOnly`, `Secure`, `SameSite=Strict` | osittain | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it`; evästeellä ei ole vielä `__Host-`-etuliitettä |
| CSRF-suojaus jokaisessa selaimesta tulevassa tilanmuutoksessa | täyttyy | Allekirjoitetut, käyttötarkoitukseen sidotut lomaketokenit sekä `Sec-Fetch-Site`/`Origin`-tarkistukset, `test_csrf_protections_on_admin_forms`, `test_cross_site_posts_are_refused_and_next_cannot_leave_the_site` |
| Selaimen turvaotsakkeet jokaisessa vastauksessa | täyttyy | `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy: same-origin` hallinta- ja tilisivuilla (sivut, jotka asiakas avaa ponnahdusikkunaan, säilyttävät selaimen oletuksen, jotta ponnahdusikkuna säilyttää openerinsa), `test_headers_and_errors` |
| HSTS | täyttyy | Caddy lisää tuotantopäällysteessä (`Caddyfile`) |
| Ei arkaluonteista dataa URLeissa | osittain | Tokenit ja salasanat kulkevat vain otsakkeissa ja rungoissa; Documents API -spesifikaatio sijoittaa kertakäyttöisen linkkitokenin kenttiin `upload_ui_url`/`select_documents_url`, joten se on 256-bittinen, tallennettu tiivisteenä, voimassa 10 minuuttia, ja sivu vaatii lisäksi selainistunnon samana käyttäjänä |

## V4 Rajapinta ja web-palvelu

| Vaatimus | Tila | Todiste |
|---|---|---|
| JSON-rajapinnat validoivat sisältötyypit ja hylkäävät tukemattomat metodit | täyttyy | FastAPI-jäsennys spesifikaation virherungolla, 405 muille metodeille; Schemathesis `unsupported_method` yöajossa |
| CORS rajattu; ei koskaan credentialseja jokerimerkin kanssa | täyttyy | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials` |
| Yhtenäinen virhemuoto ilman sisäisiä tietoja | täyttyy | Vain `{"message": …}`, `test_headers_and_errors` |
| Todennus jokaisessa rajapintaoperaatiossa; vain Bearer | täyttyy | `test_foundation::test_current_user_requires_a_bearer_token`, turvallisuussarja |
| Sopimusfuzzaus: ei 5xx:ää, vastaukset vastaavat dokumentoituja skeemoja, virheellinen syöte hylätään | täyttyy | `tests/e2e/test_schemathesis.py` (jokainen operaatio, positiivinen ja negatiivinen generointi) |

## V5 Tiedostojen käsittely

| Vaatimus | Tila | Todiste |
|---|---|---|
| Kokorajat todellisuudessa vastaanotetuille tavuille | täyttyy | Suoratoistokirjoitukset laskevat tavut; chunked-rungot katkaistaan; `test_storage_stream_counts_bytes`, `test_chunked_body_over_the_limit_is_cut_off` |
| Tiedostotyyppi päätetään sisällöstä, ei asiakkaan ilmoituksesta | täyttyy | Magic bytes kuville; asiakirjat tallennetaan ja tarjoillaan `application/octet-stream`-tyyppinä |
| Asiakkaan tiedostonimet eivät koskaan päädy tiedostojärjestelmään | täyttyy | UUID-tallennusavaimet, `test_storage_keys_cannot_escape` |
| Lähetettyä sisältöä ei koskaan suoriteta tai renderöidä | täyttyy | Liitteet `nosniff`-otsakkeella; ei malleja tallennustilasta |
| Arkistojen purku rajattu | täyttyy | `.ifczip`, jossa tasan yksi `.ifc`, ja kokoraja puretuille tavuille |
| Epäluotettavien tiedostojen jäsennys eristetty | täyttyy | IFC-muunnos työprosessissa aika-, muisti- ja entiteettirajoin (`test_ifcgraph_convert`) |
| Lähetettyjen tiedostojen virustarkistus | ei täyty | Jätetty ylläpitäjälle (skannaa tallennustaltio); skanneria ei ole integroitu |

## V6 Todennus

| Vaatimus | Tila | Todiste |
|---|---|---|
| Salasanan pituus- ja vahvuuskäytäntö, ei koostumussääntöjä | täyttyy | `auth/passwords.py`: vähintään 12 merkkiä ja zxcvbn-pisteet ≥ 3 käyttäjätunnus tunnettuna syötteenä, `test_password_policy_and_hashing` |
| Tarkistus vuotaneiden salasanojen listoja vasten | osittain | zxcvbn:n yleisten salasanojen sanastot; ei live-hakua vuotolistoista |
| Argon2id-tiivistys | täyttyy | `pwdlib` ja Argon2id, `test_password_policy_and_hashing` |
| Brute force -suojaus yleisin viestein | täyttyy | Nopeusraja osoitetta kohti, kasvava odotus käyttäjätunnusta kohti, vakioviesti väärästä käyttäjästä tai salasanasta, käytöstä poistetut tilit hylätään (`test_disabled_user_cannot_sign_in_and_loses_tokens`) |
| Monivaiheinen todennus | ei täyty | Vain salasanat; TOTP kirjautumissivulle on suunniteltu (*Myöhemmin* suunnitelmassa). Rajapinta-asiakkaat eivät koskaan näe salasanoja: ne todentautuvat OAuth2:n kautta tätä kirjautumissivua vasten, joten yksi MFA kattaa kaiken |
| Turvallinen tunnistetietojen palautus | täyttyy | Ei itsepalvelunollausta; järjestelmänvalvoja myöntää kertakäyttöisen salasanan uudelleentodennuksen jälkeen, ja käyttäjän on vaihdettava se seuraavassa kirjautumisessa |
| Uudelleentodennus arkaluonteisissa operaatioissa | täyttyy | Oma salasana vaaditaan salasanan vaihtoihin, nollauksiin, hallintamerkinnän muutoksiin, salaisuuden kierrätykseen ja poistoon (`test_user_management`, `test_client_management_and_secret_rotation`) |
| Tilin käytöstä poisto päättää sen pääsyn | täyttyy | Tokenit ja istunnot perutaan, kun käyttäjä poistetaan käytöstä |

## V7 Istunnonhallinta

| Vaatimus | Tila | Todiste |
|---|---|---|
| Palvelinpuolen istunnot satunnaisin tunnistein, tallennettu tiivisteinä | täyttyy | `web/sessions.py`, 256-bittinen evästearvo, SHA-256 levossa |
| Uusi istunto kirjautuessa; uloskirjautuminen tuhoaa sen | täyttyy | `test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Joutoajan ja absoluuttiset aikakatkaisut | täyttyy | `web_session_idle_seconds` ja absoluuttinen vanheneminen, siivooja poistaa |
| Käyttäjät voivat nähdä ja päättää istuntonsa ja valtuutuksensa | täyttyy | `/account`: istunnot, sovellukset, "kirjaudu ulos kaikkialta" |
| Järjestelmänvalvojat voivat päättää minkä tahansa istunnon tai valtuutuksen | täyttyy | `/admin/sessions`, `opencde revoke` |

## V8 Valtuutus

| Vaatimus | Tila | Todiste |
|---|---|---|
| Oletuksena esto; objektitason tarkistukset jokaisessa käytössä | täyttyy | Jokainen kysely alkaa käyttäjäsolmusta ja kulkee `MEMBER_OF`-suhteen kautta; ei-jäsenet saavat 404 (`test_topic_authorization_matrix`) |
| Toimintotason tarkistukset roolin mukaan, palvelinpuolella | täyttyy | Rooli × toiminto -matriisi projekteille, asioille, kommenteille, viewpointeille, asiakirjoille; `authorization`-objektit johdettu samoista säännöistä |
| Hallintatoiminnot erotettu ja suojattu | täyttyy | `/admin` vaatii hallintaroolin jokaisella reitillä (`test_admin_pages_need_the_admin_role`) |
| Valtuutus päätetään samassa transaktiossa kuin muutos | täyttyy | Repository-metodit tarkistavat ja kirjoittavat yhdessä transaktiossa |
| Kenttätason paljastuminen rajattu | täyttyy | Eksplisiittiset vastausmallit; tiivisteet ja tallennusavaimet eivät ole missään vastauksessa (`validate_documents`, conformance-sarja) |

## V9 Itsenäiset tokenit

ei sovellu: tokenit ovat opaakkeja viittauksia, jotka tallennetaan
tiivisteinä (ADR 0002); ei ole JWT:itä validoitavaksi.

## V10 OAuth ja OIDC

| Vaatimus | Tila | Todiste |
|---|---|---|
| Vain authorization code PKCE `S256`:lla, paitsi luottamukselliselle asiakkaalle, jonka ylläpitäjä on merkinnyt; ei implicit- tai password-granteja | täyttyy | `test_pkce_is_mandatory_and_plain_is_refused` |
| Redirect-URIn tarkka vastaavuus; loopback-poikkeus RFC 8252:n mukaan | täyttyy | `test_unregistered_redirect_uri_is_shown_not_followed`, `test_loopback_port_may_vary_but_host_may_not` |
| `state` vaaditaan; `iss` vastauksessa | täyttyy | `test_state_is_required_and_unknown_scope_is_refused`, `test_public_client_flow_with_pkce` |
| Kertakäyttöiset koodit sidottu asiakkaaseen, redirect-URIin ja verifieriin | täyttyy | `test_code_is_single_use_and_replay_revokes_tokens`, `test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Refresh-tokenien kierto ja uudelleenkäytön tunnistus | täyttyy | `test_refresh_rotates_and_reuse_revokes_the_family` |
| Peruutus (RFC 7009) | täyttyy | `test_revocation` |
| Asiakkaan todennus; julkiset asiakkaat ilman salaisuuksia | täyttyy | `test_client_authentication_failures` |
| Tokenvastaukset eivät välimuistitettavia | täyttyy | `test_token_response_is_never_cached_and_has_spec_fields` |
| Suostumusnäyttö nimeää asiakkaan ja uudelleenohjauksen kohteen; käyttäjä voi kieltäytyä | täyttyy | `test_deny_redirects_with_access_denied`, `auth/templates` |
| Dynaaminen rekisteröinti rajoitettu | täyttyy | Oletuksena pois päältä; vain https- tai loopback-uudelleenohjaukset, kun päällä; julkiset rekisteröinnit (RFC 7591 `none`) nojaavat PKCE:hen ja siihen, että suostumussivu nimeää asiakkaan ja sen uudelleenohjausisännän; nopeusrajoitettu; alustava pääsytunniste ja järjestelmänvalvojan hyväksyntä ovat valinnaisia |
| Lähettäjään sidotut tokenit (DPoP, mTLS) | ei täyty | Tason 3 kohta; listattu suunnitelman kohdassa *Myöhemmin* |
| Yhdenmukaisuus testattu ulkoisella työkalulla | ei täyty | OAuch-ajo kuvattu tiedostossa [pentest-howto.md](pentest-howto.md) §4, tehtävä ennen ensimmäistä tuotantoasennusta |

## V11 Kryptografia

| Vaatimus | Tila | Todiste |
|---|---|---|
| Hyväksytyt algoritmit ja CSPRNG | täyttyy | `secrets` koodeille, tokeneille, evästeille ja asiakassalaisuuksille; Argon2id; SHA-256 tokenien tiivisteille; HMAC-allekirjoitetut lomaketokenit (`itsdangerous`) |
| Salaisuudet eivät koodissa tai kuvissa | täyttyy | `OPENCDE_SECRET_KEY` ja tietokannan salasana ympäristöstä tai Docker secreteistä, `opencde init`-komennon luomat; `.env` gitin ohittama; gitleaks CI:ssä |
| Avainten kierrätys | osittain | `OPENCDE_SECRET_KEY`-avaimen kierrätys mitätöi lomaketokenit ja selainistunnot, ei muuta; dokumentoitu ylläpitäjän askeleena tiedostossa `docs/fi/deploy/vps-caddy.md`; ei kahden avaimen siirtymää |

## V12 Turvallinen viestintä

| Vaatimus | Tila | Todiste |
|---|---|---|
| Vain TLS 1.2 tai 1.3, voimassa olevat varmenteet, HSTS | täyttyy | Caddy tiedostossa `compose.prod.yaml`; tuotanto kieltäytyy http-muotoisesta julkisesta URLista (`test_settings`); testssl.sh-ajo tiedostossa [pentest-howto.md](pentest-howto.md) §5 ennen tuotantoa |
| Sisäiset yhteydet suojattu | täyttyy | Tietokanta vain yksityisessä compose-verkossa; `neo4j+s://` ulkoiselle tietokannalle (`docs/fi/deploy/cloud-aura.md`) |
| Välitettyihin otsakkeisiin luotetaan vain tunnetuilta välityspalvelimilta | täyttyy | `OPENCDE_TRUSTED_PROXIES` |

## V13 Konfiguraatio

| Vaatimus | Tila | Todiste |
|---|---|---|
| Turvalliset oletukset; palvelin kieltäytyy turvattomista tuotantoasetuksista | täyttyy | `test_settings`: https, tietokannan salasana ja salainen avain vaaditaan tuotannossa, localhost-uudelleenohjaukset hylätään |
| Riippuvuudet kiinnitetty, auditoitu ja päivitetty | täyttyy | `uv.lock`, pip-audit, Dependabot 7 päivän cooldownilla, actionit kiinnitetty SHA:lla ja zizmorin tarkistamia |
| Kovennettu kontti | täyttyy | Ei-root, vain luku -juuritiedostojärjestelmä, poistetut capabilities-oikeudet, `no-new-privileges`, Trivy-skannaus SBOM:n kanssa julkaisussa |
| Käytön tarkistukset | täyttyy | `opencde doctor` (tietokanta, skeema, kello, julkinen URL, otsakkeet, tallennustila) |
| Hallintakäyttöliittymä voidaan eristää | täyttyy | Erillinen kirjautuminen ja rooli; `OPENCDE_ADMIN_UI_ENABLED=false` poistaa sen julkisesta instanssista (hallinnoi sen sijaan CLI:llä), tai rajaa `/admin` sisäisiin osoitteisiin välityspalvelimella |
| Ei kolmannen osapuolen koodia tuotantosivuilla | täyttyy | Palvelimen sivut eivät lataa mitään muista origineista; interaktiivinen rajapintadokumentaatio (`/docs`, Swagger UI CDN:stä) tarjoillaan vain tuotannon ulkopuolella, ellei `OPENCDE_API_DOCS_ENABLED=true` |

## V14 Tietosuoja

| Vaatimus | Tila | Todiste |
|---|---|---|
| Ei arkaluonteista dataa lokeissa | täyttyy | Peittoprosessori eikä runkoja kirjata, `test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Arkaluonteisia vastauksia ei välimuistiteta | täyttyy | `Cache-Control: no-store` jokaisessa ei-staattisessa vastauksessa |
| Tunnistetiedot ja tokenit tiivistetty levossa | täyttyy | Argon2id ja SHA-256 |
| Tietojen minimointi | täyttyy | Tapahtuma-arvot leikataan; vastausmallit kantavat vain spesifikaation kentät |
| Varmuuskopiot suojattu | osittain | Sovellustason vienti (ADR 0006) ylläpitäjän varmuuskopiotaltioon; palvelin ei salaa sitä, joten taltio tai arkisto on ylläpitäjän salattava |
| Käyttäjät voidaan poistaa | täyttyy | Hallintakäyttöliittymä poistaa käyttäjät (uudelleentodennuksen jälkeen) ja peruu heidän tokeninsa |

## V15 Turvallinen koodaus ja arkkitehtuuri

| Vaatimus | Tila | Todiste |
|---|---|---|
| Dokumentoitu arkkitehtuuri ja uhkamalli | täyttyy | `docs/adr/`, [threat-model.md](threat-model.md), `docs/fi/graph-schema.md` |
| Staattinen analyysi ja riippuvuustarkistukset CI:ssä | täyttyy | ruff `S`-säännöt, Bandit, Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`), pip-audit |
| Ei vaarallisia funktioita tai epäluotettavan datan deserialisointia | täyttyy | Vain JSON; ei `pickle`-, `eval`- tai shell-interpolointia (Bandit) |
| Kilpailutilanteet kertakäyttöisissä salaisuuksissa | täyttyy | Koodin ja refresh-tokenin lunastus ovat yksittäisiä transaktioita uudelleenkäytön tunnistuksella |
| Selainkäyttöliittymän ja rajapinnan luottamusrajojen erottaminen | täyttyy | Evästeet vain sivuille, bearer-tokenit vain rajapinnalle; kumpikaan ei hyväksy toista |

## V16 Turvallisuuslokitus ja virheenkäsittely

| Vaatimus | Tila | Todiste |
|---|---|---|
| Rakenteiset lokit request-tunnisteella ja UTC-ajalla | täyttyy | structlog JSON, `RequestIDMiddleware` |
| Turvallisuustapahtumat kirjataan (kirjautuminen, tokenin myöntö, peruutus, hallintatoiminnot) | täyttyy | `AuditEvent`-solmut, näytetään `/admin/audit`-sivulla CSV-vientinä |
| Pyyntötason loki vianselvitykseen ilman arkaluonteista dataa | täyttyy | Valinnainen `RequestLog` (metodi, polku, operaatio, tila, kesto, request-id, tavut, kutsuja; ei kyselymerkkijonoja, otsakkeita tai runkoja), rajattu säilytys, vain järjestelmänvalvojat (`/admin/requests`, `/admin/api/requests` `admin`-scopella) |
| Virheet käsitellään ilman sisäisten tietojen vuotamista; odottamattomat virheet kirjataan | täyttyy | `errors.py`: spesifikaation runko, 5xx kirjataan request-id:n kanssa |
| Kellon oikeellisuus vanhenemistarkistuksiin | täyttyy | `opencde doctor` vertaa kelloa NTP-lähteeseen |
| Lokien suojaus, välitys ja hälytykset | ei täyty | Jätetty ylläpitäjälle (compose-lokiajuri, SIEM) |

## V17 WebRTC

ei sovellu.

## Tunnetut puutteet

| Puute | Suunnitelma |
|---|---|
| Ei monivaiheista todennusta kirjautumissivulla | TOTP (pyotp) myöhempänä vaiheena; yksi toteutus kattaa selainkäyttäjät ja OAuth2-asiakkaat |
| Istuntoeväste ilman `__Host-`-etuliitettä | Nimeä eväste uudelleen seuraavan evästemuutoksen yhteydessä (vaatii https:n kaikkialla, mikä tuotannossa on) |
| Ei live-tarkistusta vuotaneita salasanoja vasten | Valinnainen k-anonymiteettihaku vuoto-API:sta asetuksena |
| Ei käyttäjäkohtaista tallennuskiintiötä | Lisää `max_storage_bytes_per_user`, kun monen vuokralaisen käyttö alkaa |
| Ei lähettäjään sidottuja tokeneita | DPoP (RFC 9449) myöhempänä vaiheena |
| Ei virustarkistusta | Ylläpitäjän valinta tallennustaltiolla |
| Palvelin ei salaa varmuuskopioita | Salaa varmuuskopiotaltio tai kääri `opencde backup` `age`/`gpg`-työkaluun sivukontissa |
| OAuchia ja testssl.sh:ta ei ole vielä ajettu asennusta vasten | Aja ennen ensimmäistä tuotantoasennusta; tallenna raportit |
| Ei ulkoista tunkeutumistestausta | Valinnainen, omistajan harkinnan mukaan, edellisten jälkeen |
