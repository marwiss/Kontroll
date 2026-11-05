# Ógnarlíkan

Staða: nær yfir áfanga 0–11. Hver áfangi bætir við eignunum, ógnunum og
vörnunum sem hann innleiðir, `controls.md` varpar hverri vörn á próf, og
`asvs-checklist.md` skráir sjálfsmatið gegn OWASP ASVS stigi 2.

## Eignir

| Eign | Hvar | Hvers vegna skiptir máli |
|---|---|---|
| Innskráningarupplýsingar notenda (Argon2id-tætigildi) | grafið `User` | Yfirtaka reiknings gefur aðgang að hverju verkefni þess notanda |
| OAuth2-biðlaraleyndarmál, kóðar, aðgangs- og endurnýjunartókar (SHA-256-tætigildi) | grafið `Client`, `AuthorizationCode`, `AccessToken`, `RefreshToken` | Að gefa sig út fyrir að vera notendur eða biðlarar |
| Verkefnisgögn: mál, athugasemdir, viewpoint, skyndimyndir, lýsigögn skjala | graf + geymsla | Trúnaðarupplýsingar um byggingar frá mörgum stofnunum |
| Skjöl (IFC-líkön og aðrar skrár) | geymslubakendi | Stórt, trúnaðarbundið, mögulega illkynja inntak í þáttara |
| Endurskoðunarskrá | grafið `AuditEvent` | Sönnunargögn eftir atvik |
| Stillingar og leyndarmál | `.env`, Docker secrets | Full málamiðlun ef þau leka |

## Gerendur

Nafnlaus netnotandi; auðkenndur notandi annars verkefnis; auðkenndur notandi
sama verkefnis með lægra hlutverk; skráður OAuth2-biðlari (eða einhver sem
hefur leyndarmál hans); stjórnandi; hýsingaraðilinn og hver sem getur lesið
atvikaskrár eða öryggisafrit; illviljaður skjalahöfundur.

## Trúnaðarmörk

Internet → Caddy (TLS) → API → grafgagnagrunnur og geymsla, allt á
einkaneti. Vafrinn (innskráning, samþykki, skjalaval, stjórnun) er aðskilin
mörk frá API-biðlurum sem nota Bearer-tóka.

## Ógnir og varnir (STRIDE, vex með hverjum áfanga)

| Ógn | Dæmi | Vörn | Áfangi |
|---|---|---|---|
| Upplýsingaleki um villusvör | Staflarakningar, endurómað inntak, innri auðkenni | Eitt villumeginmál `{"message"}`; sannprófunarvillur nefna svið, aldrei gildi; 5xx skráð aðeins með request-id | 0 |
| Upplýsingaleki um atvikaskrár | Tókar eða lykilorð í skrárlínum | Hulningarvinnsla á hverjum skráratburði; engin meginmál beiðna eða svara skráð | 0 |
| Spilling með of stórum eða vansköpuðum meginmálum | Minnisþurrð | Stærðarmörk meginmáls fyrir þáttun (413); streymi með bætatalningu fyrir upphöl | 0, 5 |
| Clickjacking, MIME-þefun, referrer-lekar | Síður rammaðar inn af árásaraðila; `code` lekið í Referer | CSP `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer` á hverju svari | 0 |
| Fölsun request-id | Skrárinnspýting um `X-Request-ID` | Aðeins `[A-Za-z0-9._-]{1,128}` samþykkt; annars búið til nýtt | 0 |
| Réttindaaukning með stillingamistökum | http í framleiðslu, tómt lykilorð gagnagrunns | Stillingarnar neita að ræsa | 0 |
| Aðfangakeðja | Málamiðlað ósjálfstæði eða action | `uv.lock`, pip-audit, Dependabot, actions fest með SHA, zizmor | 0 |
| Fölsun notenda og biðlara, endurspilun, mix-up, CSRF á samþykki | | Aðeins PKCE S256, nákvæm redirect_uri, `state`, `iss`, einnota kóðar, tættir tókar, skipti með afturköllun fjölskyldu, CSRF-tókar | 2 |
| Brotin heimild á hlutastigi | Lesa mál annars verkefnis um guid | Hver fyrirspurn hefst í notandahnútnum og fer um MEMBER_OF; 404 fyrir framandi hluti | 3 |
| Innspýting um OData | `$filter` smíðað til að breyta Cypher | Þáttari → AST → hvítlisti → stikar | 1, 3 |
| Geymt innihald dulbúið sem mynd | HTML eða skrifta hlaðið upp sem skyndimynd og veitt til baka | Magic bytes þurfa að passa við uppgefna gerð; myndir veittar sem `image/*` með `nosniff`; stærðarþak fyrir afkóðun | 4 |
| Upphlaðnar skrár birtar af vafra | Geymt XSS um niðurhal skjals | Skjöl og snippets eru alltaf `application/octet-stream`-viðhengi með hreinsuðum, RFC 8187-kóðuðum heitum; aldrei birt | 4, 5 |
| Stærðarmörk meginmáls sniðgengin | Chunked transfer án `Content-Length`; tvíundarleið notuð fyrir JSON-flóð | Bæti talin þegar þau berast; aðeins tvíundarleiðirnar eru undanþegnar og þær telja sjálfar gegn `max_upload_bytes` | 4 |
| Illkynja skjöl | Zip-sprengjur, path traversal, misnotkun þáttara | Auðkenni búin til af þjóni, stærðarmörk, afmörkuð útpökkun, þáttun í sandkassa-vinnuferli | 5, 9 |
| Lekinn Documents API-tengill | `upload_ui_url` eða `select_documents_url` sést í atvikaskrá, ferilskrá eða yfir öxlina | 256-bita tóki geymdur tættur, 10 mínútna gildi, eitt ferli, og síðan krefst auk þess vafrasetu sem sami notandi; URL á API-hlið nota opinbert auðkenni auk bearer-tókans | 5 |
| Misnotkun callback | Þjónninn fenginn til að sækja URL árásaraðila (SSRF), opin áframsending um callback | Þjónninn sækir aldrei callback; aðeins http(s)-URL samþykkt og vafranum áframsent með URL-kóðuðum stikum; callback hefur eigin gildistíma | 5 |
| Ófullgerð eða of stór upphöl | Hlutar stærri en tilkynnt, summur sem ganga ekki upp, yfirgefnir hlutar sem fylla diskinn | Nákvæm bilathugun á hvern hluta, stærð sannreynd við samsetningu, SHA-256 skráð, hlutar og setur renna út og eru hreinsuð með skrám sínum | 5 |
| Árásir á vafrasetu | Festing, CSRF, þjófnaður, réttindaaukning | Slembin tætt vefkaka búin til við innskráningu, `HttpOnly`, `SameSite=Strict`, `Secure` yfir https, aðgerðaleysis- og heildargildistími, undirritaðir eyðublaðstókar auk `Sec-Fetch-Site`/`Origin`-athugana, hlutverksathuganir á hverri síðu | 5, 6 |
| Aukning til stjórnanda | Meðlimur nær `/admin`; stolin stjórnandaseta notuð til endurstillinga eða skipta á leyndarmáli; stjórnandi lokaður úti | Stjórnandahlutverk athugað á hverri stjórnunarleið (annars HTML 404); hættulegar aðgerðir krefjast eigin lykilorðs stjórnandans aftur; stjórnendur geta ekki gert sjálfa sig óvirka, lækkað eða eytt; hver aðgerð endurskoðuð | 6 |
| Leyndarmál berskjölduð um viðmótið | Biðlaraleyndarmál eða mynduð lykilorð læsileg síðar | Sýnd einu sinni við stofnun eða skipti, geymd tætt; stillingasíðan hylur stillingaleyndarmál | 6 |
| Málamiðlun um uppsetninguna | Gagnagrunnur aðgengilegur af internetinu; leyndarmál bökuð inn í myndina; gámur með forréttindi; falsað `X-Forwarded-For` | Gagnagrunnur aðeins á einkaneti compose; leyndarmál úr `.env` eða Docker secrets búin til af `opencde init`; ekki-root, skrifvarinn gámur með afnumdum capabilities; áframsendum hausum aðeins treyst frá `OPENCDE_TRUSTED_PROXIES`; myndin skönnuð með SBOM við hverja útgáfu | 8 |
| Öryggisafrit sem leki eða tap | Safnskrá læsileg öðrum; endurheimt yfir lifandi gögn | Útflutningur á forritastigi í öryggisafritsgeymslu rekstraraðilans (dulkóðun í hvíld er rekstraraðilans); `opencde restore` stoppar við gagnagrunn sem er ekki tómur nema þvingað; manifest skráir skemaútgáfuna | 8 |
| Fjandsamleg IFC-skrá | Hrun þáttara, minnisþurrð, frysting, einingaflóð | Umbreyting í sérstöku vinnuferli með tíma-, minnis- og einingamörkum; bilun skráð á `IfcModel`-hnútinn og þjónninn óáreittur; merkimiðar og venslaheiti sannreynd áður en þau ná Cypher | 9 |
| Kóði þriðja aðila á síðu þjónsins | Málamiðlað CDN sem veitir Swagger UI keyrir skriftu í uppruna þjónsins | Gagnvirka API-skjölunin er óvirk í framleiðslu nema kveikt sé á henni; hún hefur eigin Content-Security-Policy sem telur upp CDN; hver önnur síða hleður aðeins auðlindum frá sama uppruna; CORS gildir aðeins um API-slóðirnar svo síður séu aldrei læsilegar cross-origin | 11 |
| Úrelt grunnmynd | Lagfæranlegir veikleikar í dreifingunni eða í meðfylgjandi söfnum pip | Keyrsluþrepið beitir öryggisuppfærslum dreifingarinnar og fjarlægir pip; Trivy fellir útgáfuna og næturskönnunina við lagfæranlega HIGH- eða CRITICAL-fundi | 8, 11 |
| Sjálfskráðir opinberir biðlarar | Hver sem er skráir biðlara með sannfærandi heiti og lokkar notendur til samþykkis | Skráning er óvirk sjálfgefið og tíðnitakmörkuð; samþykkissíðan nefnir biðlarann og hýsilinn sem hann áframsendir á; opinberir biðlarar þurfa PKCE og nákvæm redirect-URI eins og hver biðlari; stjórnendur geta gert biðlara óvirka eða eytt þeim í `/admin` | 11 |
| Beiðnaskráin sem geymsla persónuupplýsinga eða leyndarmála | Fyrirspurnarstrengir með nöfnum, tókar í hausum, meginmál með málatextum | Óvirk sjálfgefið; færslur geyma slóðina án fyrirspurnarstrengs, enga hausa og engin meginmál; varðveisla afmörkuð með `request_log_retention_hours`; lesaðgangur aðeins fyrir stjórnendur, á síðunni með setu og á `/admin/api/requests` með bearer-tóka sem ber sérstaklega umbeðna heimildina `admin` | 11 |
| Graffyrirspurnarendapunkturinn sem leið framhjá gagnalíkaninu | Cypher stjórnanda les tætigildi innskráningarupplýsinga, skrifar, breytir skemanu eða hertekur gagnagrunninn | Óvirkt sjálfgefið (`OPENCDE_GRAPH_QUERY_ENABLED`); aðeins stjórnendur með sérstaklega umbeðna heimildina `admin`; lesfærsla auk höfnunar á skrifandi setningarliðum og hverri stefju annarri en skemastefjunum (textinn athugaður með strengi, athugasemdir og heiti í bakstrikum fjarlægð, svo Memgraph, sem framfylgir ekki leshamnum, sé líka þakið); vernduðum eiginleikum hafnað í setningunni og stikunum, fjarlægðir úr hverju svari, Argon2-tætigildi hulin; raða- og tímamörk; hvert kall endurskoðað með setningunni, aldrei stikunum | 11 |
