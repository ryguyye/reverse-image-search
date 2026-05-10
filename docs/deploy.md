# Deploying selfwatch

The recurring-scans feature needs the app to be reachable from the public internet so search providers (SerpAPI's Google Lens / Yandex) can fetch your uploaded images. The simplest way to do that is **Cloudflare Tunnel** — a daemon you run alongside the app that connects out to Cloudflare and gets a public hostname. No port-forwarding, no firewall config, free TLS.

This guide covers two flows:

1. **Quick** (TryCloudflare): no account, ephemeral URL. Good for testing in 30 seconds.
2. **Named tunnel**: stable URL on your own domain. Recommended for ongoing use.

## Prerequisites

- The app running locally: `make install && make dev` (defaults to port 8000)
- `cloudflared` installed:
  - macOS: `brew install cloudflared`
  - Linux/Windows: <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>

## 1. Quick tunnel (TryCloudflare)

```bash
make tunnel              # equivalent to: cloudflared tunnel --url http://localhost:8000
```

`cloudflared` prints a URL like `https://wandering-orange-fox-1234.trycloudflare.com`. Use that as `PUBLIC_BASE_URL`:

```bash
echo "PUBLIC_BASE_URL=https://wandering-orange-fox-1234.trycloudflare.com" >> .env
# restart the app so the new env var is picked up
```

Caveats:
- The URL changes every time you restart the tunnel.
- TryCloudflare has rate limits and is not for production traffic.
- Anyone with the URL can hit your app — there's no auth in selfwatch by default. See [Adding auth](#adding-auth) below.

## 2. Named tunnel (stable URL on your own domain)

You'll need a domain managed in Cloudflare's free plan.

```bash
# One-time setup
cloudflared tunnel login                                            # opens browser
cloudflared tunnel create selfwatch                                 # creates the tunnel + creds file
cloudflared tunnel route dns selfwatch selfwatch.yourdomain.com     # adds the CNAME

# Copy and edit the example config
mkdir -p ~/.cloudflared
cp cloudflared/config.example.yml ~/.cloudflared/config.yml
$EDITOR ~/.cloudflared/config.yml      # replace tunnel UUID and hostname

# Run the tunnel (foreground)
cloudflared tunnel run selfwatch
```

Once it's up, set `PUBLIC_BASE_URL`:

```
PUBLIC_BASE_URL=https://selfwatch.yourdomain.com
```

To run cloudflared as a service:
- macOS: `sudo cloudflared service install` then `sudo launchctl start com.cloudflare.cloudflared`
- Linux (systemd): `sudo cloudflared service install` creates `/etc/systemd/system/cloudflared.service`

## Running the app for tunnel use

Use `make run` (not `make dev`) when serving real traffic:

```bash
make run
```

That invokes uvicorn with `--proxy-headers --forwarded-allow-ips="*"` so request URLs are reconstructed from Cloudflare's `X-Forwarded-Proto`/`X-Forwarded-For` headers. Without this, FastAPI may build `http://` URLs even though the public-facing hostname is `https://`.

When cloudflared connects to localhost on the same host, the proxy-headers path is fine. If you ever put selfwatch behind a different reverse proxy (e.g. nginx → uvicorn) you may want to restrict `--forwarded-allow-ips` to that proxy's IP.

## Adding auth

selfwatch has no built-in auth. With Cloudflare Tunnel you get **Cloudflare Access** for free on the named-tunnel path:

1. In the Cloudflare dashboard, go to **Zero Trust → Access → Applications**.
2. Add a self-hosted application for `selfwatch.yourdomain.com`.
3. Configure a policy (e.g. "emails ending in @yourcompany.com" or a one-time PIN to a specific email).

This puts an SSO-style login in front of the app without changing any code.

## Persistent uploads + database

`./uploads` and `./selfwatch.db` are in `.gitignore` and live next to the app. If you redeploy with `make clean` you lose them. For ongoing use:

- Run the app from a stable working directory (not a temp checkout).
- Back up `./selfwatch.db` and `./uploads` periodically — they hold your watches and previously-seen match URLs.

## Troubleshooting

- **`request.url_for(...)` returns http:// instead of https://** — you're running with plain `make dev` rather than `make run`. The dev target doesn't set `--proxy-headers`. Use `make run` when traffic comes through Cloudflare.
- **Webhook never fires** — check that the watch's `webhook_url` is correct and reachable. The webhook only fires when the run produces *new* matches; if the same URLs were already seen on a previous run, no webhook is sent. `POST /api/watches/{id}/run` returns the `webhook_status` field.
- **Provider returns 4xx fetching the image** — your `PUBLIC_BASE_URL` isn't reachable from the internet, or the upload was deleted. Tail cloudflared logs (`cloudflared tunnel info`) to confirm requests for `/uploads/<name>` are arriving.
- **Cloudflare 524 timeout** — bump `connectTimeout` in `~/.cloudflared/config.yml` (see `cloudflared/config.example.yml`).
