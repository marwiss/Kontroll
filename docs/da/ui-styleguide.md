# UI-stilguide

Hver side, serveren renderer (login og samtykke, Documents API-sider, konto,
administration), deler ét udseende og ét sæt regler. Denne guide er normativ
for nye sider (ADR 0004).

## Principper

1. **Serverrenderet, virker uden JavaScript.** Hver handling er en
   formular-POST; JavaScript gør kun tingene glattere (filtrering, sortering,
   bekræftelsesdialoger, kopieringsknapper).
2. **Én kilde til designet, og det er Dataspatiums.** Ejeren besluttede, at
   serverens sider og Dataspatium-appen deler ét udseende, baseret på
   Dataspatiums, og som Dataspatiums rettighedshaver tillod Dataregium at bruge
   det design trods de forskellige licenser (2026-11-05). Farver, typografi,
   afstande og radier kommer fra `opencde/ui/static/css/tokens.css`, som
   bærer Dataspatiums tokens med deres `--dm-*`-navne; komponenter fra
   `components.css`, som udtrykker Dataspatiums komponenter på serverens rene
   HTML. Hardcode aldrig en farve eller en pixelværdi i en template, og når
   Dataspatiums tokens ændres, så ændr vores på samme måde.
3. **Streng CSP.** Ingen inline-`<script>` eller `style=`, ingen
   `on*`-attributter, ingen `innerHTML` med serverdata, intet CDN. Scripts er
   ES-moduler under `/static/js/`, indlæst med `<script type="module">`.
4. **Sikker som standard.** Hver formular bærer en signeret `form_token`;
   sider, der ændrer data, tjekker den, browserens `Sec-Fetch-Site`/`Origin`
   og, for farlige handlinger, brugerens eget kodeord. Hemmeligheder vises
   én gang.
5. **Tilgængelig.** Semantisk HTML, rigtige `<label>`s, synligt fokus, WCAG
   2.2 AA-kontrast, `aria-current`, `role="status"` for meddelelser.
   Playwright med axe-core tjekker hver adminside (`uv run pytest -m ui`).

## Layout

- `base.html`: sidehoved (mærke + `{% block nav %}`), `<main id="main">`,
  sidefod. Brug `page--narrow` som body-klasse til formularer i én kolonne.
- Adminsider udvider `admin/_page.html`: sidenavigation (`admin_nav`), et
  meddelelsesområde, derefter siden i `{% block admin %}`. Indholdet er en
  kolonne af `.card`s, hver med én `<h2>`.
- Tabeller ligger i `.table-wrap > table.table`. Tilføj `data-filterable` for
  en filterboks (vises, når der er mere end fem rækker) og `data-sortable`
  for kliksorterbare overskrifter.

## Komponenter (makroer, tilgængelige i hver template)

| Makro | Brug |
|---|---|
| `field(name, label, type, value, …)` | Tekst-, kodeords-, e-mail- og URL-felter med etiket og valgfri hjælpetekst |
| `select_field(name, label, options, selected)` | `<select>`; `options` er en liste af `(value, text)` |
| `textarea_field(name, label, value, rows)` | Flerlinjefelt, én værdi per linje for lister |
| `checkbox(name, label, checked)` | En boolesk værdi med sin etiket |
| `confirm_password(form_id)` | Feltet "dit kodeord", som farlige formularer kræver |
| `button(text, kind, name, value)` | `primary`, `secondary`, `danger`; `formnovalidate` for Afbryd |
| `alert(kind, text, title)` | Bokse af typen `error`, `success`, `warning`, `info` |
| `notice_box(notice, kind)` | Resultatet af den forrige handling (fra `?notice=`) |
| `user_nav(web_user, signout_token)` | Logget ind-bruger og logout-formular i sidehovedet |
| `when(iso)` | Et `<time>`-element for et ISO-tidsstempel |

Badges: `.badge` (accent), `.badge--neutral`, `.badge--success`,
`.badge--warning`, `.badge--danger`. Farezoner: `.card.card--danger` med én
formular per destruktiv handling og `data-confirm="spørgsmål"` på formularen.

## Tokens og det fælles udseende

`tokens.css` er Dataspatiums token-fil (`src/ui/design/tokens.css` dér) minus
datapaletten og panellayoutet, som kun appen har brug for. Navnene er de
samme, `--dm-*`, så en værdi kan sammenlignes linje for linje:

- Typografi: Inter (selvhostet under `/static/fonts/`, SIL Open Font License,
  vægtene 400, 500 og 600), skalaen `--dm-text-xs` 12 px … `--dm-text-2xl`
  24 px, brødtekst 15 px, linjehøjde 1,45.
- Afstand: 4 px-skalaen `--dm-s-1` … `--dm-s-12`.
- Form: `--dm-radius-sm` 6 px for kontroller, `--dm-radius-md` 10 px for kort
  og dialoger; skygger kun på dialoger.
- Farve: den neutrale skala, de semantiske flader og teksten, accenten
  (`#2b6cb0`, mærkets blå), statusfarverne `ok`/`warn`/`error`, hver med en
  `-soft`-baggrund, og det mørke tema under `:root[data-theme="dark"]` og
  `prefers-color-scheme: dark`.
- Layout: topbjælken er `--dm-topbar-h` 48 px, sidefoden `--dm-statusbar-h`
  28 px, administrationens sidenavigation `--dm-panel-min-w` 200 px; under
  760 px stables layoutet, og kontroller vokser til 44 px berøringsflader.

Komponenterne afbildes på Dataspatiums således:

| Dataregium-klasse | Dataspatium-komponent | Udseende |
|---|---|---|
| `.btn`, `--primary`, `--secondary`, `--ghost`, `--danger`, `--small` | `dm-button` med `variant` og `size` | 32 px (26 px lille), radius 6 px, 13 px medium tekst; primær udfyldt accent; danger rød tekst, rød ved hover |
| `.input`, `.select`, `.textarea`, `.field__label`, `.field__hint` | `.dm-field`, `.dm-label`, `.dm-help` | 32 px, feltkant, fokusring indeni; tekstområder i monospace |
| `.badge` | `dm-badge` | pille, 12 px medium |
| `.card` | `dm-panel[card]`, `.dm-card` | flade, kant, radius 10 px, ingen skygge |
| `.table` i `.table-wrap` | `dm-table` | 13 px, overskrift på surface-2 ved 34 px, 30 px rækker, sorteret overskrift i accent |
| `.nav a`, `.sidenav__list a` | `.dm-list-item` | 13 px, radius 6 px, hover-flade, aktuel i accent-soft |
| `.alert` | `.dm-toast` | flade med en 3 px farvet venstre kant |
| `dialog` | `dialog.dm-dialog` | 560 px, radius 10 px, stor skygge, baggrund |
| `.consent` | `.dm-course-task` | surface-2 med en accentkant til venstre |
| `.stat` | et kort med `--dm-text-2xl` | tabeltal |

Dataspatiums regler gælder også på serverens sider: højst én primærknap per
visning; destruktive handlinger bruger danger-varianten og en
bekræftelsesdialog; tal højrestillede med tabeltal; datoer `YYYY-MM-DD`,
tider `HH:MM`; alt tilgængeligt via tastatur med en synlig fokusring; ingen
animation ud over korte overgange, slet ingen under `prefers-reduced-motion`.

## Mærket

Serverens mærke er søskende til Dataspatiums: hvor Dataspatium viser tre
stablede ark, viser Dataregium tre forbundne noder (en graf): hule ringe med
radius 2,6, én i midten til venstre forbundet med to linjer til de to til
højre, hvide på den samme blå plade `#2b6cb0` med hjørneradius 7 i et kvadrat
på 32 enheder, alt med samme stregbredde 2,2. Den hvide farve beholder
Dataspatiums margener nøjagtigt (x 7,4–24,6, y 5,08–26,92 af boksen). Kilden
er `opencde/ui/static/icon.svg`; `icon-32.png`, `icon-180.png`,
`icon-192.png`, `icon-512.png` og `favicon.ico` renderes fra den (PNG-filerne
med Edge headless på transparent baggrund, ICO-filen omslutter PNG-filerne på
16, 32 og 48 px). Brug SVG'en, hvor siden kan, behold pladen, og omfarv ikke
mærket.

## Skrivning

- Korte overskrifter, der navngiver objektet: "Brugere", "Nyt projekt",
  "Farezone".
- Knapper siger, hvad der sker: "Opret bruger", "Rotér hemmelighed", ikke
  "OK".
- Hjælpetekster forklarer konsekvenser i én sætning ved siden af feltet.
- Fejl- og meddelelsestekster gentager aldrig brugerinput og afslører aldrig,
  om en konto findes ("Brugernavnet eller kodeordet er ikke korrekt.").
- Hver tekst kommer fra sprogkatalogerne gennem `t("key")` (se "Sproglaget"
  nedenfor); engelsk er kilden, og de andre seks sprog følger Dataspatiums
  ordliste. Termer følger specifikationerne (topic, viewpoint, client,
  redirect URI, scope, role), og API-termer forbliver, som de er, på alle
  sprog.

## Sproglaget

Siderne findes på README'ens syv sprog. Mekanikken er Dataspatiums: ét fladt
katalog per sprog i `opencde/ui/i18n/<lang>.json` med punkterede nøgler og
`{name}`-parametre, de samme nøglenavne, hvor de to produkter deler et begreb
(`opencde.signin`, `opencde.signout`, `opencde.project`,
`opencde.kind.topics`, `common.cancel`, `common.save` …), og egne områder til
resten (`nav.*`, `account.*`, `docs.*`, `admin.*`, `notice.*`, `js.*`).

- Templates og makroer kalder `t("key")` eller `t("key", name=value)`;
  forespørgslens sprog ligger i en kontekstvariabel, som `render()` sætter,
  så importerede makroer også oversættes. Python-kode, der bygger en
  sidetekst før rendering, bruger `tr(request, "key")`.
- Sproget vælges per forespørgsel: `?lang=xx` (huskes i cookien
  `opencde_lang` i et år), cookien, browserens `Accept-Language` (rent `no`
  betyder bokmål), engelsk. Sidefoden på hver side bærer skifteren.
- Scripts holder aldrig tekster: `base.html` lægger de få strenge, scripts
  har brug for, i `data-t-*`-attributter på `<html>` (filterboks,
  rækkeantal, bekræftelsesdialogen, kopieringsfeedback).
- En nøgle, der mangler på et andet sprog, falder tilbage til engelsk; en
  nøgle, der mangler overalt, renderes som nøglen selv. Enhedstesten
  `test_every_language_has_every_key_of_the_english_source` holder de syv
  kataloger identiske i deres nøglesæt og parametre, så tilføj hver ny nøgle
  til dem alle i samme commit.
- De beskeder, konto-, projekt- og klientkoden rejser ved ugyldigt input
  (`UserFacingError` med nøgle og parametre, delt med CLI'et), oversættes ved
  sidegrænsen med `tr_error(request, exc)`; CLI'et og API'et beholder den
  engelske tekst.

## JavaScript-regler

- Ét indgangsmodul per sidetype (`admin.js`), der importerer små moduler
  (`table.js`, `confirm.js`, `copy.js`). Byg DOM med `createElement` og
  `textContent`.
- Forbedr kun det, der findes: læs `data-*`-attributter, aldrig konfiguration
  fra inline-scripts.
- En formular, der bliver på sin side, kan have `data-inline` (`inline.js`): den gemmer med `fetch`, og `main`-elementet på den side, serveren svarer med, erstatter det gamle. Siden tolkes hel med `DOMParser`, så serverens escaping gælder, og formularen sendes på almindelig vis, hvis noget går galt.
- Hold adfærden reversibel: en side skal gøre det rigtige, hvis modulet ikke
  kan indlæses.
