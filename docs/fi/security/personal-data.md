# Henkilötiedot ja säilytysajat

Mitä Kontroll-palvelin tallentaa ihmisistä, kuinka kauan ja kuka sen näkee.
Tämä on palvelimen puolikas sivusta, joka jaetaan Dataspatiumin kanssa;
sovelluksen puolikas (mitä se säilyttää selaimessa ja mitä se lähettää) on
Dataspatiumin dokumentaatiossa. Se, joka ylläpitää Kontrollia muille, on
näiden tietojen rekisterinpitäjä; tämä sivu antaa faktat omiin selosteisiin.

## Mitä tallennetaan

| Tieto | Missä | Sisältö | Säilytetään |
|---|---|---|---|
| Käyttäjätilit | `User`-solmut | käyttäjätunnus, koko nimi, sähköposti (valinnainen), salasanan Argon2id-tiiviste, järjestelmänvalvojan merkintä, luontiaika, viimeisin kirjautuminen | Kunnes järjestelmänvalvoja poistaa tilin |
| Projektijäsenyydet | `MEMBER_OF`-suhteet | käyttäjä, projekti, rooli | Kunnes poistetaan |
| OAuth2-tokenit | solmut `AuthorizationCode`, `AccessToken`, `RefreshToken` | SHA-256-tiivisteet (ei koskaan itse tokeneita), käyttäjä, asiakas, scope, ajat | Koodit 60 s, access-tokenit 1 h, refresh-tokenit 30 päivää (`OPENCDE_*_TTL_SECONDS`); siivous poistaa vanhentuneet tai perutut |
| Selainistunnot | `WebSession`-solmut | käyttäjä, luonti- ja viimeisimmän toiminnan aika, asiakkaan osoite kirjautuessa | 8 tuntia tai 30 minuuttia ilman toimintaa; poistetaan uloskirjautuessa |
| Epäonnistuneet kirjautumiset | `SignInThrottle`-solmut | käyttäjätunnuksen tiiviste, epäonnistumisten määrä, milloin seuraava yritys on sallittu | vuorokausi viimeisestä epäonnistumisesta; onnistunut kirjautuminen poistaa sen |
| OAuth2-asiakkaat | `Client`-solmut | nimi, kuvaus, osoite, redirect-URIt, tiivistetty salaisuus, `software_id`/`software_version`, luoja | Kunnes poistetaan; itse rekisteröityneet asiakkaat, joita ei ole käytetty 30 päivään, poistetaan tokeneineen |
| BCF-tiedot | solmut `Topic`, `Comment`, `Viewpoint`, `Event` ja niihin liittyvät | käyttäjien kirjoittamat otsikot, kuvaukset ja kommentit, käyttäjätunnukset tekijöinä ja vastuuhenkilöinä, ajat, tilannekuvat, komponenttiviittaukset | Kunnes asia, kommentti tai projekti poistetaan |
| Asiakirjat | solmut `Document` ja `DocumentVersion`, tiedostot hakemistossa `OPENCDE_DATA_DIR` | otsikko, tiedostonimi, koko, SHA-256, lähettäjä, aika; itse tiedosto (joka voi sisältää henkilötietoja, esimerkiksi nimiä IFC-mallin omistajahistoriassa) | Kunnes versio tai projekti poistetaan; varmuuskopiot säilyttävät kopioita niin kauan kuin ylläpitäjä säilyttää varmuuskopiot |
| IFC-graafi | `IfcModel`-solmut ja jokaisen tuodun mallin entiteetit | IFC-tiedoston sisältö graafidatana, mukaan lukien projektin `IfcOwnerHistory` | Korvatut tai epäonnistuneet mallit poistetaan komennolla `opencde ifc-lpg prune`; muuten asiakirjaversion mukana |
| Tapahtumaloki | `AuditEvent`-solmut | mitä tapahtui (kirjautuminen, myönnetty token, rekisteröity asiakas, muutettu rooli …), kuka teki, asiakkaan osoite, aika, request-id | Ei vanhene itsestään; järjestelmänvalvojat voivat viedä sen CSV:nä, ja ylläpitäjä poistaa oman käytäntönsä mukaan |
| Pyyntöloki (valinnainen) | `RequestLog`-solmut | metodi, polku ilman kyselymerkkijonoa, operaatio, tila, kesto, tavumäärät, request-id, käyttäjä- tai asiakastunnus; ei koskaan otsakkeita, runkoja tai tokeneita | `OPENCDE_REQUEST_LOG_RETENTION_HOURS` (oletus 72); pois päältä, ellei `OPENCDE_REQUEST_LOG_ENABLED=true` |
| Lähetys- ja valintaistunnot | solmut `UploadSession`, `UploadPart`, `SelectionSession` ja tilapäiset osatiedostot | kuka aloitti kulun, mitkä tiedostot, callback-osoite, ajat | 24 tuntia lähetyksille, 10 minuuttia sivulinkeille; palvelin siivoaa |
| Palvelinlokit | kontin vakiotuloste (JSON-rivejä) | request-id, polku, tila, kesto, käyttäjä- tai asiakastunnus, asiakkaan osoite luotetulta välityspalvelimelta; ei koskaan runkoja, tokeneita, koodeja tai salasanoja | Niin kauan kuin ylläpitäjä säilyttää konttilokit |

Varmuuskopiot, jotka on tehty komennolla `opencde backup` tai `backup`-palvelulla,
sisältävät kaiken yllä olevan palvelinlokeja lukuun ottamatta, salattuina
tai ei ylläpitäjän valinnan mukaan ([deploy/backup.md](../deploy/backup.md)).

## Kuka näkee mitä

- Projektin jäsenet näkevät sen asiat, kommentit, viewpointit ja asiakirjat
  rajapintojen kautta; rooli ratkaisee, mitä he saavat muuttaa. Projektin
  ulkopuoliset käyttäjät eivät näe, että se on olemassa (404).
- Järjestelmänvalvojat näkevät kaikki käyttäjät, projektit, asiakkaat,
  istunnot, tapahtumalokin ja, kun se on päällä, pyyntölokin `/admin`-sivuilla
  ja `admin`-scopen sisältävällä bearer-tokenilla osoitteessa `/admin/api`.
- Jokainen käyttäjä näkee oman tilinsä, sovelluksensa ja istuntonsa
  osoitteessa `/account` ja voi perua ne.
- Kukaan ei näe salasanoja, salaisuuksia tai tokeneita: palvelin tallentaa
  vain tiivisteet ja näyttää uuden salaisuuden kerran, luotaessa.
- Kuka tahansa voi lukea osoitteet `/.well-known/kontroll`,
  `/foundation/versions`, `/foundation/1.0/auth` ja `/healthz`; ne sisältävät
  asetuksia, eivät koskaan ihmisiä.

## Oikeudet ja toimenpiteet

- **Henkilön poistaminen**: poista tili kohdassa `/admin/users` (tai
  komennolla `opencde user delete`); istunnot ja tokenit poistuvat mukana.
  Nimi jää henkilön kirjoittamiin asioihin ja kommentteihin projektin
  BCF-datana; poista tai muokkaa niitä rajapinnan kautta tai poista projekti.
- **Vienti**: tapahtumaloki viedään CSV:nä; BCF- ja asiakirjatiedot viedään
  rajapintojen kautta (Dataspatiumin kaltainen asiakas voi tallentaa projektin
  BCFzip-tiedostona); `opencde backup` kirjoittaa koko tietokannan.
- **Tietoturvapoikkeama**: `opencde revoke --all` päättää kaikki istunnot ja
  tokenit; kierrätä tietokannan salasana ja salainen avain sen jälkeen
  ([controls.md](controls.md)).
- **Minimointi**: pidä pyyntöloki pois päältä, ellet selvitä asiakkaan
  vikaa, pidä `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` pois päältä, ellet
  tarvitse sitä, äläkä julkaise tietokantaporttia
  ([deploy/bolt.md](../deploy/bolt.md)).

## Dataspatiumissa

Sovellus säilyttää selaimessa palvelimen osoitteen, rekisteröimänsä
asiakastunnuksen, käyttäjän istunnon tokenit ja lokin kutsuistaan
(request-id:ineen); salasanaa se ei koskaan tallenna. Mikä näistä lähtee
selaimesta ja miten ne tyhjennetään, kerrotaan [Dataspatiumin omalla henkilötietosivulla](https://github.com/marwiss/Dataspatium/blob/main/docs/fi/sakerhet.md).
