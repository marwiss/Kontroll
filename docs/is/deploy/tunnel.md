# Opinbert https-vistfang fyrir biðlaraprófanir (gangur)

BCF- og Documents-biðlarar krefjast venjulega https og hýsils sem næst í.
Gangur (tunnel) gefur staðbundna staflanum þínum opinbert vistfang án þess að
opna gáttir eða leigja þjón.

## Cloudflare Tunnel (frítt, stöðugt hýsilheiti á eigin léni)

1. Búðu til gang í Cloudflare Zero Trust → Networks → Tunnels, bættu við
   opinberu hýsilheiti (til dæmis `cde.example.org`) með þjónustunni
   `http://api:8000` og afritaðu tóka gangsins.
2. Í `.env`:

   ```
   OPENCDE_ENVIRONMENT=production
   OPENCDE_PUBLIC_URL=https://cde.example.org
   TUNNEL_TOKEN=<tókinn>
   ```

   Rekstrarhamurinn krefst https-vistfangsins, lykilorðs gagnagrunnsins og
   leynilykils; `opencde init --public-url https://cde.example.org` skrifar
   þau.
3. Ræstu:

   ```sh
   docker compose -f compose.yaml -f compose.tunnel.yaml up -d
   docker compose -f compose.yaml -f compose.tunnel.yaml exec api opencde seed
   ```

Jaðar gangsins lýkur TLS; þjónninn treystir compose-netinu sem milliþjóni
sínum (`OPENCDE_TRUSTED_PROXIES`) og sér vistfang biðlarans í
`X-Forwarded-For`. Skráðu redirect-URI prófunarbiðlarans í stjórnuninni.

## Tailscale Funnel

Með Tailscale á tölvunni birta `tailscale serve --bg 8000` og síðan
`tailscale funnel 443 on` þróunarstaflann á
`https://<tölva>.<tailnet>.ts.net`. Settu `OPENCDE_PUBLIC_URL` á það vistfang
og `OPENCDE_ENVIRONMENT=production` (eða haltu `development` og sættu þig við
að þjónninn telji sig vera á http: tenglar virka samt því að opinbera
vistfangið er notað í þá).

## ngrok (fljótlegt, breytilegt hýsilheiti)

`ngrok http 8000` prentar https-vistfang; settu það í `OPENCDE_PUBLIC_URL` og
endurræstu API-ið. Fínt fyrir eina prófun, ekki fyrir neitt sem geymir
vistfangið.

Vafrabiðlari eins og [Dataspatium](https://github.com/marwiss/Dataspatium)
getur notað vistfang gangsins sem þjónsvistfang sitt meðan forritið sjálft er
þjónað frá `http://127.0.0.1:<gátt>`; redirect-URI forritsins er áfram
loopback-vistfang, og CORS leyfir sjálfgefið allan uppruna.

## Eftir á

Þróunarstafli um gang er rekstrarlíkur þjónn með sýnilykilorðum. Stöðvaðu
hann (`docker compose ... down`) eða skiptu um sáðu lykilorðin þegar
prófuninni er lokið.
