# Rekstur á eigin þjóni (Docker Compose + Caddy)

Einn Linux-hýsill (2 vCPU og 4 GB vinnsluminni er ríflegt til að byrja með),
Docker með compose-viðbótinni, DNS-heiti sem vísar á hann, gáttir 80 og 443
opnar. Caddy sækir og endurnýjar TLS-skírteinið; API-ið, gagnagrunnurinn og
öryggisafritunarverkið keyra á lokuðu neti.

## 1. Undirbúa

```sh
git clone https://github.com/marwiss/Kontroll.git /opt/kontroll
cd /opt/kontroll
uv run opencde init --public-url https://cde.example.org
```

Án `--public-url` spyr `opencde init` um gildin og prentar síðan skipanirnar sem koma næst, einnig fyrir stjórnandann og fyrsta biðlarann.

`init` skrifar `.env` með `OPENCDE_ENVIRONMENT=production`, leynilykli,
lykilorði gagnagrunnsins og `OPENCDE_DOMAIN`. Bættu við
`OPENCDE_ACME_EMAIL=you@example.org` svo að Let's Encrypt geti náð í þig vegna
skírteina. Haltu `.env` leyndri (git hunsar hana); hún er eina skráin með
leyndarmálum.

Án uv á þjóninum: afritaðu `.env.example` í `.env` og fylltu gildin inn
handvirkt (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
fyrir leynilykilinn).

## 2. Ræsa

```sh
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde doctor
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde user create admin --admin
```

Síðasta skipunin prentar lykilorð stjórnandans einu sinni. Skráðu þig inn á
`https://cde.example.org/signin`, opnaðu `/admin` og búðu til þau verkefni,
notendur og OAuth2-biðlara sem forritin þín þurfa.

## 3. Rekstur

| Verk | Skipun |
|---|---|
| Uppfæra í nýjasta image | `docker compose -f compose.yaml -f compose.prod.yaml pull && docker compose -f compose.yaml -f compose.prod.yaml up -d` |
| Festa útgáfu | `OPENCDE_IMAGE_TAG=2.7.0` í `.env` (merkin fylgja GitHub-útgáfunum) |
| Atvikaskrár | `docker compose -f compose.yaml -f compose.prod.yaml logs -f api` (JSON-línur) |
| Heilsa | `https://cde.example.org/readyz`; síðan Stillingar í stjórnuninni |
| Öryggisafrit | á hverri nóttu í geymsluna `backups` af þjónustunni `backup`; sjá [backup.md](backup.md) |
| Afturkalla aðgang í öryggisatviki | `docker compose ... exec api opencde revoke --all` (eða `--user`, `--client`) |

## 4. Gátlisti fyrir herðingu

- Gagnagrunnurinn er ekki birtur; aðeins Caddy hlustar á hýslinum. Að birta
  Bolt-gáttina fyrir grafbiðlara er meðvitað skref með eigin yfirlagi og TLS,
  sjá [bolt.md](bolt.md); opin gátt gefur þeim sem hefur lykilorðið fullan
  aðgang að gagnagrunninum.
- API-gámurinn er skrifvarinn, keyrir ekki sem root og án capabilities;
  geymslan er nefnd gagnageymsla.
- `OPENCDE_TRUSTED_PROXIES` nær yfir compose-netið svo að vistfang biðlarans í
  endurskoðunarskránni sé hið rétta; láttu það vera nema þú breytir netinu.
- Stjórnunina má takmarka við innri vistföng. Bættu þessu við vefsvæðisblokkina í `Caddyfile` og aðlagaðu vistföngin; `/admin/api` fylgir með, svo að stjórnun Dataspatium virkar aðeins frá þeim vistföngum:

  ```caddyfile
  @admin_outside {
  	path /admin /admin/*
  	not remote_ip 10.0.0.0/8 192.168.0.0/16
  }
  respond @admin_outside 404
  ```

- API-ið leyfir 600 beiðnir á mínútu á hvert vistfang. Allir á bak við sama vistfang deila þeim, svo að hækkaðu mörkin fyrir stóra skrifstofu, til dæmis `OPENCDE_RATE_LIMIT_API=3000/minute`. Hið sama gildir um 10 innskráningartilraunir á mínútu, `OPENCDE_RATE_LIMIT_SIGN_IN=60/minute`; biðin á hvert notandanafn stöðvar ágiskanir hvort sem er.
- Haltu `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=false` nema þú þurfir
  sjálfsafgreidda biðlaraskráningu (Foundation API 2.2.3); skráðu biðlara í
  `/admin`.
- Skiptu um leynilykilinn og lykilorð gagnagrunnsins samkvæmt þinni stefnu
  (`docs/is/security/controls.md`), endurræstu og skráðu þig inn aftur.
- Keyrðu `testssl.sh https://cde.example.org` og athugaðu
  <https://observatory.mozilla.org> eftir fyrstu ræsingu.
- Eldveggur: leyfðu aðeins 22 (frá þínum vistföngum), 80 og 443.
