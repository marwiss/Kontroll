# UI-stilguide

Kvar side serveren teiknar (innlogging og samtykke, Documents API-sider,
konto, administrasjon) deler eitt utsjånad og eitt sett reglar. Denne guiden
er normativ for nye sider (ADR 0004).

## Prinsipp

1. **Servergjeven, verkar utan JavaScript.** Kvar handling er ein
   skjema-POST; JavaScript gjer berre ting glattare (filtrering, sortering,
   stadfestingsdialogar, kopieringsknappar).
2. **Éi kjelde til designet, og det er Dataspatium si.** Eigaren avgjorde at
   sidene til serveren og Dataspatium-appen deler eitt utsjånad, basert på
   Dataspatium sitt, og som rettshavar til Dataspatium lét Kontroll bruke det
   designet trass i dei ulike lisensane (2026-11-05). Fargar, typografi,
   avstandar og radiar kjem frå `opencde/ui/static/css/tokens.css`, som ber
   Dataspatium sine tokens med `--dm-*`-namna deira; komponentar frå
   `components.css`, som uttrykkjer Dataspatium sine komponentar på den reine
   HTML-en til serveren. Hardkod aldri ein farge eller ein pikselverdi i ein
   mal, og når Dataspatium sine tokens blir endra, endre våre på same måte.
3. **Streng CSP.** Ingen inline-`<script>` eller `style=`, ingen
   `on*`-attributt, ingen `innerHTML` med serverdata, ingen CDN. Skript er
   ES-modular under `/static/js/`, lasta med `<script type="module">`.
4. **Trygg som standard.** Kvart skjema ber ein signert `form_token`; sider
   som endrar data, sjekkar han, nettlesaren sin `Sec-Fetch-Site`/`Origin`
   og, for farlege handlingar, brukaren sitt eige passord. Løyndomar blir
   viste éin gong.
5. **Tilgjengeleg.** Semantisk HTML, ekte `<label>`-ar, synleg fokus, WCAG
   2.2 AA-kontrast, `aria-current`, `role="status"` for meldingar. Playwright
   med axe-core sjekkar kvar adminside (`uv run pytest -m ui`).

## Layout

- `base.html`: topptekst (merke + `{% block nav %}`), `<main id="main">`,
  botntekst. Bruk `page--narrow` som body-klasse for skjema i éi kolonne.
- Adminsider utvidar `admin/_page.html`: sidenavigasjon (`admin_nav`), eit
  meldingsområde, deretter sida i `{% block admin %}`. Innhaldet er ei
  kolonne av `.card`-ar, kvar med éin `<h2>`.
- Tabellar ligg i `.table-wrap > table.table`. Legg til `data-filterable` for
  ein filterboks (blir vist når det er meir enn fem rader) og `data-sortable`
  for klikksorterbare overskrifter.

## Komponentar (makroar, tilgjengelege i kvar mal)

| Makro | Bruk |
|---|---|
| `field(name, label, type, value, …)` | Tekst-, passord-, e-post- og URL-felt med etikett og valfri hjelpetekst |
| `select_field(name, label, options, selected)` | `<select>`; `options` er ei liste av `(value, text)` |
| `textarea_field(name, label, value, rows)` | Fleirlinjefelt, éin verdi per linje for lister |
| `checkbox(name, label, checked)` | Ein boolsk verdi med etiketten sin |
| `confirm_password(form_id)` | Feltet "passordet ditt" som farlege skjema treng |
| `button(text, kind, name, value)` | `primary`, `secondary`, `danger`; `formnovalidate` for Avbryt |
| `alert(kind, text, title)` | Boksar av typen `error`, `success`, `warning`, `info` |
| `notice_box(notice, kind)` | Resultatet av førre handling (frå `?notice=`) |
| `user_nav(web_user, signout_token)` | Innlogga brukar og utloggingsskjema i toppteksten |
| `when(iso)` | Eit `<time>`-element for eit ISO-tidsstempel |

Merke: `.badge` (aksent), `.badge--neutral`, `.badge--success`,
`.badge--warning`, `.badge--danger`. Faresoner: `.card.card--danger` med eitt
skjema per destruktiv handling og `data-confirm="spørsmål"` på skjemaet.

## Tokens og det felles utsjånaden

`tokens.css` er token-fila til Dataspatium (`src/ui/design/tokens.css` der)
minus datapaletten og panellayouten som berre appen treng. Namna er dei same,
`--dm-*`, så ein verdi kan samanliknast linje for linje:

- Typografi: Inter (sjølvhosta under `/static/fonts/`, SIL Open Font License,
  vektene 400, 500 og 600), skalaen `--dm-text-xs` 12 px … `--dm-text-2xl`
  24 px, brødtekst 15 px, linjehøgd 1,45.
- Avstand: 4 px-skalaen `--dm-s-1` … `--dm-s-12`.
- Form: `--dm-radius-sm` 6 px for kontrollar, `--dm-radius-md` 10 px for kort
  og dialogar; skuggar berre på dialogar.
- Farge: den nøytrale skalaen, dei semantiske flatene og teksten, aksenten
  (`#2b6cb0`, det blå i merket), statusfargane `ok`/`warn`/`error`, kvar med
  ein `-soft`-bakgrunn, og det mørke temaet under `:root[data-theme="dark"]`
  og `prefers-color-scheme: dark`.
- Layout: topplinja er `--dm-topbar-h` 48 px, botnteksten `--dm-statusbar-h`
  28 px, sidenavigasjonen i administrasjonen `--dm-panel-min-w` 200 px; under
  760 px blir layouten stabla og kontrollane veks til 44 px trykkflater.

Komponentane blir avbilda på Dataspatium sine slik:

| Kontroll-klasse | Dataspatium-komponent | Utsjånad |
|---|---|---|
| `.btn`, `--primary`, `--secondary`, `--ghost`, `--danger`, `--small` | `dm-button` med `variant` og `size` | 32 px (26 px liten), radius 6 px, 13 px medium tekst; primær fylt aksent; danger raud tekst, raud ved hover |
| `.input`, `.select`, `.textarea`, `.field__label`, `.field__hint` | `.dm-field`, `.dm-label`, `.dm-help` | 32 px, feltkant, fokusring innanfor; tekstområde i monospace |
| `.badge` | `dm-badge` | pille, 12 px medium |
| `.card` | `dm-panel[card]`, `.dm-card` | flate, kant, radius 10 px, ingen skugge |
| `.table` i `.table-wrap` | `dm-table` | 13 px, overskrift på surface-2 ved 34 px, 30 px rader, sortert overskrift i aksent |
| `.nav a`, `.sidenav__list a` | `.dm-list-item` | 13 px, radius 6 px, hover-flate, gjeldande i accent-soft |
| `.alert` | `.dm-toast` | flate med ein 3 px farga venstrekant |
| `dialog` | `dialog.dm-dialog` | 560 px, radius 10 px, stor skugge, bakgrunn |
| `.consent` | `.dm-course-task` | surface-2 med ein aksentkant til venstre |
| `.stat` | eit kort med `--dm-text-2xl` | tabelltal |

Reglane til Dataspatium gjeld òg på sidene til serveren: høgst éin
primærknapp per visning; destruktive handlingar brukar danger-varianten og
ein stadfestingsdialog; tal høgrestilte med tabelltal; datoar `YYYY-MM-DD`,
tider `HH:MM`; alt nåeleg med tastatur med ein synleg fokusring; ingen
animasjon utover korte overgangar, ingen i det heile under
`prefers-reduced-motion`.

## Merket

Merket til serveren er sysken til Dataspatium sitt: der Dataspatium viser tre
stabla ark, viser Kontroll tre samanbundne nodar (ein graf): hole ringar med
radius 2,6, éin i midten til venstre bunden med to linjer til dei to til
høgre, kvite på den same blå plata `#2b6cb0` med hjørneradius 7 i eit kvadrat
på 32 einingar, alt med same strekbreidd 2,2. Den kvite fargen held på
margane til Dataspatium nøyaktig (x 7,4–24,6, y 5,08–26,92 av boksen). Kjelda
er `opencde/ui/static/icon.svg`; `icon-32.png`, `icon-180.png`,
`icon-192.png`, `icon-512.png` og `favicon.ico` blir teikna frå han
(PNG-filene med Edge headless på gjennomsiktig bakgrunn, ICO-fila omsluttar
PNG-filene på 16, 32 og 48 px). Bruk SVG-en der sida kan, hald på plata, og
fargelegg ikkje merket på nytt.

## Skriving

- Korte overskrifter som namngjev objektet: "Brukarar", "Nytt prosjekt",
  "Faresone".
- Knappar seier kva som skjer: "Opprett brukar", "Roter løyndom", ikkje "OK".
- Hjelpetekstar forklarar konsekvensar i éi setning ved sida av feltet.
- Feil- og meldingstekstar gjentek aldri brukarinndata og avslører aldri om
  ein konto finst ("Brukarnamnet eller passordet er ikkje rett.").
- Kvar tekst kjem frå språkkatalogane gjennom `t("key")` (sjå "Språklaget"
  nedanfor); engelsk er kjelda, og dei andre seks språka følgjer ordlista til
  Dataspatium. Termar følgjer spesifikasjonane (topic, viewpoint, client,
  redirect URI, scope, role), og API-termar held fram som dei er på alle
  språk.

## Språklaget

Sidene finst på dei sju språka i README-en. Mekanikken er Dataspatium sin:
éin flat katalog per språk i `opencde/ui/i18n/<lang>.json` med punkterte
nøklar og `{name}`-parametrar, dei same nøkkelnamna der dei to produkta deler
eit omgrep (`opencde.signin`, `opencde.signout`, `opencde.project`,
`opencde.kind.topics`, `common.cancel`, `common.save` …), og eigne område for
resten (`nav.*`, `account.*`, `docs.*`, `admin.*`, `notice.*`, `js.*`).

- Malar og makroar kallar `t("key")` eller `t("key", name=value)`; språket
  til førespurnaden ligg i ein kontekstvariabel som `render()` set, så
  importerte makroar blir òg omsette. Python-kode som byggjer ein sidetekst
  før teikning, brukar `tr(request, "key")`.
- Språket blir valt per førespurnad: `?lang=xx` (hugsa i cookien
  `opencde_lang` i eit år), cookien, nettlesaren sin `Accept-Language` (rein
  `no` tyder bokmål), engelsk. Botnteksten på kvar side ber veljaren.
- Skript held aldri tekstar: `base.html` legg dei få strengane skripta treng,
  i `data-t-*`-attributt på `<html>` (filterboks, radtal, stadfestingsdialogen,
  kopieringstilbakemelding).
- Ein nøkkel som manglar på eit anna språk, fell tilbake til engelsk; ein
  nøkkel som manglar overalt, blir teikna som nøkkelen sjølv. Einingstesten
  `test_every_language_has_every_key_of_the_english_source` held dei sju
  katalogane identiske i nøkkelsett og parametrar, så legg kvar ny nøkkel til
  i alle i same commit.
- Meldingane konto-, prosjekt- og klientkoden reiser ved ugyldig inndata
  (`UserFacingError` med nøkkel og parametrar, delt med CLI-et), blir omsette
  ved sidegrensa med `tr_error(request, exc)`; CLI-et og API-et held på den
  engelske teksten.

## JavaScript-reglar

- Éin inngangsmodul per sidetype (`admin.js`), som importerer små modular
  (`table.js`, `confirm.js`, `copy.js`). Bygg DOM med `createElement` og
  `textContent`.
- Forbetre berre det som finst: les `data-*`-attributt, aldri konfigurasjon
  frå inline-skript.
- Eit skjema som blir på sida si, kan ha `data-inline` (`inline.js`): det lagrar med `fetch`, og `main`-elementet på sida serveren svarar med, erstattar det gamle. Sida blir tolka heil med `DOMParser`, så escapinga til serveren gjeld, og skjemaet blir sendt på vanleg måte om noko går gale.
- Hald åtferda reversibel: ei side må gjere det rette om modulen ikkje kan
  lastast.
