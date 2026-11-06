# UI-stilguide

Hver side serveren rendrer (innlogging og samtykke, Documents API-sider,
konto, administrasjon) deler ett utseende og ett sett regler. Denne guiden er
normativ for nye sider (ADR 0004).

## Prinsipper

1. **Servergjengitt, virker uten JavaScript.** Hver handling er en
   skjema-POST; JavaScript gjør bare ting glattere (filtrering, sortering,
   bekreftelsesdialoger, kopieringsknapper).
2. **Én kilde til designet, og det er Dataspatiums.** Eieren besluttet at
   serverens sider og Dataspatium-appen deler ett utseende, basert på
   Dataspatiums, og som Dataspatiums rettighetshaver tillot Kontroll å bruke
   det designet til tross for de ulike lisensene (2026-11-05). Farger,
   typografi, avstander og radier kommer fra `opencde/ui/static/css/tokens.css`,
   som bærer Dataspatiums tokens med `--dm-*`-navnene deres; komponenter fra
   `components.css`, som uttrykker Dataspatiums komponenter på serverens rene
   HTML. Hardkod aldri en farge eller en pikselverdi i en mal, og når
   Dataspatiums tokens endres, endre våre på samme måte.
3. **Streng CSP.** Ingen inline-`<script>` eller `style=`, ingen
   `on*`-attributter, ingen `innerHTML` med serverdata, ingen CDN. Skript er
   ES-moduler under `/static/js/`, lastet med `<script type="module">`.
4. **Sikker som standard.** Hvert skjema bærer en signert `form_token`; sider
   som endrer data, sjekker den, nettleserens `Sec-Fetch-Site`/`Origin` og,
   for farlige handlinger, brukerens eget passord. Hemmeligheter vises én
   gang.
5. **Tilgjengelig.** Semantisk HTML, ekte `<label>`-er, synlig fokus, WCAG
   2.2 AA-kontrast, `aria-current`, `role="status"` for meldinger. Playwright
   med axe-core sjekker hver adminside (`uv run pytest -m ui`).

## Layout

- `base.html`: topptekst (merke + `{% block nav %}`), `<main id="main">`,
  bunntekst. Bruk `page--narrow` som body-klasse for skjemaer i én kolonne.
- Adminsider utvider `admin/_page.html`: sidenavigasjon (`admin_nav`), et
  meldingsområde, deretter siden i `{% block admin %}`. Innholdet er en
  kolonne av `.card`-er, hver med én `<h2>`.
- Tabeller ligger i `.table-wrap > table.table`. Legg til `data-filterable`
  for en filterboks (vises når det er mer enn fem rader) og `data-sortable`
  for klikksorterbare overskrifter.

## Komponenter (makroer, tilgjengelige i hver mal)

| Makro | Bruk |
|---|---|
| `field(name, label, type, value, …)` | Tekst-, passord-, e-post- og URL-felt med etikett og valgfri hjelpetekst |
| `select_field(name, label, options, selected)` | `<select>`; `options` er en liste av `(value, text)` |
| `textarea_field(name, label, value, rows)` | Flerlinjefelt, én verdi per linje for lister |
| `checkbox(name, label, checked)` | En boolsk verdi med etiketten sin |
| `confirm_password(form_id)` | Feltet "ditt passord" som farlige skjemaer trenger |
| `button(text, kind, name, value)` | `primary`, `secondary`, `danger`; `formnovalidate` for Avbryt |
| `alert(kind, text, title)` | Bokser av typen `error`, `success`, `warning`, `info` |
| `notice_box(notice, kind)` | Resultatet av forrige handling (fra `?notice=`) |
| `user_nav(web_user, signout_token)` | Innlogget bruker og utloggingsskjema i toppteksten |
| `when(iso)` | Et `<time>`-element for et ISO-tidsstempel |

Merker: `.badge` (aksent), `.badge--neutral`, `.badge--success`,
`.badge--warning`, `.badge--danger`. Faresoner: `.card.card--danger` med ett
skjema per destruktiv handling og `data-confirm="spørsmål"` på skjemaet.

## Tokens og det felles utseendet

`tokens.css` er Dataspatiums token-fil (`src/ui/design/tokens.css` der) minus
datapaletten og panellayouten som bare appen trenger. Navnene er de samme,
`--dm-*`, så en verdi kan sammenlignes linje for linje:

- Typografi: Inter (selvhostet under `/static/fonts/`, SIL Open Font License,
  vektene 400, 500 og 600), skalaen `--dm-text-xs` 12 px … `--dm-text-2xl`
  24 px, brødtekst 15 px, linjehøyde 1,45.
- Avstand: 4 px-skalaen `--dm-s-1` … `--dm-s-12`.
- Form: `--dm-radius-sm` 6 px for kontroller, `--dm-radius-md` 10 px for kort
  og dialoger; skygger bare på dialoger.
- Farge: den nøytrale skalaen, de semantiske flatene og teksten, aksenten
  (`#2b6cb0`, merkets blå), statusfargene `ok`/`warn`/`error`, hver med en
  `-soft`-bakgrunn, og det mørke temaet under `:root[data-theme="dark"]` og
  `prefers-color-scheme: dark`.
- Layout: topplinjen er `--dm-topbar-h` 48 px, bunnteksten `--dm-statusbar-h`
  28 px, administrasjonens sidenavigasjon `--dm-panel-min-w` 200 px; under
  760 px stables layouten og kontrollene vokser til 44 px berøringsflater.

Komponentene avbildes på Dataspatiums slik:

| Kontroll-klasse | Dataspatium-komponent | Utseende |
|---|---|---|
| `.btn`, `--primary`, `--secondary`, `--ghost`, `--danger`, `--small` | `dm-button` med `variant` og `size` | 32 px (26 px liten), radius 6 px, 13 px medium tekst; primær fylt aksent; danger rød tekst, rød ved hover |
| `.input`, `.select`, `.textarea`, `.field__label`, `.field__hint` | `.dm-field`, `.dm-label`, `.dm-help` | 32 px, feltkant, fokusring innenfor; tekstområder i monospace |
| `.badge` | `dm-badge` | pille, 12 px medium |
| `.card` | `dm-panel[card]`, `.dm-card` | flate, kant, radius 10 px, ingen skygge |
| `.table` i `.table-wrap` | `dm-table` | 13 px, overskrift på surface-2 ved 34 px, 30 px rader, sortert overskrift i aksent |
| `.nav a`, `.sidenav__list a` | `.dm-list-item` | 13 px, radius 6 px, hover-flate, gjeldende i accent-soft |
| `.alert` | `.dm-toast` | flate med en 3 px farget venstrekant |
| `dialog` | `dialog.dm-dialog` | 560 px, radius 10 px, stor skygge, bakgrunn |
| `.consent` | `.dm-course-task` | surface-2 med en aksentkant til venstre |
| `.stat` | et kort med `--dm-text-2xl` | tabelltall |

Dataspatiums regler gjelder også på serverens sider: høyst én primærknapp per
visning; destruktive handlinger bruker danger-varianten og en
bekreftelsesdialog; tall høyrestilt med tabelltall; datoer `YYYY-MM-DD`,
tider `HH:MM`; alt nåbart med tastatur med en synlig fokusring; ingen
animasjon utover korte overganger, ingen i det hele tatt under
`prefers-reduced-motion`.

## Merket

Serverens merke er søsken til Dataspatiums: der Dataspatium viser tre
stablede ark, viser Kontroll tre sammenkoblede noder (en graf): hule ringer
med radius 2,6, én i midten til venstre forbundet med to linjer til de to til
høyre, hvite på den samme blå platen `#2b6cb0` med hjørneradius 7 i et
kvadrat på 32 enheter, alt med samme strekbredde 2,2. Den hvite fargen
beholder Dataspatiums marger nøyaktig (x 7,4–24,6, y 5,08–26,92 av boksen).
Kilden er `opencde/ui/static/icon.svg`; `icon-32.png`, `icon-180.png`,
`icon-192.png`, `icon-512.png` og `favicon.ico` rendres fra den (PNG-filene
med Edge headless på gjennomsiktig bakgrunn, ICO-filen omslutter PNG-filene
på 16, 32 og 48 px). Bruk SVG-en der siden kan, behold platen, og fargelegg
ikke merket på nytt.

## Skriving

- Korte overskrifter som navngir objektet: "Brukere", "Nytt prosjekt",
  "Faresone".
- Knapper sier hva som skjer: "Opprett bruker", "Roter hemmelighet", ikke
  "OK".
- Hjelpetekster forklarer konsekvenser i én setning ved siden av feltet.
- Feil- og meldingstekster gjentar aldri brukerinndata og avslører aldri om
  en konto finnes ("Brukernavnet eller passordet er ikke riktig.").
- Hver tekst kommer fra språkkatalogene gjennom `t("key")` (se "Språklaget"
  nedenfor); engelsk er kilden, og de andre seks språkene følger Dataspatiums
  ordliste. Termer følger spesifikasjonene (topic, viewpoint, client,
  redirect URI, scope, role), og API-termer forblir som de er på alle språk.

## Språklaget

Sidene finnes på README-ens sju språk. Mekanikken er Dataspatiums: én flat
katalog per språk i `opencde/ui/i18n/<lang>.json` med punkterte nøkler og
`{name}`-parametere, de samme nøkkelnavnene der de to produktene deler et
begrep (`opencde.signin`, `opencde.signout`, `opencde.project`,
`opencde.kind.topics`, `common.cancel`, `common.save` …), og egne områder for
resten (`nav.*`, `account.*`, `docs.*`, `admin.*`, `notice.*`, `js.*`).

- Maler og makroer kaller `t("key")` eller `t("key", name=value)`;
  forespørselens språk ligger i en kontekstvariabel som `render()` setter, så
  importerte makroer oversettes også. Python-kode som bygger en sidetekst før
  gjengivelse, bruker `tr(request, "key")`.
- Språket velges per forespørsel: `?lang=xx` (huskes i cookien `opencde_lang`
  i et år), cookien, nettleserens `Accept-Language` (rent `no` betyr bokmål),
  engelsk. Bunnteksten på hver side bærer velgeren.
- Skript holder aldri tekster: `base.html` legger de få strengene skriptene
  trenger, i `data-t-*`-attributter på `<html>` (filterboks, radantall,
  bekreftelsesdialogen, kopieringstilbakemelding).
- En nøkkel som mangler på et annet språk, faller tilbake til engelsk; en
  nøkkel som mangler overalt, gjengis som nøkkelen selv. Enhetstesten
  `test_every_language_has_every_key_of_the_english_source` holder de sju
  katalogene identiske i nøkkelsett og parametere, så legg hver ny nøkkel til
  i alle i samme commit.
- Meldingene konto-, prosjekt- og klientkoden reiser ved ugyldig inndata
  (`UserFacingError` med nøkkel og parametere, delt med CLI-et), oversettes
  ved sidegrensen med `tr_error(request, exc)`; CLI-et og API-et beholder den
  engelske teksten.

## JavaScript-regler

- Én inngangsmodul per sidetype (`admin.js`), som importerer små moduler
  (`table.js`, `confirm.js`, `copy.js`). Bygg DOM med `createElement` og
  `textContent`.
- Forbedre bare det som finnes: les `data-*`-attributter, aldri konfigurasjon
  fra inline-skript.
- Et skjema som blir på siden sin, kan ha `data-inline` (`inline.js`): det lagrer med `fetch`, og `main`-elementet på siden serveren svarer med, erstatter det gamle. Siden tolkes hel med `DOMParser`, så serverens escaping gjelder, og skjemaet sendes på vanlig måte hvis noe går galt.
- Hold atferden reversibel: en side må gjøre det rette hvis modulen ikke kan
  lastes.
