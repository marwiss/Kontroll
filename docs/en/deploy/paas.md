# Self-hosted platforms (Coolify, Dokploy, Portainer)

These platforms read a compose file, give it a domain with automatic TLS and
offer a web UI for logs, restarts and updates. They are a comfortable way to run
the server when you already use one of them.

## Compose file

Use `compose.yaml` together with `compose.prod.yaml` **without the `proxy`
service**: the platform's own proxy (Traefik in Coolify and Dokploy) terminates
TLS. The simplest way is a small override file next to them:

```yaml
# compose.paas.yaml
services:
  proxy:
    profiles: ["disabled"]
  api:
    labels:
      # Dokploy / Coolify read these to route the domain to the container.
      traefik.enable: "true"
      traefik.http.services.opencde.loadbalancer.server.port: "8000"
```

and deploy `compose.yaml compose.prod.yaml compose.paas.yaml` as one stack.

## Environment

Set the variables of `.env.example` in the platform's environment editor. The
minimum for production:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://cde.example.org
OPENCDE_SECRET_KEY=<48 random characters>
OPENCDE_GRAPH_PASSWORD=<24 random characters>
OPENCDE_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]
```

`OPENCDE_DOMAIN` is only needed by Caddy and can be omitted.

## Notes

- Keep the platform itself patched: Coolify, for example, published fixes for
  serious vulnerabilities in January 2026. The platform's admin UI should not be
  reachable from the open internet.
- The database volume and the storage volume are the data; include them in the
  platform's backup, and keep the nightly `backup` service's volume as well.
- First administrator: open a console on the `api` service and run
  `opencde user create admin --admin`.
