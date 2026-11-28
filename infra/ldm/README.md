# LDM server: public HTTPS for madis-api (v2 Phase 9)

Goal: Railway's `worker` downloads the 5-minute HFMETAR files from your LDM server over HTTPS.
`madis-api` keeps listening only on `127.0.0.1:8000`; **Caddy** in front of it gets a free HTTPS
certificate for `ldm.getedgefront.com` and forwards only `/health` and `/api/v1/hfmetar/*`.

Why not an IP allowlist: Railway's Hobby plan has no static outbound IP addresses, so the server
can't tell Railway apart from anyone else by IP. Protection is: HTTPS only (the token never
travels in clear text), a long random Bearer token checked by `madis-api`, GET/HEAD only, every
other path 404, small request limits and an access log. **Rate limiting:** the standard Caddy
package has no rate-limit feature (it needs a custom-built Caddy with a third-party module,
`github.com/mholt/caddy-ratelimit`, which you'd then have to rebuild for every update). We don't
use it: without the token nothing but `/health` answers, and `/health` is cheap.

Server facts: host `ldm`, IP `143.110.213.207`, Ubuntu, you log in as `root`.

---

## 0. Log in to the server first (every time)

All commands in steps 2–6 run **on the server**, not on your Windows PC. In Windows PowerShell:

```
ssh root@143.110.213.207
```

Wait until the prompt shows **`root@ldm:~#`**. Only then paste the commands. If the prompt shows
`PS C:\...>` you are still on Windows: don't paste server commands there.

## 1. DNS at Namecheap (in the browser)

1. Namecheap → Domain List → `getedgefront.com` → **Manage** → **Advanced DNS**.
2. **Add New Record** → Type **A Record**, Host **`ldm`**, Value **`143.110.213.207`**, TTL
   **Automatic** → save (green tick).
3. Check it (on the server, after ~5–30 minutes):

   ```
   getent ahosts ldm.getedgefront.com | head -1
   ```

   It must print `143.110.213.207`. Don't continue until it does (Caddy needs it for the
   certificate).

## 2. Firewall (keep SSH open!)

Look first:

```
ufw status verbose
```

- If it says **`Status: inactive`**: allow SSH **before** turning it on, then the web ports:

  ```
  ufw allow OpenSSH
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
  ufw status verbose
  ```

- If it says **`Status: active`**: just add the web ports (SSH is already allowed, or you
  couldn't be logged in):

  ```
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw status verbose
  ```

The list must show `22/tcp` (or `OpenSSH`), `80/tcp` and `443/tcp` as `ALLOW`. Port 8000 must
**not** be listed: `madis-api` stays private. Check it listens on localhost only:

```
ss -ltnp | grep ':8000'
```

It should show `127.0.0.1:8000`. If it shows `0.0.0.0:8000`, stop and tell me.

If your server is a DigitalOcean droplet with a **Cloud Firewall** attached (DigitalOcean →
Networking → Firewalls), allow inbound TCP 80 and 443 there too.

## 3. Install Caddy (official package)

```
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy
```

Caddy is now running (service `caddy`) with a placeholder config. Put ours in place, keeping a
copy of the original:

```
cp -n /etc/caddy/Caddyfile /etc/caddy/Caddyfile.orig
mkdir -p /var/log/caddy && chown caddy:caddy /var/log/caddy
curl -fsSL https://raw.githubusercontent.com/maishu423-debug/getedgefront/v2-phase-9-hfmetar/infra/ldm/Caddyfile -o /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
```

`validate` must end with **`Valid configuration`**. Then apply it and watch Caddy get the
certificate:

```
systemctl reload caddy
systemctl status caddy --no-pager
journalctl -u caddy --no-pager -n 30
```

Look for `certificate obtained successfully` for `ldm.getedgefront.com`. (It needs step 1's DNS
and ports 80/443 open.)

## 4. Check the API token (and rotate it if it's weak)

Show only the token's **length** (not the token):

```
grep -E '^MADIS_API_TOKEN=' /opt/madis-api/.env | cut -d= -f2- | tr -d "\"' \r\n" | wc -c
```

- **44 or more**: fine (that's 32 random bytes in base64). Skip to step 5.
- **Less than 44**, or a word you chose yourself: rotate it.

  ```
  cp -p /opt/madis-api/.env /opt/madis-api/.env.bak-$(date +%F-%H%M)
  NEW="$(openssl rand -base64 32 | tr -d '\n')"
  sed -i "s|^MADIS_API_TOKEN=.*|MADIS_API_TOKEN=${NEW}|" /opt/madis-api/.env
  systemctl restart madis-api
  systemctl status madis-api --no-pager
  echo "$NEW"
  ```

  Copy the printed token **once** into Railway (`worker` → Variables → `MADIS_API_TOKEN`) and into
  your local repo `.env` as `MADIS_API_TOKEN=...` (so I can run the real-file analysis). Never paste
  it into chat. Then clear your screen: `clear`.

## 5. Verify from outside

On the server (this goes out through DNS, HTTPS and Caddy like Railway does):

```
TOKEN="$(grep -E '^MADIS_API_TOKEN=' /opt/madis-api/.env | cut -d= -f2- | tr -d "\"' \r\n")"
curl -s -o /dev/null -w 'health: %{http_code}\n' https://ldm.getedgefront.com/health
curl -s -o /dev/null -w 'files with token: %{http_code}\n' -H "Authorization: Bearer ${TOKEN}" https://ldm.getedgefront.com/api/v1/hfmetar/files
curl -s -o /dev/null -w 'files without token: %{http_code}\n' https://ldm.getedgefront.com/api/v1/hfmetar/files
curl -s -o /dev/null -w 'anything else: %{http_code}\n' https://ldm.getedgefront.com/docs
unset TOKEN
```

Expected: `health: 200`, `files with token: 200`, `files without token: 401` (or `403`),
`anything else: 404`. Tell me when you see that; I'll check from here too.

## 6. Railway `worker` variables

Railway → `worker` → Variables (then Deploy):

| Variable | Value |
|---|---|
| `LDM_API_BASE_URL` | `https://ldm.getedgefront.com` |
| `MADIS_API_TOKEN` | the token (step 4) 🔒 |
| `HF_INGEST_ENABLED` | `false` until the Phase 9 PR is merged and deployed, then `true` |

Optional (defaults shown): `HF_POLL_SECONDS=60`, `HF_MAX_FILES_PER_RUN=6`, `HF_BACKFILL_HOURS=24`,
`HF_STALE_MINUTES=15` (worker alert). The worker refuses to start the job without a token or with an `http://`
URL (logged as `hfmetar job not started`); the other jobs keep running.

What to look for in the worker logs after switching it on: one `hfmetar ingest` line per minute
(`files_processed`, `count_new`, `count_revised`, `duration_ms`, `process_peak_rss_mb`). Alerts
are log lines starting `hfmetar alert:` (`ldm_health`, `no_new_readings`), repeated hourly while
they last, and `hfmetar alert resolved:` when they clear.

## Rollback (if anything goes wrong)

- **Caddy misbehaves:** put the original config back, or stop Caddy entirely. `madis-api` itself
  is untouched by Caddy.

  ```
  cp /etc/caddy/Caddyfile.orig /etc/caddy/Caddyfile && systemctl reload caddy
  # or stop it completely:
  systemctl stop caddy && systemctl disable caddy
  ```

- **Firewall:** remove the web ports (SSH stays allowed):

  ```
  ufw delete allow 80/tcp
  ufw delete allow 443/tcp
  ```

  If you enabled ufw in step 2 and want it off again: `ufw disable`.
- **Token:** restore the backup and restart:

  ```
  ls /opt/madis-api/.env.bak-*
  cp -p /opt/madis-api/.env.bak-<the date> /opt/madis-api/.env && systemctl restart madis-api
  ```

- **DNS:** delete the `ldm` A record at Namecheap.
- **Remove Caddy:** `apt remove caddy` (the certificate and settings stay in `/var/lib/caddy`
  until you delete that folder).

Useful later: `tail -n 20 /var/log/caddy/ldm-access.log` shows the last requests (the token is
logged as `REDACTED`).
