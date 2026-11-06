# Orðasafn

Orðin sem þessi skjölun notar og hvað þau merkja hér. Mál, athugasemd, sjónarhorn og
verkefni eru sömu orð og í Dataspatium.

## Staðlar

| Orð | Hvað það merkir hér |
|---|---|
| OpenCDE | API buildingSMART fyrir sameiginlegt gagnaumhverfi: Foundation, BCF og Documents |
| CDE | Common data environment, sameiginlegt gagnaumhverfi: sameiginlegi staðurinn fyrir upplýsingar verkefnis |
| Foundation API | Sá hluti OpenCDE sem segir hvaða API þjónn býður, hvernig á að skrá sig inn og hver þú ert |
| BCF | BIM Collaboration Format, fyrir mál um byggingarlíkan. BCF API 3.0 og 2.1 eru vefviðmót þess |
| Documents API | Sá hluti OpenCDE sem hleður upp og velur skjöl á síðum í vafranum |
| IFC | Industry Foundation Classes, opna skráarsniðið fyrir byggingarlíkön |

## Í verkefni

| Orð | Hvað það merkir hér |
|---|---|
| Verkefni | Sameiginlega rýmið: meðlimirnir, málin og skjölin |
| Meðlimur, hlutverk | Einhver í verkefni, sem viewer, contributor, editor eða manager. Hlutverkið ræður hvað viðkomandi má gera |
| Stjórnandi | Notandi sem sér um notendur, verkefni og biðlara. Það er ekki hlutverk í verkefni og veitir ekki aðgang að efni verkefnis |
| Viðbætur (extensions) | Gildin sem verkefni leyfir fyrir tegund, stöðu, forgang, merkimiða og svo framvegis |
| Mál (topic) | Eitthvað til að gera, athuga eða svara. Orð BCF er topic |
| Athugasemd | Ábending við mál, sem getur vísað á sjónarhorn |
| Sjónarhorn (viewpoint) | Vistuð sýn á líkanið: myndavél, einingar og mynd |
| Eining | Byggingarhluti sem sjónarhorn nefnir, með `GlobalId` sínu |
| Skyndimynd (snapshot) | Mynd sjónarhorns |
| Atburður | Færsla í sögu máls eða athugasemdar |
| Skjal, útgáfa | Skrá með titli; ný upphleðsla hennar er ný útgáfa |

## Innskráning

| Orð | Hvað það merkir hér |
|---|---|
| Biðlari | Forrit sem vinnur fyrir hönd notanda, skráð á þjóninum |
| Opinber biðlari | Biðlari sem getur ekki varðveitt leyndarmál, svo sem vafra- eða tölvuforrit |
| Trúnaðarbiðlari | Biðlari á eigin þjóni, sem getur varðveitt leyndarmál |
| Sjálfskráning | Að biðlari skrái sig sjálfur, óvirkt í upphafi |
| Redirect-URI | Vistfangið sem þjónninn sendir vafrann aftur á eftir innskráningu |
| PKCE | Einnota sönnun þess að sá sem innleysir kóðann er sá sem bað um hann |
| Aðgangstóki | Skammlíf sönnun sem er send með hverri beiðni til API |
| Endurnýjunartóki | Lengri sönnun sem gefur nýjan aðgangstóka og gildir einu sinni |
| Scope | Til hvers má nota tóka: `profile`, `bcf`, `documents` eða `admin` |

## Líkanið sem graf

| Orð | Hvað það merkir hér |
|---|---|
| IFC-graf | Upphlaðið líkan sem hnútar og tengsl í gagnagrunninum, valfrjálst |
| `GlobalId` | Varanlegt auðkenni staks í IFC-skrá |
| `SAME_AS` | Tengslin frá einingu sjónarhorns til staksins í líkani |
| GTIN | Global Trade Item Number, númer vöru; hér lesið úr eiginleikasafninu `Reuse` |
| Cypher | Fyrirspurnamál grafgagnagrunnsins |
| Bolt | Eigin tenging gagnagrunnsins, valfrjáls fyrir þá sem spyrja grafið beint |

## Að reka þjóninn

| Orð | Hvað það merkir hér |
|---|---|
| Stafli | Gámarnir sem mynda keyrandi þjón: API, gagnagrunnurinn og í rekstri milliþjónninn og öryggisafritunin |
| Seed | `opencde seed`, sem hleður sýnigögnum í tóman gagnagrunn |
| Capabilities | `/.well-known/kontroll`, sem segir hvað þessi þjónn hefur virkjað |
| Beiðnaskrá | Valfrjáls skrá yfir beiðnirnar sem þjónninn hefur svarað |
| Endurskoðunarskrá | Skráin yfir hver hefur skráð sig inn og breytt hverju |
