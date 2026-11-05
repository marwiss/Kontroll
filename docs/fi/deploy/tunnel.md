# Julkinen https-osoite asiakastestejä varten (tunneli)

BCF- ja Documents-asiakkaat vaativat yleensä https:n ja tavoitettavan
isännän. Tunneli antaa paikalliselle pinollesi julkisen osoitteen avaamatta
portteja tai vuokraamatta palvelinta.

## Cloudflare Tunnel (ilmainen, pysyvä isäntänimi omassa verkkotunnuksessa)

1. Luo tunneli kohdassa Cloudflare Zero Trust → Networks → Tunnels, lisää
   julkinen isäntänimi (esimerkiksi `cde.example.org`) palvelulla
   `http://api:8000` ja kopioi tunnelin token.
2. `.env`-tiedostoon:

   ```
   OPENCDE_ENVIRONMENT=production
   OPENCDE_PUBLIC_URL=https://cde.example.org
   TUNNEL_TOKEN=<token>
   ```

   Tuotantotila vaatii https-osoitteen, tietokannan salasanan ja salaisen
   avaimen; `opencde init --public-url https://cde.example.org` kirjoittaa ne.
3. Käynnistä:

   ```sh
   docker compose -f compose.yaml -f compose.tunnel.yaml up -d
   docker compose -f compose.yaml -f compose.tunnel.yaml exec api opencde seed
   ```

Tunnelin reuna päättää TLS:n; palvelin luottaa compose-verkkoon
välityspalvelimenaan (`OPENCDE_TRUSTED_PROXIES`) ja näkee asiakasosoitteen
`X-Forwarded-For`-otsakkeessa. Rekisteröi testiasiakkaasi redirect-URI
hallinnassa.

## Tailscale Funnel

Kun koneella on Tailscale, `tailscale serve --bg 8000` ja sen jälkeen
`tailscale funnel 443 on` julkaisevat kehityspinon osoitteessa
`https://<kone>.<tailnet>.ts.net`. Aseta `OPENCDE_PUBLIC_URL` tuohon
osoitteeseen ja `OPENCDE_ENVIRONMENT=production` (tai pidä `development` ja
hyväksy, että palvelin uskoo olevansa http:ssä: linkit toimivat silti, koska
niihin käytetään julkista osoitetta).

## ngrok (nopea, vaihtuva isäntänimi)

`ngrok http 8000` tulostaa https-osoitteen; laita se
`OPENCDE_PUBLIC_URL`-muuttujaan ja käynnistä API uudelleen. Sopii
kertatestiin, ei mihinkään, joka tallentaa osoitteen.

Selainasiakas, kuten [Dataspatium](https://github.com/marwiss/Dataspatium),
voi käyttää tunnelin osoitetta palvelinosoitteenaan, kun sovellus itse
tarjoillaan osoitteesta `http://127.0.0.1:<portti>`; sovelluksen redirect-URI
pysyy loopback-osoitteena, ja CORS sallii oletuksena kaikki alkuperät.

## Jälkeenpäin

Tunneloitu kehityspino on tuotannon kaltainen palvelin demosalasanoilla.
Pysäytä se (`docker compose ... down`) tai kierrätä seedatut salasanat, kun
testi on ohi.
