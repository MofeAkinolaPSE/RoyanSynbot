# RoyanHealth go-live walkthrough

Gets the latest RoyanHealth (code **and** data) from the laptop onto Royan's server, reachable at
`https://<DOMAIN>` with a padlock. Do the steps in order and tick each box.

Everything the app needs travels in **one database dump**: patients, visits, bills, Roy Books, users and roles,
settings, prices, patient signatures. The only thing that is not in the database is the settings file
`deploy\.env`, because it holds the password the app needs to open the database in the first place.

---

## What you need to collect (only these)

| What | From whom | Write it here |
|---|---|---|
| `<DOMAIN>`: the address staff will type (e.g. `app.royanhospital.com`) | buy it / Royan's domain admin | |
| `<PUBLIC_IP>`: the hospital's fixed internet IP that will carry the app | Royan's ISP | |
| `<SERVER_IP>`: the server's address on the hospital network (fixed / reserved) | Royan IT, or `ipconfig` on the server | |
| Router login (address, user, password) | Royan IT | |
| `<EMAIL>`: a shared IT mailbox for certificate expiry warnings | Royan IT | |
| The newest Hope dumps (`db_drmnigeria-<date>.sql.gz` and `hope_master_nigeria-<date>.sql.gz`) | Royan (the Hope system) | |

## Already known (nothing to look up)

| Item | Value |
|---|---|
| App folder on the server | `<APP_FOLDER>` = where the repo is cloned (e.g. `C:\Royan\RoyanSynbot`) |
| Folder you run every command from | `<APP_FOLDER>\deploy` |
| Public ports | **80** (HTTP, redirects to HTTPS; Let's Encrypt checks here) and **443** (HTTPS). Nothing else is opened to the internet. |
| Ports only on the server itself | database `127.0.0.1:5433`, Redis `6379`, GlitchTip `8090` |
| Web server | compose service `nginx` (container `royan_nginx`); config `deploy\nginx\nginx.conf` |
| Certificate | `/etc/nginx/ssl/cert.pem` + `key.pem`; issued by `deploy\issue-cert.ps1`; renewed automatically by `royan_certbot` |
| Database | `synbot_health` in container `royan_db` (user `postgres` unless `.env` says otherwise) |

---

## Step 1: Bring Hope up to date (before the dump)

The data on the laptop comes from Hope's **25 Jan 2026** dumps. Royan has kept working in Hope since, so:

1. **Make room first.** The refresh needs about 25 GB free (the new dump is unpacked into a ~20 GB working file).
   Windows PowerShell, in the repo folder. These are only old copies; the live database is not touched:

   ```powershell
   Remove-Item "data-assimilation\staging\hope_staging.db"          # 18.5 GB: working copy of the Jan 2026 dump; rebuilt from the new one
   Remove-Item "data-assimilation\Docs\DrM File\data1712.sql"       # 2.7 GB: old Hope export
   Remove-Item "data-assimilation\Docs\DrM File\db_drmnigeria-2023*.sql.gz"
   Remove-Item "data-assimilation\Docs\DrM File\db_drmnigeria-2024*.sql.gz"
   Remove-Item "data-assimilation\Docs\DrM File\db_drmnigeria-20260125.sql.gz"   # duplicate of the copy in NEw Dump
   Remove-Item synbot_health_prod_20260629.dump, synbot_health_ready.dump, synbot_health_ready_20260715.dump, billing_fixed.dump
   docker builder prune -f                                           # ~4.8 GB of old build steps (the next build is a little slower)
   ```

   When the new Hope dumps are in, also delete the Jan 2026 ones in `data-assimilation\Docs\NEw Dump\`.
2. Get the newest two Hope dumps from Royan and put them in `data-assimilation\Docs\NEw Dump\`.
3. If Finance has the **2025 Sage export** (receipts), get it too: it clears the ₦222.4M "pre-go-live HMO
   balance to reconcile" on the executive overview.
4. Run the refresh with me: the incremental Hope load, then the HMO billing lines and Sage receipts. The exact
   commands are confirmed on the real files first (dry run, then counts checked) because a migration is only
   repeated safely after it has been tested on the new dump.

- [ ] Hope data refreshed and checked on the laptop

## Step 2: Make the database dump (on the laptop)

Do this after the last change you want to carry over. **Where:** the laptop, Windows PowerShell, in
`<repo>\deploy`.

```powershell
docker exec royan_db pg_dump -U postgres -d synbot_health -Fc -f /tmp/royan.dump
docker cp royan_db:/tmp/royan.dump "$HOME\Desktop\royan-golive.dump"
docker exec royan_db psql -U postgres -d synbot_health -Atc "SELECT 'patients=' || (SELECT count(*) FROM royan_patients) || '  bills=' || (SELECT count(*) FROM royan_billing) || '  users=' || (SELECT count(*) FROM royan_users) || '  books_diff=' || (SELECT COALESCE(sum(debit)-sum(credit),0) FROM fin_journal_lines)"
```

Write down the last line (the counts). Copy `royan-golive.dump` (about 1 GB) and the laptop's `deploy\.env` to the
server by USB or a private share. They hold patient data and passwords: never email them, wipe the USB after.

- [ ] Dump made; counts noted: ____________________

## Step 3: Update the code on the server

**Where:** the server, Windows PowerShell, Docker Desktop showing **Engine running**.

```powershell
cd "<APP_FOLDER>"
git pull
cd deploy
```

Put the laptop's `.env` in `<APP_FOLDER>\deploy\` (replace the old one). Then open it in Notepad and check:

| Line | Must be |
|---|---|
| `DEV_TOKEN_ENABLED` | `0` |
| `CORS_ALLOW_ORIGINS` | `https://<DOMAIN>,https://localhost` |
| `ADMIN_PASSWORD` | a strong password only Royan IT keeps |

```powershell
docker compose build
docker compose up -d
```

The first build takes several minutes.

- [ ] Code pulled, `.env` in place and checked, app built and started

## Step 4: Replace the server's database with the dump

Still in `<APP_FOLDER>\deploy` on the server. The first two lines keep a copy of what the server had, just in case.

```powershell
docker exec royan_db pg_dump -U postgres -d synbot_health -Fc -f /tmp/server-before.dump
docker cp royan_db:/tmp/server-before.dump "$HOME\Desktop\server-before.dump"
docker compose stop backend backup
docker cp "<path to>\royan-golive.dump" royan_db:/tmp/royan.dump
docker exec royan_db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS synbot_health WITH (FORCE)"
docker exec royan_db psql -U postgres -d postgres -c "CREATE DATABASE synbot_health"
docker exec royan_db pg_restore -U postgres -d synbot_health --no-owner /tmp/royan.dump
docker compose up -d
```

The restore takes about 5 minutes. Then run the counts line from Step 2 on the server. It must print **exactly**
what you noted on the laptop. If it differs, don't go live: restore again.

Open `https://localhost` on the server and sign in (a certificate warning is expected until Step 8).

- [ ] Server counts match the laptop; sign-in works on `https://localhost`

## Step 5: Point the domain at the hospital

At the domain registrar → DNS settings for `<DOMAIN>`: add an **A record**, host `@` (or the sub-domain name,
e.g. `app`), value `<PUBLIC_IP>`. Delete any other record for the same host (e.g. a "parking page").

Check on any PC: `nslookup <DOMAIN> 8.8.8.8` must answer `<PUBLIC_IP>` (can take up to a few hours).

- [ ] `nslookup` returns `<PUBLIC_IP>`

## Step 6: Open the server's firewall

On the server, **PowerShell as administrator**:

```powershell
New-NetFirewallRule -DisplayName "RoyanHealth HTTP 80"   -Direction Inbound -Protocol TCP -LocalPort 80  -Action Allow
New-NetFirewallRule -DisplayName "RoyanHealth HTTPS 443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

- [ ] Firewall allows 80 and 443

## Step 7: Forward the router to the server

Before changing anything, make sure you can still reach the router from inside the hospital: open its address
(e.g. `http://192.168.0.1`) on an office PC. If that doesn't load, stop and do this step with Royan IT.

In the router (usually **NAT / Port forwarding / Virtual server**), add two rules:

| Name | Outside port | Forward to | Inside port | Protocol |
|---|---|---|---|---|
| royan-https | 443 | `<SERVER_IP>` | 443 | TCP |
| royan-http | 80 | `<SERVER_IP>` | 80 | TCP |

On a MikroTik these are **IP → Firewall → NAT → Add New**: Chain `dstnat`, Dst. Address `<PUBLIC_IP>`,
Protocol `tcp`, Dst. Port `443` (then `80`), Action `dst-nat`, To Addresses `<SERVER_IP>`, To Ports `443` (`80`).
Don't tick the small boxes next to the fields (they mean "NOT").

Reserve `<SERVER_IP>` for the server in the router's DHCP settings, so the rules keep working.

If there are two routers in a row, the outer one forwards to the inner one's outside address, and the inner one
forwards to `<SERVER_IP>`; ask Royan IT which routers sit between the internet and the server.

- [ ] Both rules saved; server address reserved

## Step 8: Test from outside, then get the certificate

1. On a phone **on mobile data** (not hospital Wi-Fi), open `http://<DOMAIN>`. It should jump to
   `https://<DOMAIN>` and show a certificate warning; tap Advanced → Proceed → the **RoyanHealth login** appears.
   - Router login page instead: the router rules don't match (Step 7).
   - Nothing loads: check Step 6 and that `docker compose ps` shows `royan_nginx` with `0.0.0.0:80` and `0.0.0.0:443`.
2. On the server, in `<APP_FOLDER>\deploy`:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\issue-cert.ps1 -Email <EMAIL> -Domain <DOMAIN>
   ```

   Five steps, each ending in a green **OK**, then "Done". It tests with Let's Encrypt's practice servers first,
   then gets the real certificate and reloads nginx.
3. Close all browser windows, open `https://<DOMAIN>`: padlock, no warning. Check on the phone too.

Renewal is automatic: `royan_certbot` checks twice a day and nginx picks up a renewed certificate within 6 hours.
Keep port 80 open; renewals need it.

- [ ] Padlock on the computer and the phone

## Step 9: Before the doors open

- [ ] Docker Desktop → Settings → General → **Start Docker Desktop when you sign in**; the server is set to never
      sleep and to sign in after a power cut (or is on a UPS). Restart it once and check the app comes back.
- [ ] Logins created for every doctor (linked to their staff record) and every other team (front desk, nurses,
      lab, Scancare, pharmacy, cashier, HMO, stores, finance, auditor) in **User Access**.
- [ ] Medical Superintendent and Authorised Signatory named: Billing → Consultation fees → Signatories.
- [ ] The nightly backup (02:00, container `royan_backup`) is copied off the server at least weekly.
- [ ] After a day of use: if the browser console shows no "Content-Security-Policy" warnings, rename
      `Content-Security-Policy-Report-Only` to `Content-Security-Policy` in `deploy\nginx\nginx.conf` and run
      `docker compose restart nginx`.

---

## If something fails

| Problem | Fix |
|---|---|
| `issue-cert.ps1` stops at step 2 ("did not return the check file") | `docker compose up -d --force-recreate nginx`, run it again. |
| `issue-cert.ps1` stops at step 3 ("could not reach this server on port 80") | Port 80 isn't getting in: recheck Steps 5–7, test `http://<DOMAIN>` from mobile data. |
| "too many failed authorizations" | Let's Encrypt limits retries: wait an hour, fix port 80, try again. |
| Padlock still missing after "Done" | Close every browser window (they remember the old certificate), or try a private window. |
| Port 80/443 "already in use" when starting | Another program holds it (IIS, Skype, another web server). Admin PowerShell: `netstat -ano \| findstr ":80 "`, find the process ID in Task Manager → Details, stop it. |
| Restore prints warnings about extensions | Harmless; what counts is that the Step 2 counts match. |

## Never

- Delete the Docker volume `deploy_certbot_conf` (it holds the real certificate and the Let's Encrypt account).
- Run `issue-cert.ps1` on the laptop.
- Close port 80 on the router after go-live (renewals need it).
- Keep entering patients on the laptop after Step 2: from Step 4 the **server** is the hospital's system.
