# Stílleiðarvísir viðmótsins

Hver síða sem þjónninn birtir (innskráning og samþykki, Documents API-síður,
reikningur, stjórnun) deilir einu útliti og einu reglusetti. Þessi
leiðarvísir er bindandi fyrir nýjar síður (ADR 0004).

## Meginreglur

1. **Birt á þjóni, virkar án JavaScript.** Hver aðgerð er POST eyðublaðs;
   JavaScript gerir hlutina aðeins liprari (síun, röðun, staðfestingargluggar,
   afritunarhnappar).
2. **Ein uppspretta hönnunar, og hún er Dataspatium.** Eigandinn ákvað að
   síður þjónsins og Dataspatium-forritið deili einu útliti, byggðu á
   Dataspatium, og leyfði sem rétthafi Dataspatium Dataregium að nota þá hönnun
   þrátt fyrir ólík leyfi (2026-11-05). Litir, letur, bil og rúnnun koma úr
   `opencde/ui/static/css/tokens.css`, sem ber tókana Dataspatium með
   `--dm-*`-heitum sínum; íhlutir úr `components.css`, sem tjáir íhluti
   Dataspatium á hreinu HTML þjónsins. Harðkóðaðu aldrei lit eða pixlagildi
   í sniðmáti, og þegar tókar Dataspatium breytast, breyttu okkar á sama
   hátt.
3. **Strangt CSP.** Engin innfelld `<script>` eða `style=`, engin
   `on*`-eigindi, ekkert `innerHTML` með þjónsgögnum, ekkert CDN. Skriftur
   eru ES-einingar undir `/static/js/`, hlaðnar með `<script type="module">`.
4. **Öruggt sjálfgefið.** Hvert eyðublað ber undirritaðan `form_token`; síður
   sem breyta gögnum athuga hann, `Sec-Fetch-Site`/`Origin` vafrans og, fyrir
   hættulegar aðgerðir, eigið lykilorð notandans. Leyndarmál eru sýnd einu
   sinni.
5. **Aðgengilegt.** Merkingarbært HTML, raunveruleg `<label>`, sýnilegur
   fókus, WCAG 2.2 AA-birtuskil, `aria-current`, `role="status"` fyrir
   tilkynningar. Playwright með axe-core athugar hverja stjórnunarsíðu
   (`uv run pytest -m ui`).

## Uppsetning

- `base.html`: haus (merki + `{% block nav %}`), `<main id="main">`, fótur.
  Notaðu `page--narrow` sem body-klasa fyrir eyðublöð í einum dálki.
- Stjórnunarsíður víkka `admin/_page.html`: hliðarleiðsögn (`admin_nav`),
  tilkynningasvæði, síðan síðan í `{% block admin %}`. Innihaldið er dálkur
  af `.card`, hvert með einni `<h2>`.
- Töflur eru í `.table-wrap > table.table`. Bættu við `data-filterable` fyrir
  síureit (birtist þegar raðir eru fleiri en fimm) og `data-sortable` fyrir
  hausa sem raða við smell.

## Íhlutir (fjölvar, tiltækir í hverju sniðmáti)

| Fjölvi | Notkun |
|---|---|
| `field(name, label, type, value, …)` | Texta-, lykilorðs-, netfangs- og URL-reitir með merkimiða og valkvæðri vísbendingu |
| `select_field(name, label, options, selected)` | `<select>`; `options` er listi af `(value, text)` |
| `textarea_field(name, label, value, rows)` | Fjöllínureitur, eitt gildi í hverri línu fyrir lista |
| `checkbox(name, label, checked)` | Boole-gildi með merkimiða sínum |
| `confirm_password(form_id)` | Reiturinn „lykilorðið þitt“ sem hættuleg eyðublöð þurfa |
| `button(text, kind, name, value)` | `primary`, `secondary`, `danger`; `formnovalidate` fyrir Hætta við |
| `alert(kind, text, title)` | Kassar af gerðinni `error`, `success`, `warning`, `info` |
| `notice_box(notice, kind)` | Niðurstaða fyrri aðgerðar (úr `?notice=`) |
| `user_nav(web_user, signout_token)` | Innskráður notandi og útskráningareyðublað í hausnum |
| `when(iso)` | `<time>`-stak fyrir ISO-tímastimpil |

Merkimiðar: `.badge` (áhersla), `.badge--neutral`, `.badge--success`,
`.badge--warning`, `.badge--danger`. Hættusvæði: `.card.card--danger` með einu
eyðublaði fyrir hverja eyðandi aðgerð og `data-confirm="spurning"` á
eyðublaðinu.

## Tókar og sameiginlega útlitið

`tokens.css` er tókaskrá Dataspatium (`src/ui/design/tokens.css` þar) að
frádreginni gagnalitapallettunni og spjaldauppsetningunni sem forritið eitt
þarf. Heitin eru þau sömu, `--dm-*`, svo bera megi gildi saman línu fyrir
línu:

- Letur: Inter (hýst sjálft undir `/static/fonts/`, SIL Open Font License,
  þyngdir 400, 500 og 600), kvarðinn `--dm-text-xs` 12 px … `--dm-text-2xl`
  24 px, meginmál 15 px, línuhæð 1,45.
- Bil: 4 px kvarðinn `--dm-s-1` … `--dm-s-12`.
- Form: `--dm-radius-sm` 6 px fyrir stýringar, `--dm-radius-md` 10 px fyrir
  kort og glugga; skuggar aðeins á gluggum.
- Litur: hlutlausi kvarðinn, merkingarbæru yfirborðin og textinn, áherslan
  (`#2b6cb0`, blái litur merkisins), stöðulitirnir `ok`/`warn`/`error`, hver
  með `-soft`-bakgrunni, og dökka þemað undir `:root[data-theme="dark"]` og
  `prefers-color-scheme: dark`.
- Uppsetning: toppstikan er `--dm-topbar-h` 48 px, fóturinn
  `--dm-statusbar-h` 28 px, hliðarleiðsögn stjórnunarinnar `--dm-panel-min-w`
  200 px; undir 760 px staflast uppsetningin og stýringar stækka í 44 px
  snertifleti.

Íhlutirnir varpast á íhluti Dataspatium þannig:

| Dataregium-klasi | Dataspatium-íhlutur | Útlit |
|---|---|---|
| `.btn`, `--primary`, `--secondary`, `--ghost`, `--danger`, `--small` | `dm-button` með `variant` og `size` | 32 px (26 px lítill), rúnnun 6 px, 13 px medium-texti; primary fylltur áherslulit; danger rauður texti, rauður við yfirsveim |
| `.input`, `.select`, `.textarea`, `.field__label`, `.field__hint` | `.dm-field`, `.dm-label`, `.dm-help` | 32 px, reitarammi, fókushringur innan í; textasvæði með jafnbreiðu letri |
| `.badge` | `dm-badge` | pilla, 12 px medium |
| `.card` | `dm-panel[card]`, `.dm-card` | yfirborð, rammi, rúnnun 10 px, enginn skuggi |
| `.table` í `.table-wrap` | `dm-table` | 13 px, haus á surface-2 í 34 px, 30 px raðir, raðaður haus í áherslulit |
| `.nav a`, `.sidenav__list a` | `.dm-list-item` | 13 px, rúnnun 6 px, yfirborð við yfirsveim, núverandi í accent-soft |
| `.alert` | `.dm-toast` | yfirborð með 3 px lituðum vinstri jaðri |
| `dialog` | `dialog.dm-dialog` | 560 px, rúnnun 10 px, stór skuggi, bakgrunnur |
| `.consent` | `.dm-course-task` | surface-2 með áherslujaðri til vinstri |
| `.stat` | kort með `--dm-text-2xl` | töflutölur |

Reglur Dataspatium gilda líka á síðum þjónsins: mest einn primary-hnappur í
hverri sýn; eyðandi aðgerðir nota danger-afbrigðið og staðfestingarglugga;
tölur hægristilltar með töflutölum; dagsetningar `YYYY-MM-DD`, tímar `HH:MM`;
allt aðgengilegt með lyklaborði með sýnilegum fókushring; engar hreyfimyndir
umfram stuttar millifærslur, engar undir `prefers-reduced-motion`.

## Merkið

Merki þjónsins er systkini merkis Dataspatium: þar sem Dataspatium sýnir þrjú
stöfluð blöð sýnir Dataregium þrjá tengda hnúta (graf): hola hringi með radíus
2,6, einn í miðju til vinstri tengdan með tveimur línum við þá tvo til hægri,
hvíta á sömu bláu plötunni `#2b6cb0` með hornarúnnun 7 í 32 eininga
ferningi, allt með sömu strikbreidd 2,2. Hvíta litunin heldur spássíum
Dataspatium nákvæmlega (x 7,4–24,6, y 5,08–26,92 af kassanum). Upprunaskráin
er `opencde/ui/static/icon.svg`; `icon-32.png`, `icon-180.png`,
`icon-192.png`, `icon-512.png` og `favicon.ico` eru teiknuð úr henni
(PNG-skrárnar með Edge headless á gegnsæjum bakgrunni, ICO-skráin umlykur 16,
32 og 48 px PNG-skrárnar). Notaðu SVG þar sem síðan getur, haltu plötunni og
endurlitaðu ekki merkið.

## Skrif

- Stuttar fyrirsagnir sem nefna hlutinn: „Notendur“, „Nýtt verkefni“,
  „Hættusvæði“.
- Hnappar segja hvað gerist: „Búa til notanda“, „Skipta um leyndarmál“, ekki
  „Í lagi“.
- Vísbendingar skýra afleiðingar í einni setningu við hlið reitsins.
- Villu- og tilkynningatextar enduróma aldrei inntak notanda og gefa aldrei
  upp hvort reikningur sé til („Notandanafnið eða lykilorðið er ekki rétt.“).
- Hver texti kemur úr tungumálaskránum um `t("key")` (sjá „Tungumálalagið“
  hér fyrir neðan); enska er uppruninn og hin sex tungumálin fylgja orðalista
  Dataspatium. Hugtök fylgja forskriftunum (topic, viewpoint, client,
  redirect URI, scope, role), og API-hugtök haldast óbreytt á hverju
  tungumáli.

## Tungumálalagið

Síðurnar eru til á sjö tungumálum README. Vélbúnaðurinn er Dataspatium: ein
flöt skrá á hvert tungumál í `opencde/ui/i18n/<lang>.json` með punktalyklum
og `{name}`-stikum, sömu lykilheiti þar sem vörurnar tvær deila hugtaki
(`opencde.signin`, `opencde.signout`, `opencde.project`,
`opencde.kind.topics`, `common.cancel`, `common.save` …), og eigin svæði fyrir
hitt (`nav.*`, `account.*`, `docs.*`, `admin.*`, `notice.*`, `js.*`).

- Sniðmát og fjölvar kalla `t("key")` eða `t("key", name=value)`; tungumál
  beiðninnar er í samhengisbreytu sem `render()` setur, svo innfluttir fjölvar
  þýðast líka. Python-kóði sem byggir síðutexta áður en birt er notar
  `tr(request, "key")`.
- Tungumálið er valið fyrir hverja beiðni: `?lang=xx` (munað í vefkökunni
  `opencde_lang` í eitt ár), vefkakan, `Accept-Language` vafrans (hreint `no`
  þýðir bokmál), enska. Fótur hverrar síðu ber skiptinn.
- Skriftur geyma aldrei texta: `base.html` setur þá fáu strengi sem
  skrifturnar þurfa í `data-t-*`-eigindi á `<html>` (síureitur, raðafjöldi,
  staðfestingarglugginn, afritunarsvörun).
- Lykill sem vantar á öðru tungumáli fellur aftur á ensku; lykill sem vantar
  alls staðar birtist sem lykillinn sjálfur. Einingaprófið
  `test_every_language_has_every_key_of_the_english_source` heldur
  lyklasettum og stikum skránna sjö eins, svo bættu hverjum nýjum lykli við
  þær allar í sömu innfærslu.
- Skilaboðin sem reiknings-, verkefnis- og biðlarakóðinn varpar við ógilt
  inntak (`UserFacingError` með lykli og stikum, deilt með CLI) eru þýdd á
  síðumörkunum með `tr_error(request, exc)`; CLI og forritaskilin halda enska
  textanum.

## JavaScript-reglur

- Ein inngangseining á hverja síðugerð (`admin.js`), sem flytur inn smáar
  einingar (`table.js`, `confirm.js`, `copy.js`). Byggðu DOM með
  `createElement` og `textContent`.
- Bættu aðeins það sem er til: lestu `data-*`-eigindi, aldrei stillingar úr
  innfelldum skriftum.
- Eyðublað sem helst á sinni síðu getur haft `data-inline` (`inline.js`): það vistar með `fetch`, og `main`-stak síðunnar sem þjónninn svarar með kemur í stað hins gamla. Síðan er þáttuð heil með `DOMParser`, svo að útskipting þjónsins gildir, og eyðublaðið er sent á venjulegan hátt ef eitthvað fer úrskeiðis.
- Haltu hegðuninni afturkræfri: síða þarf að gera rétt ef einingin hleðst
  ekki.
