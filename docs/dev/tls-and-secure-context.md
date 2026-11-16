# TLS and secure contexts

Some browser features only exist on a **secure context**: HTTPS with a
certificate the browser trusts, or `localhost` / `127.0.0.1`. The app's
Settings → General → **Connection** card reports which capabilities the current
origin has.

## What needs HTTPS

| Capability | Needs a secure context | Works on plain HTTP |
|---|---|---|
| PWA install (`beforeinstallprompt`, manifest) | yes | no |
| Share target (Android share sheet into the app) | yes, and the PWA must be installed | no |
| Microphone recording (`getUserMedia` / `MediaRecorder`) | yes | no |
| Media Session / lock-screen audio controls | yes | no |
| Service worker / offline shell | yes | no |
| Camera **file** picker (`<input capture="environment">`) | no | yes |
| Uploads, notes, reading, highlights, search | no | yes |

A self-signed certificate the device has not trusted still counts as insecure
for service workers and media capture. Use a locally trusted CA (`mkcert`, or a
self-hosted CA installed on the phone) for LAN testing, or a real certificate
for anything internet-facing.

## Option 1 — the bundled TLS stack

`docker/nginx-TLS.conf` is a TLS-terminating variant of the web proxy:

1. Mount it over `nginx.conf` and publish `443:443` (the commented volumes in
   `docker/docker-compose.standalone.yml`).
2. Put `fullchain.pem` / `privkey.pem` in `docker/certs/`. The port-80 server
   answers certbot's HTTP-01 webroot challenge and redirects everything else.
3. Replace `SERVER_NAME` with your domain.
4. Declare the public scheme so the cookie `Secure` flag derives itself:
   `SA_PUBLIC_URL=https://<your-host>` (or `SA_TLS=1` when TLS terminates
   on another proxy). Plain-HTTP loopback/VPN deployments stay without it
   and logins keep working.
5. Open the app on `https://<your-host>` and check Settings → General →
   Connection: **Secure connection** and the four capability chips should be
   green (Install/Share may still depend on the browser).

HSTS is sent by both nginx and the backend; don't enable HSTS on a host you
also need to reach over plain HTTP.

## Option 2 — Caddy in front

Caddy obtains and renews certificates automatically:

```caddyfile
study.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Keep the backend bound to loopback, set `SA_PUBLIC_URL=https://<host>` (or
`SA_TLS=1`) so the cookie `Secure` flag derives itself, and use the
same origin for `/api` and `/ws`.

## Option 3 — localhost or a LAN with a trusted local CA

- `http://localhost:8000` is a secure context in every modern browser; no
  certificate is needed for development.
- For a phone on the LAN, `http://192.168.x.x:8000` is **not** secure. Use
  `mkcert` to issue a certificate for the LAN hostname/IP, install the local CA
  on the phone, serve HTTPS, and use `https://<host>:<port>`.
- If you only need photo uploads from a phone, plain HTTP is enough — the
  camera **file** picker works, and captures queue through the offline journal.
  Install, share target and voice recording stay unavailable until HTTPS.

## Verifying

- Browser devtools: `window.isSecureContext` is `true`.
- Settings → General → **Connection** shows the live capability report.
- The capture inbox's offline queue works on any origin; it is not a
  secure-context feature.
- Desktop (pywebview) does not use browser HTTPS; the card shows **Desktop
  app** and the browser-only capabilities are not applicable.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Install button missing | not HTTPS/localhost, or the browser does not fire `beforeinstallprompt` |
| Share target missing | PWA not installed, or the manifest has no `share_target` |
| Microphone button disabled | insecure origin or no `getUserMedia` permission |
| `window.isSecureContext` false on `https://…` | the certificate is not trusted by the device |
| Cookies lost after enabling TLS | cookies sent without `Secure` over HTTPS: declare `SA_PUBLIC_URL=https://…` / `SA_TLS=1` — or an HTTP redirect loop |
