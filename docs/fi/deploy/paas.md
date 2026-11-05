# Itse ylläpidetyt alustat (Coolify, Dokploy, Portainer)

Nämä alustat lukevat compose-tiedoston, antavat sille verkkotunnuksen
automaattisella TLS:llä ja tarjoavat web-käyttöliittymän lokeille,
uudelleenkäynnistyksille ja päivityksille. Ne ovat mukava tapa ajaa
palvelinta, kun käytät jo jotakin niistä.

## Compose-tiedosto

Käytä `compose.yaml`-tiedostoa yhdessä `compose.prod.yaml`-tiedoston kanssa
**ilman `proxy`-palvelua**: alustan oma välityspalvelin (Traefik Coolifyssa
ja Dokployssa) päättää TLS:n. Yksinkertaisinta on pieni ylikirjoitustiedosto
niiden rinnalla:

```yaml
# compose.paas.yaml
services:
  proxy:
    profiles: ["disabled"]
  api:
    labels:
      # Dokploy / Coolify lukevat nämä reitittäessään verkkotunnuksen konttiin.
      traefik.enable: "true"
      traefik.http.services.opencde.loadbalancer.server.port: "8000"
```

ja ota käyttöön `compose.yaml compose.prod.yaml compose.paas.yaml` yhtenä
pinona.

## Ympäristö

Aseta `.env.example`-tiedoston muuttujat alustan ympäristöeditorissa.
Vähimmäisvaatimus tuotannolle:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://cde.example.org
OPENCDE_SECRET_KEY=<48 satunnaista merkkiä>
OPENCDE_GRAPH_PASSWORD=<24 satunnaista merkkiä>
OPENCDE_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]
```

`OPENCDE_DOMAIN`-muuttujaa tarvitsee vain Caddy, ja sen voi jättää pois.

## Huomioita

- Pidä itse alusta päivitettynä: esimerkiksi Coolify julkaisi korjauksia
  vakaviin haavoittuvuuksiin tammikuussa 2026. Alustan hallintakäyttöliittymän
  ei pitäisi olla tavoitettavissa avoimesta internetistä.
- Tietokannan taltio ja tallennustilan taltio ovat data; sisällytä ne alustan
  varmuuskopiointiin ja säilytä myös öisen `backup`-palvelun taltio.
- Ensimmäinen järjestelmänvalvoja: avaa konsoli `api`-palveluun ja aja
  `opencde user create admin --admin`.
