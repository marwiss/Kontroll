# Persónuupplýsingar og varðveisla

Hvað Kontroll-þjónn geymir um fólk, hve lengi, og hver getur séð það. Þetta
er helmingur þjónsins af síðu sem er deilt með Dataspatium; helmingur
forritsins (hvað það geymir í vafranum og hvað það sendir) er í skjölun
Dataspatium. Sá sem rekur Kontroll fyrir aðra er ábyrgðaraðili þessara
gagna; síðan gefur staðreyndirnar fyrir eigin skrár.

## Hvað er geymt

| Gögn | Hvar | Innihald | Geymt |
|---|---|---|---|
| Notendareikningar | `User`-hnútar | notandanafn, fullt nafn, netfang (valkvætt), Argon2id-tætigildi lykilorðsins, stjórnandamerki, stofntími, síðasta innskráning | Þar til stjórnandi eyðir reikningnum |
| Verkefnisaðild | `MEMBER_OF`-vensl | notandi, verkefni, hlutverk | Þar til hún er fjarlægð |
| OAuth2-tókar | hnútarnir `AuthorizationCode`, `AccessToken`, `RefreshToken` | SHA-256-tætigildi (aldrei tókarnir sjálfir), notandi, biðlari, scope, tímar | Kóðar 60 s, aðgangstókar 1 klst., endurnýjunartókar 30 dagar (`OPENCDE_*_TTL_SECONDS`); hreinsunin eyðir þeim þegar þeir renna út eða eru afturkallaðir |
| Vafrasetur | `WebSession`-hnútar | notandi, stofn- og síðasta virknitími, vistfang biðlarans við innskráningu | 8 klukkustundir, eða 30 mínútna aðgerðaleysi; eytt við útskráningu |
| Misheppnaðar innskráningar | `SignInThrottle`-hnútar | tætigildi notandanafnsins, fjöldi villna, hvenær næsta tilraun er leyfð | sólarhring eftir síðustu villu; vel heppnuð innskráning fjarlægir hann |
| OAuth2-biðlarar | `Client`-hnútar | heiti, lýsing, vistfang, redirect-URI, tætt leyndarmál, `software_id`/`software_version`, hver bjó til | Þar til þeim er eytt; sjálfskráðir biðlarar sem eru ónotaðir í 30 daga er eytt ásamt tókum þeirra |
| BCF-gögn | hnútarnir `Topic`, `Comment`, `Viewpoint`, `Event` og tengdir | titlar, lýsingar og athugasemdir sem notendur skrifa, notandanöfn sem höfundar og ábyrgðarmenn, tímar, skyndimyndir, einingatilvísanir | Þar til málinu, athugasemdinni eða verkefninu er eytt |
| Skjöl | hnútarnir `Document` og `DocumentVersion`, skrár undir `OPENCDE_DATA_DIR` | titill, skráarheiti, stærð, SHA-256, sá sem hlóð upp, tími; skráin sjálf (sem getur innihaldið persónuupplýsingar, til dæmis nöfn í eigendasögu IFC-líkans) | Þar til útgáfunni eða verkefninu er eytt; öryggisafrit geyma afrit eins lengi og rekstraraðilinn geymir öryggisafritin |
| IFC-graf | `IfcModel`-hnútar og einingar hvers innflutts líkans | innihald IFC-skrárinnar sem grafgögn, þar á meðal `IfcOwnerHistory` verkefnisins; með `OPENCDE_IFC_LPG_LOSSLESS`, sem er sjálfgefið, öll skráin, með hausnum og hverri owner history | Líkön sem hafa verið leyst af hólmi eða mistókust eru fjarlægð með `opencde ifc-lpg prune`; annars með skjalaútgáfunni |
| IFC-sannprófun | `IfcValidation`-hnútar undir útgáfum skjala | hve margar athugasemdir skráin hefur og hvenær hún var prófuð, og allt að 10.000 athugasemdir sem geta vitnað í línur úr skránni | Með útgáfu skjalsins eða verkefninu |
| Endurskoðunarskrá | `AuditEvent`-hnútar | hvað gerðist (innskráning, tóki gefinn út, biðlari skráður, hlutverki breytt …), hver gerði það, vistfang biðlarans, tími, request-id | Rennur ekki út af sjálfu sér; stjórnendur geta flutt hana út sem CSV og rekstraraðilinn eyðir samkvæmt eigin stefnu |
| Beiðnaskrá (valkvæð) | `RequestLog`-hnútar | aðferð, slóð án fyrirspurnarstrengs, aðgerð, staða, tímalengd, bætafjöldi, request-id, notanda- eða biðlaraauðkenni; aldrei hausar, meginmál eða tókar | `OPENCDE_REQUEST_LOG_RETENTION_HOURS` (72 sjálfgefið); óvirk nema `OPENCDE_REQUEST_LOG_ENABLED=true` |
| Upphals- og valsetur | hnútarnir `UploadSession`, `UploadPart`, `SelectionSession` og tímabundnar hlutaskrár | hver hóf ferlið, hvaða skrár, callback-vistfang, tímar | 24 klukkustundir fyrir upphal, 10 mínútur fyrir síðutenglana; þjónninn hreinsar |
| Atvikaskrár þjónsins | staðalúttak gámsins (JSON-línur) | request-id, slóð, staða, tímalengd, notanda- eða biðlaraauðkenni, vistfang biðlarans frá treysta milliþjóninum; aldrei meginmál, tókar, kóðar eða lykilorð | Eins lengi og rekstraraðilinn geymir gámaskrár |

Öryggisafrit gerð með `opencde backup` eða þjónustunni `backup` innihalda allt
ofangreint nema atvikaskrár þjónsins, dulkóðuð eða ekki eftir vali
rekstraraðilans ([deploy/backup.md](../deploy/backup.md)).

## Hver sér hvað

- Meðlimir verkefnis sjá mál þess, athugasemdir, viewpoint og skjöl um
  forritaskilin; hlutverkið ræður hverju þeir mega breyta. Notendur utan
  verkefnis geta ekki séð að það sé til (404).
- Stjórnendur sjá alla notendur, verkefni, biðlara, setur,
  endurskoðunarskrána og, þegar hún er virk, beiðnaskrána, á síðunum undir
  `/admin` og, með bearer-tóka með heimildinni `admin`, um `/admin/api`.
- Hver notandi sér eigin reikning, forrit og setur á `/account` og getur
  afturkallað þau.
- Enginn sér lykilorð, leyndarmál eða tóka: þjónninn geymir aðeins tætigildi
  og sýnir nýtt leyndarmál einu sinni, við stofnun.
- Hver sem er getur lesið `/.well-known/kontroll`, `/foundation/versions`,
  `/foundation/1.0/auth` og `/healthz`; þau innihalda stillingar, aldrei
  fólk.

## Réttindi og aðgerðir

- **Eyða einstaklingi**: eyddu reikningnum undir `/admin/users` (eða með
  `opencde user delete`); setur og tókar fylgja með. Nafnið stendur áfram á
  málum og athugasemdum sem viðkomandi skrifaði, sem BCF-gögn verkefnisins;
  eyddu þeim eða breyttu um forritaskilin, eða eyddu verkefninu.
- **Flytja út**: endurskoðunarskráin er flutt út sem CSV; BCF- og skjalagögn
  eru flutt út um forritaskilin (biðlari eins og Dataspatium getur vistað
  verkefni sem BCFzip); `opencde backup` skrifar allan gagnagrunninn.
- **Öryggisatvik**: `opencde revoke --all` lýkur öllum setum og tókum; skiptu
  um lykilorð gagnagrunnsins og leynilykilinn á eftir
  ([controls.md](controls.md)).
- **Lágmarka**: láttu beiðnaskrána vera óvirka nema þú sért að villuleita
  biðlara, haltu `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` óvirkri nema þú þurfir
  hana, og birtu ekki gagnagrunnsgáttina ([deploy/bolt.md](../deploy/bolt.md)).

## Í Dataspatium

Forritið geymir vistfang þjónsins, biðlaraauðkennið sem það skráði, tóka
notandans fyrir setuna og skrá yfir köll sín (með request-id) í vafranum; það
geymir aldrei lykilorðið. Hvað af þessu fer úr vafranum, og hvernig það er
hreinsað, er á [eigin síðu Dataspatium um persónuupplýsingar](https://github.com/marwiss/Dataspatium/blob/main/docs/is/sakerhet.md).
