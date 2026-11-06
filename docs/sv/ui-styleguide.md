# Stilguide för gränssnittet

Varje sida servern renderar (inloggning och samtycke, Documents API-sidorna,
konto, administration) delar ett utseende och en uppsättning regler. Den här
guiden är normerande för nya sidor (ADR 0004).

## Principer

1. **Serverrenderat, fungerar utan JavaScript.** Varje handling är en
   formulär-POST; JavaScript gör bara saker smidigare (filtrering, sortering,
   bekräftelsedialoger, kopieringsknappar).
2. **En källa till designen, och det är Dataspatiums.** Ägaren beslutade att
   serverns sidor och Dataspatium-appen delar ett utseende, baserat på
   Dataspatiums, och som Dataspatiums upphovsrättsinnehavare tillät Kontroll
   att använda den designen trots de olika licenserna (2026-11-05). Färger,
   typografi, avstånd och radier kommer från `opencde/ui/static/css/tokens.css`,
   som bär Dataspatiums tokens med deras `--dm-*`-namn; komponenter från
   `components.css`, som uttrycker Dataspatiums komponenter på serverns rena
   HTML. Hårdkoda aldrig en färg eller ett pixelvärde i en mall, och när
   Dataspatiums tokens ändras, ändra våra på samma sätt.
3. **Strikt CSP.** Inga inline-`<script>` eller `style=`, inga `on*`-attribut,
   ingen `innerHTML` med serverdata, inget CDN. Skript är ES-moduler under
   `/static/js/`, laddade med `<script type="module">`.
4. **Säkert som standard.** Varje formulär bär en signerad `form_token`; sidor
   som ändrar data kontrollerar den, webbläsarens `Sec-Fetch-Site`/`Origin`
   och, för farliga handlingar, användarens eget lösenord. Hemligheter visas
   en gång.
5. **Tillgängligt.** Semantisk HTML, riktiga `<label>`, synligt fokus,
   kontrast enligt WCAG 2.2 AA, `aria-current`, `role="status"` för
   meddelanden. Playwright med axe-core kontrollerar varje adminsida
   (`uv run pytest -m ui`).

## Layout

- `base.html`: sidhuvud (märke + `{% block nav %}`), `<main id="main">`,
  sidfot. Använd `page--narrow` som body-klass för enkolumnsformulär.
- Adminsidor utökar `admin/_page.html`: sidonavigering (`admin_nav`), ett
  meddelandeområde, sedan sidan i `{% block admin %}`. Innehållet är en
  kolumn av `.card`, var och en med en `<h2>`.
- Tabeller ligger i `.table-wrap > table.table`. Lägg till `data-filterable`
  för en filterruta (visas när det finns fler än fem rader) och
  `data-sortable` för klicksorterbara rubriker.

## Komponenter (makron, tillgängliga i varje mall)

| Makro | Användning |
|---|---|
| `field(name, label, type, value, …)` | Text-, lösenords-, e-post- och URL-fält med etikett och valfri hjälptext |
| `select_field(name, label, options, selected)` | `<select>`; `options` är en lista av `(value, text)` |
| `textarea_field(name, label, value, rows)` | Flerradsfält, ett värde per rad för listor |
| `checkbox(name, label, checked)` | Ett booleskt värde med sin etikett |
| `confirm_password(form_id)` | Fältet "ditt lösenord" som farliga formulär behöver |
| `button(text, kind, name, value)` | `primary`, `secondary`, `danger`; `formnovalidate` för Avbryt |
| `alert(kind, text, title)` | Rutor av typen `error`, `success`, `warning`, `info` |
| `notice_box(notice, kind)` | Resultatet av föregående handling (från `?notice=`) |
| `user_nav(web_user, signout_token)` | Inloggad användare och utloggningsformulär i sidhuvudet |
| `when(iso)` | Ett `<time>`-element för en ISO-tidsstämpel |

Märken: `.badge` (accent), `.badge--neutral`, `.badge--success`,
`.badge--warning`, `.badge--danger`. Riskzoner: `.card.card--danger` med ett
formulär per destruktiv handling och `data-confirm="fråga"` på formuläret.

## Tokens och det delade utseendet

`tokens.css` är Dataspatiums token-fil (`src/ui/design/tokens.css` där) minus
datapaletten och panellayouten som bara appen behöver. Namnen är desamma,
`--dm-*`, så att ett värde kan jämföras rad för rad:

- Typografi: Inter (självhostad under `/static/fonts/`, SIL Open Font
  License, vikterna 400, 500 och 600), skalan `--dm-text-xs` 12 px …
  `--dm-text-2xl` 24 px, brödtext 15 px, radhöjd 1,45.
- Avstånd: 4 px-skalan `--dm-s-1` … `--dm-s-12`.
- Form: `--dm-radius-sm` 6 px för kontroller, `--dm-radius-md` 10 px för kort
  och dialoger; skuggor bara på dialoger.
- Färg: den neutrala skalan, de semantiska ytorna och texten, accenten
  (`#2b6cb0`, märkets blå), statusfärgerna `ok`/`warn`/`error`, var och en
  med en `-soft`-bakgrund, och det mörka temat under
  `:root[data-theme="dark"]` och `prefers-color-scheme: dark`.
- Layout: toppraden är `--dm-topbar-h` 48 px, sidfoten `--dm-statusbar-h`
  28 px, administrationens sidonavigering `--dm-panel-min-w` 200 px; under
  760 px staplas layouten och kontrollerna växer till 44 px träffytor.

Komponenterna avbildas på Dataspatiums så här:

| Kontroll-klass | Dataspatium-komponent | Utseende |
|---|---|---|
| `.btn`, `--primary`, `--secondary`, `--ghost`, `--danger`, `--small` | `dm-button` med `variant` och `size` | 32 px (26 px liten), radie 6 px, 13 px medium text; primär fylld accent; danger röd text, röd vid hovring |
| `.input`, `.select`, `.textarea`, `.field__label`, `.field__hint` | `.dm-field`, `.dm-label`, `.dm-help` | 32 px, fältkant, fokusring inuti; textrutor med fast breddsteg |
| `.badge` | `dm-badge` | pill, 12 px medium |
| `.card` | `dm-panel[card]`, `.dm-card` | yta, kant, radie 10 px, ingen skugga |
| `.table` i `.table-wrap` | `dm-table` | 13 px, rubrik på surface-2 vid 34 px, 30 px rader, sorterad rubrik i accent |
| `.nav a`, `.sidenav__list a` | `.dm-list-item` | 13 px, radie 6 px, hovring på yta, aktuell i accent-soft |
| `.alert` | `.dm-toast` | yta med en 3 px färgad vänsterkant |
| `dialog` | `dialog.dm-dialog` | 560 px, radie 10 px, stor skugga, bakgrundsskikt |
| `.consent` | `.dm-course-task` | surface-2 med en accentkant till vänster |
| `.stat` | ett kort med `--dm-text-2xl` | tabellsiffror |

Dataspatiums regler gäller också på serverns sidor: högst en primärknapp per
vy; destruktiva handlingar använder danger-varianten och en
bekräftelsedialog; tal högerställda med tabellsiffror; datum `YYYY-MM-DD`,
tider `HH:MM`; allt nåbart med tangentbord med synlig fokusring; ingen
animation utöver korta övergångar, inga alls under `prefers-reduced-motion`.

## Märket

Serverns märke är syskonet till Dataspatiums: där Dataspatium visar tre
staplade blad visar Kontroll tre sammankopplade noder (en graf): ihåliga
ringar med radie 2,6, en i mitten till vänster förbunden med två linjer till
de två till höger, vita på samma blå platta `#2b6cb0` med hörnradie 7 i en
32-enheters kvadrat, allt med samma linjebredd 2,2. Den vita färgen behåller
Dataspatiums marginaler exakt (x 7,4–24,6, y 5,08–26,92 av rutan). Källan är
`opencde/ui/static/icon.svg`; `icon-32.png`, `icon-180.png`, `icon-192.png`,
`icon-512.png` och `favicon.ico` renderas från den (PNG-filerna med Edge
headless på transparent bakgrund, ICO-filen omsluter PNG-filerna på 16, 32
och 48 px). Använd SVG:n där sidan kan, behåll plattan och färga inte om
märket.

## Skrivande

- Korta rubriker som namnger objektet: "Användare", "Nytt projekt", "Riskzon".
- Knappar säger vad som händer: "Skapa användare", "Rotera hemlighet", inte
  "OK".
- Hjälptexter förklarar konsekvenser i en mening bredvid fältet.
- Fel- och meddelandetexter ekar aldrig användarindata och avslöjar aldrig om
  ett konto finns ("Användarnamnet eller lösenordet är inte korrekt.").
- Varje text kommer från språkkatalogerna genom `t("key")` (se "Språklagret"
  nedan); engelska är källan och de andra sex språken följer Dataspatiums
  ordlista. Termerna följer specifikationerna (topic, viewpoint, client,
  redirect URI, scope, role) och API-termer förblir som de är på varje språk.

## Språklagret

Sidorna finns på README:ns sju språk. Mekaniken är Dataspatiums: en platt
katalog per språk i `opencde/ui/i18n/<lang>.json` med punktade nycklar och
`{name}`-parametrar, samma nyckelnamn där de två produkterna delar ett
begrepp (`opencde.signin`, `opencde.signout`, `opencde.project`,
`opencde.kind.topics`, `common.cancel`, `common.save` …), och egna områden
för resten (`nav.*`, `account.*`, `docs.*`, `admin.*`, `notice.*`, `js.*`).

- Mallar och makron anropar `t("key")` eller `t("key", name=value)`; begärans
  språk ligger i en kontextvariabel som `render()` sätter, så att importerade
  makron också översätts. Python-kod som bygger en sidtext före rendering
  använder `tr(request, "key")`.
- Språket väljs per begäran: `?lang=xx` (kommer ihåg i kakan `opencde_lang` i
  ett år), kakan, webbläsarens `Accept-Language` (ren `no` betyder bokmål),
  engelska. Sidfoten på varje sida bär växlaren.
- Skript håller aldrig texter: `base.html` lägger de få strängar skripten
  behöver i `data-t-*`-attribut på `<html>` (filterruta, radantal,
  bekräftelsedialogen, kopieringsåterkoppling).
- En nyckel som saknas på ett annat språk faller tillbaka på engelska; en
  nyckel som saknas överallt renderas som nyckeln själv. Enhetstestet
  `test_every_language_has_every_key_of_the_english_source` håller de sju
  katalogerna identiska i nyckeluppsättningar och parametrar, så lägg till
  varje ny nyckel i alla i samma commit.
- Meddelandena som konto-, projekt- och klientkoden ger vid ogiltig indata
  (`UserFacingError` med nyckel och parametrar, delade med CLI:t) översätts
  vid sidgränsen med `tr_error(request, exc)`; CLI:t och API:t behåller den
  engelska texten.

## JavaScript-regler

- En ingångsmodul per sidtyp (`admin.js`), som importerar små moduler
  (`table.js`, `confirm.js`, `copy.js`). Bygg DOM med `createElement` och
  `textContent`.
- Förbättra bara det som finns: läs `data-*`-attribut, aldrig konfiguration
  från inline-skript.
- Ett formulär som stannar på sin sida kan ha `data-inline` (`inline.js`): det sparar med `fetch`, och `main`-elementet på sidan som servern svarar med ersätter det gamla. Sidan tolkas hel med `DOMParser`, så serverns escaping gäller, och formuläret skickas på vanligt sätt om något går fel.
- Håll beteendet reversibelt: en sida måste göra rätt om modulen inte kan
  laddas.
