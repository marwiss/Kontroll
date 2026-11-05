# Självhostade plattformar (Coolify, Dokploy, Portainer)

De här plattformarna läser en compose-fil, ger den en domän med automatisk TLS
och erbjuder ett webbgränssnitt för loggar, omstarter och uppdateringar. De är
ett bekvämt sätt att köra servern när du redan använder en av dem.

## Compose-fil

Använd `compose.yaml` tillsammans med `compose.prod.yaml` **utan tjänsten
`proxy`**: plattformens egen proxy (Traefik i Coolify och Dokploy) terminerar
TLS. Enklast är en liten överlagringsfil bredvid dem:

```yaml
# compose.paas.yaml
services:
  proxy:
    profiles: ["disabled"]
  api:
    labels:
      # Dokploy / Coolify läser dessa för att dirigera domänen till containern.
      traefik.enable: "true"
      traefik.http.services.opencde.loadbalancer.server.port: "8000"
```

och driftsätt `compose.yaml compose.prod.yaml compose.paas.yaml` som en stack.

## Miljö

Sätt variablerna från `.env.example` i plattformens miljöredigerare. Minimum
för produktion:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://cde.example.org
OPENCDE_SECRET_KEY=<48 slumpmässiga tecken>
OPENCDE_GRAPH_PASSWORD=<24 slumpmässiga tecken>
OPENCDE_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]
```

`OPENCDE_DOMAIN` behövs bara av Caddy och kan utelämnas.

## Att tänka på

- Håll plattformen själv uppdaterad: Coolify publicerade till exempel
  rättningar för allvarliga sårbarheter i januari 2026. Plattformens
  administrationsgränssnitt ska inte gå att nå från det öppna internet.
- Databasvolymen och lagringsvolymen är datat; ta med dem i plattformens
  säkerhetskopiering, och behåll även volymen för den nattliga tjänsten
  `backup`.
- Första administratören: öppna en konsol på tjänsten `api` och kör
  `opencde user create admin --admin`.
