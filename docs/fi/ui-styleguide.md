# Käyttöliittymän tyyliopas

Jokainen palvelimen renderöimä sivu (kirjautuminen ja suostumus, Documents
API -sivut, tili, hallinta) jakaa yhden ulkoasun ja yhden sääntöjoukon. Tämä
opas on normatiivinen uusille sivuille (ADR 0004).

## Periaatteet

1. **Palvelimella renderöity, toimii ilman JavaScriptiä.** Jokainen toiminto
   on lomakkeen POST; JavaScript vain sujuvoittaa (suodatus, lajittelu,
   vahvistusdialogit, kopiointipainikkeet).
2. **Yksi designin lähde, ja se on Dataspatiumin.** Omistaja päätti, että
   palvelimen sivut ja Dataspatium-sovellus jakavat yhden, Dataspatiumiin
   perustuvan ulkoasun, ja Dataspatiumin tekijänoikeuden haltijana salli
   Dataregiumin käyttää tuota designia lisenssien eroista huolimatta
   (2026-11-05). Värit, typografia, välit ja pyöristykset tulevat tiedostosta
   `opencde/ui/static/css/tokens.css`, joka sisältää Dataspatiumin tokenit
   `--dm-*`-nimillään; komponentit tiedostosta `components.css`, joka ilmaisee
   Dataspatiumin komponentit palvelimen pelkällä HTML:llä. Älä koskaan
   kovakoodaa väriä tai pikseliarvoa malliin, ja kun Dataspatiumin tokenit
   muuttuvat, muuta omamme samalla tavalla.
3. **Tiukka CSP.** Ei inline-`<script>`-elementtejä eikä `style=`-määreitä, ei
   `on*`-attribuutteja, ei `innerHTML`-käyttöä palvelindatan kanssa, ei
   CDN:ää. Skriptit ovat ES-moduuleja polun `/static/js/` alla, ladattuina
   `<script type="module">`-elementillä.
4. **Turvallinen oletuksena.** Jokainen lomake kantaa allekirjoitettua
   `form_token`-arvoa; dataa muuttavat sivut tarkistavat sen, selaimen
   `Sec-Fetch-Site`/`Origin`-otsakkeet ja vaarallisissa toiminnoissa käyttäjän
   oman salasanan. Salaisuudet näytetään kerran.
5. **Saavutettava.** Semanttinen HTML, oikeat `<label>`-elementit, näkyvä
   kohdistus, WCAG 2.2 AA -kontrasti, `aria-current`, `role="status"`
   ilmoituksille. Playwright ja axe-core tarkistavat jokaisen hallintasivun
   (`uv run pytest -m ui`).

## Asettelu

- `base.html`: ylätunniste (tunnus + `{% block nav %}`), `<main id="main">`,
  alatunniste. Käytä `page--narrow`-body-luokkaa yksisarakkeisille
  lomakkeille.
- Hallintasivut laajentavat `admin/_page.html`-mallia: sivunavigaatio
  (`admin_nav`), ilmoitusalue, sitten sivu lohkossa `{% block admin %}`.
  Sisältö on sarake `.card`-elementtejä, kullakin yksi `<h2>`.
- Taulukot ovat rakenteessa `.table-wrap > table.table`. Lisää
  `data-filterable` suodatuskenttää varten (näkyy, kun rivejä on yli viisi)
  ja `data-sortable` napsautuksella lajiteltaville otsikoille.

## Komponentit (makrot, käytettävissä jokaisessa mallissa)

| Makro | Käyttö |
|---|---|
| `field(name, label, type, value, …)` | Teksti-, salasana-, sähköposti- ja URL-kentät nimiöllä ja valinnaisella ohjeella |
| `select_field(name, label, options, selected)` | `<select>`; `options` on lista `(value, text)`-pareja |
| `textarea_field(name, label, value, rows)` | Monirivinen kenttä, listoissa yksi arvo riviä kohti |
| `checkbox(name, label, checked)` | Totuusarvo nimiöineen |
| `confirm_password(form_id)` | Vaarallisten lomakkeiden tarvitsema "salasanasi"-kenttä |
| `button(text, kind, name, value)` | `primary`, `secondary`, `danger`; `formnovalidate` Peruuta-painikkeelle |
| `alert(kind, text, title)` | Laatikot tyypeillä `error`, `success`, `warning`, `info` |
| `notice_box(notice, kind)` | Edellisen toiminnon tulos (parametrista `?notice=`) |
| `user_nav(web_user, signout_token)` | Kirjautunut käyttäjä ja uloskirjautumislomake ylätunnisteessa |
| `when(iso)` | `<time>`-elementti ISO-aikaleimalle |

Merkit: `.badge` (korostus), `.badge--neutral`, `.badge--success`,
`.badge--warning`, `.badge--danger`. Vaaravyöhykkeet: `.card.card--danger`,
yksi lomake tuhoavaa toimintoa kohti ja `data-confirm="kysymys"` lomakkeessa.

## Tokenit ja yhteinen ulkoasu

`tokens.css` on Dataspatiumin token-tiedosto (siellä
`src/ui/design/tokens.css`) ilman datapalettia ja paneeliasettelua, joita
vain sovellus tarvitsee. Nimet ovat samat, `--dm-*`, jotta arvoa voi verrata
rivi riviltä:

- Typografia: Inter (itse isännöity polussa `/static/fonts/`, SIL Open Font
  License, leikkaukset 400, 500 ja 600), asteikko `--dm-text-xs` 12 px …
  `--dm-text-2xl` 24 px, leipäteksti 15 px, riviväli 1,45.
- Välit: 4 px:n asteikko `--dm-s-1` … `--dm-s-12`.
- Muoto: `--dm-radius-sm` 6 px säätimille, `--dm-radius-md` 10 px korteille
  ja dialogeille; varjot vain dialogeissa.
- Väri: neutraali asteikko, semanttiset pinnat ja teksti, korostusväri
  (`#2b6cb0`, tunnuksen sininen), tilavärit `ok`/`warn`/`error`, kullakin
  `-soft`-tausta, sekä tumma teema valitsimilla `:root[data-theme="dark"]` ja
  `prefers-color-scheme: dark`.
- Asettelu: yläpalkki on `--dm-topbar-h` 48 px, alatunniste
  `--dm-statusbar-h` 28 px, hallinnan sivunavigaatio `--dm-panel-min-w`
  200 px; alle 760 px asettelu pinoutuu ja säätimet kasvavat 44 px:n
  kosketusalueiksi.

Komponentit vastaavat Dataspatiumin komponentteja näin:

| Dataregium-luokka | Dataspatium-komponentti | Ulkoasu |
|---|---|---|
| `.btn`, `--primary`, `--secondary`, `--ghost`, `--danger`, `--small` | `dm-button` ja `variant` sekä `size` | 32 px (26 px pieni), pyöristys 6 px, 13 px medium-teksti; primary täytetty korostusvärillä; danger punainen teksti, punainen osoitettaessa |
| `.input`, `.select`, `.textarea`, `.field__label`, `.field__hint` | `.dm-field`, `.dm-label`, `.dm-help` | 32 px, kentän reunus, kohdistusrengas sisäpuolella; tekstialueet tasalevyisellä kirjasimella |
| `.badge` | `dm-badge` | pilleri, 12 px medium |
| `.card` | `dm-panel[card]`, `.dm-card` | pinta, reunus, pyöristys 10 px, ei varjoa |
| `.table` rakenteessa `.table-wrap` | `dm-table` | 13 px, otsikko surface-2-pinnalla 34 px, 30 px rivit, lajiteltu otsikko korostusvärillä |
| `.nav a`, `.sidenav__list a` | `.dm-list-item` | 13 px, pyöristys 6 px, osoitettaessa pinta, nykyinen accent-soft |
| `.alert` | `.dm-toast` | pinta ja 3 px:n värillinen vasen reuna |
| `dialog` | `dialog.dm-dialog` | 560 px, pyöristys 10 px, suuri varjo, taustahuntu |
| `.consent` | `.dm-course-task` | surface-2 ja korostusvärinen vasen reuna |
| `.stat` | kortti, jossa `--dm-text-2xl` | taulukkonumerot |

Dataspatiumin säännöt pätevät myös palvelimen sivuilla: enintään yksi
primary-painike näkymää kohti; tuhoavat toiminnot käyttävät danger-varianttia
ja vahvistusdialogia; numerot tasataan oikealle taulukkonumeroin;
päivämäärät `YYYY-MM-DD`, ajat `HH:MM`; kaikki saavutettavissa näppäimistöllä
näkyvällä kohdistusrenkaalla; ei animaatiota lyhyitä siirtymiä lukuun
ottamatta, eikä lainkaan `prefers-reduced-motion`-asetuksella.

## Tunnus

Palvelimen tunnus on Dataspatiumin tunnuksen sisarus: missä Dataspatium
näyttää kolme päällekkäistä arkkia, Dataregium näyttää kolme yhdistettyä solmua
(graafin): onttoja renkaita säteellä 2,6, yksi keskellä vasemmalla
yhdistettynä kahdella viivalla kahteen oikealla olevaan, valkoisina samalla
sinisellä laatalla `#2b6cb0`, jonka kulmapyöristys on 7, 32 yksikön
neliössä, kaikki samalla viivanpaksuudella 2,2. Valkoinen muste säilyttää
Dataspatiumin marginaalit täsmälleen (x 7,4–24,6, y 5,08–26,92 laatikosta).
Lähde on `opencde/ui/static/icon.svg`; `icon-32.png`, `icon-180.png`,
`icon-192.png`, `icon-512.png` ja `favicon.ico` renderöidään siitä (PNG:t
Edge headlessilla läpinäkyvälle taustalle, ICO käärii 16, 32 ja 48 px:n
PNG:t). Käytä SVG:tä, missä sivu voi, säilytä laatta äläkä väritä tunnusta
uudelleen.

## Kirjoittaminen

- Lyhyet otsikot, jotka nimeävät kohteen: "Käyttäjät", "Uusi projekti",
  "Vaaravyöhyke".
- Painikkeet kertovat, mitä tapahtuu: "Luo käyttäjä", "Vaihda salaisuus",
  ei "OK".
- Ohjeet selittävät seuraukset yhdellä lauseella kentän vierellä.
- Virhe- ja ilmoitustekstit eivät koskaan toista käyttäjän syötettä eivätkä
  paljasta, onko tili olemassa ("Käyttäjätunnus tai salasana ei ole oikein.").
- Jokainen teksti tulee kielikatalogeista `t("key")`-kutsulla (katso
  "Kielikerros" alla); englanti on lähde, ja muut kuusi kieltä noudattavat
  Dataspatiumin sanastoa. Termit noudattavat spesifikaatioita (topic,
  viewpoint, client, redirect URI, scope, role), ja API-termit pysyvät
  ennallaan jokaisella kielellä.

## Kielikerros

Sivut ovat README:n seitsemällä kielellä. Mekaniikka on Dataspatiumin: yksi
litteä katalogi kieltä kohti tiedostossa `opencde/ui/i18n/<lang>.json`
pisteavaimin ja `{name}`-parametrein, samat avainnimet, missä tuotteet
jakavat käsitteen (`opencde.signin`, `opencde.signout`, `opencde.project`,
`opencde.kind.topics`, `common.cancel`, `common.save` …), ja omat alueet
muulle (`nav.*`, `account.*`, `docs.*`, `admin.*`, `notice.*`, `js.*`).

- Mallit ja makrot kutsuvat `t("key")` tai `t("key", name=value)`; pyynnön
  kieli on kontekstimuuttujassa, jonka `render()` asettaa, joten myös tuodut
  makrot kääntyvät. Python-koodi, joka rakentaa sivutekstin ennen
  renderöintiä, käyttää `tr(request, "key")`.
- Kieli valitaan pyyntöä kohti: `?lang=xx` (muistetaan `opencde_lang`-evästeessä
  vuoden), eväste, selaimen `Accept-Language` (pelkkä `no` tarkoittaa
  bokmålia), englanti. Jokaisen sivun alatunniste sisältää vaihtimen.
- Skriptit eivät koskaan sisällä tekstejä: `base.html` sijoittaa skriptien
  tarvitsemat harvat merkkijonot `<html>`-elementin `data-t-*`-attribuutteihin
  (suodatuskenttä, rivimäärät, vahvistusdialogi, kopiointipalaute).
- Toiselta kieleltä puuttuva avain palaa englantiin; kaikkialta puuttuva avain
  renderöidään avaimena itsenään. Yksikkötesti
  `test_every_language_has_every_key_of_the_english_source` pitää seitsemän
  katalogin avainjoukot ja parametrit identtisinä, joten lisää jokainen uusi
  avain kaikkiin samassa commitissa.
- Viestit, jotka tili-, projekti- ja asiakaskoodi nostaa virheellisestä
  syötteestä (`UserFacingError` avaimella ja parametreilla, jaettu CLI:n
  kanssa), käännetään sivun rajalla `tr_error(request, exc)`-kutsulla; CLI ja
  rajapinta säilyttävät englanninkielisen tekstin.

## JavaScript-säännöt

- Yksi sisääntulomoduuli sivutyyppiä kohti (`admin.js`), joka tuo pieniä
  moduuleja (`table.js`, `confirm.js`, `copy.js`). Rakenna DOM
  `createElement`- ja `textContent`-kutsuilla.
- Paranna vain sitä, mikä on olemassa: lue `data-*`-attribuutteja, älä
  koskaan asetuksia inline-skripteistä.
- Lomakkeella, joka pysyy sivullaan, voi olla `data-inline` (`inline.js`): se tallentaa `fetch`-kutsulla, ja palvelimen vastaussivun `main`-elementti korvaa vanhan. Sivu jäsennetään kokonaisena `DOMParser`illa, joten palvelimen escaping pätee, ja lomake lähetetään tavalliseen tapaan, jos jokin menee vikaan.
- Pidä käytös palautuvana: sivun on toimittava oikein, jos moduuli ei
  lataudu.
