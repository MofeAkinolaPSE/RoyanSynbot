# RoyanHealth go-live walkthrough

Gets the latest RoyanHealth (code **and** data) from the laptop onto Royan's server, reachable at
**`https://royanhospitalaiapp.online:9443`** with a padlock. Tick each box as you go.

Everything the app needs travels in **one database dump**: patients, visits, bills, Roy Books, users and roles,
settings, prices, patient signatures. The only thing outside the database is the settings file `deploy\.env`,
because it holds the password the app needs to open the database in the first place.

**Order:**

| When | Steps |
|---|---|
| Now (while the new Hope dump is on its way) | 3 (code on the server), 5–8 (domain, firewall, router, certificate) |
| After the Hope refresh | 1 (refresh Hope), 2 (make the dump), 4 (swap the server's database), 9 (before the doors open) |

---

## The values

| Item | Value |
|---|---|
| Address staff type | **`https://royanhospitalaiapp.online:9443`** |
| Domain | `royanhospitalaiapp.online` |
| Public IP (hospital line) | `102.223.1.15`: **shared with Placeware**, which keeps ports 80 and 443 |
| Public port for RoyanHealth | **`9443`** (8443 is taken). The router sends it to the server's 443. |
| Server | `172.16.0.26` (on the MikroTik's network: one router between it and the internet) |
| App folder on the server | `<APP_FOLDER>` = where the repo is cloned on the server (e.g. `C:\Royan\RoyanSynbot`) |
| Run every command from | `<APP_FOLDER>\deploy` |
| Ports on the server | nginx `443` (HTTPS) and `80` (only redirects; not opened on the router). Database `127.0.0.1:5433`, Redis `6379`, GlitchTip `8090` stay on the server only. |
| Certificate | Let's Encrypt, proven through the domain's DNS (port 80 belongs to Placeware), issued by `deploy\issue-cert-dns.ps1`, renewed automatically by the `royan_certbot` container |
| Database | `synbot_health` in container `royan_db` (user `postgres` unless `.env` says otherwise) |

Still to collect:

| What | From whom |
|---|---|
| A shared IT email for certificate expiry warnings (`<EMAIL>`) | Royan IT |
| MikroTik login | Royan IT / the consultant |
| Login to the registrar where `royanhospitalaiapp.online` was bought (it shows Namecheap's parking page today) | you |
| The newest Hope dumps (`db_drmnigeria-<date>.sql.gz`, `hope_master_nigeria-<date>.sql.gz`) and, if Finance has it, the 2025 Sage export | Royan |

---

## Step 1: Bring Hope up to date (after the new dump arrives, on the laptop)

The laptop's Hope data comes from the **25 Jan 2026** dumps; Royan has kept working in Hope since.

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

2. Put the newest two Hope dumps in `data-assimilation\Docs\NEw Dump\` and delete the Jan 2026 ones there.
3. If Finance has the **2025 Sage export** (receipts), add it: it clears the ₦222.4M "pre-go-live HMO balance to
   reconcile" on the executive overview.
4. The refresh is run together: incremental Hope load, then the HMO billing lines and Sage receipts. The exact
   commands are confirmed on the real files first (dry run, then counts checked).

- [ ] Hope data refreshed and checked on the laptop

## Step 2: Make the database dump (on the laptop)

After the last change you want to carry over. Windows PowerShell, in `<repo>\deploy`:

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

Put the laptop's `.env` in `<APP_FOLDER>\deploy\` (replace the old one), open it in Notepad and check:

| Line | Must be |
|---|---|
| `DEV_TOKEN_ENABLED` | `0` |
| `CORS_ALLOW_ORIGINS` | `https://royanhospitalaiapp.online:9443,https://localhost` |
| `ADMIN_PASSWORD` | a strong password only Royan IT keeps |

```powershell
docker compose build
docker compose up -d
docker compose ps
```

The first build takes several minutes. `docker compose ps` must show `royan_nginx` with `0.0.0.0:443->443`.
Open `https://localhost` on the server: the login page appears (a certificate warning is expected until Step 8).

- [ ] Code pulled, `.env` in place and checked, app running on the server

## Step 4: Replace the server's database with the dump (after Step 2)

In `<APP_FOLDER>\deploy` on the server. The first two lines keep a copy of what the server had, just in case.

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

The restore takes about 5 minutes. Then run the counts line from Step 2 on the server: it must print **exactly**
what you noted on the laptop. If it differs, don't go live: restore again.

- [ ] Server counts match the laptop; sign-in works

## Step 5: Put the domain's DNS on Cloudflare and point it at the hospital

The certificate is proven through DNS, and Cloudflare's free DNS lets the server renew it by itself every 60 days.
Traffic does **not** go through Cloudflare: the record is "DNS only".

1. Create a free account at `dash.cloudflare.com` → **Add a domain** → `royanhospitalaiapp.online` → Free plan.
   Cloudflare shows **two nameservers** (like `xxx.ns.cloudflare.com`).
2. At the registrar (Namecheap: Domain List → Manage → **Nameservers** → Custom DNS): replace the nameservers with
   Cloudflare's two. Save. Cloudflare emails you when the domain is **Active** (minutes to a few hours).
3. In Cloudflare → the domain → **DNS → Records → Add record**: Type `A`, Name `@`, IPv4 `102.223.1.15`,
   Proxy status **DNS only** (grey cloud, not orange). Delete any other `A`/`CNAME` record for `@`.
4. In Cloudflare → **My Profile → API Tokens → Create Token → "Edit zone DNS"** template → Zone resources:
   Include · Specific zone · `royanhospitalaiapp.online` → Create. Copy the token (shown once).
5. On the server: copy `deploy\certbot-secrets\cloudflare.ini.example` to `deploy\certbot-secrets\cloudflare.ini`,
   open it in Notepad and paste the token in place of `PASTE-THE-TOKEN-HERE`. (This file is never committed.)

Check on any PC: `nslookup royanhospitalaiapp.online 8.8.8.8` must answer `102.223.1.15`.

- [ ] Cloudflare shows the domain Active; `nslookup` returns `102.223.1.15`; token saved on the server

## Step 6: Open the server's firewall

On the server, **PowerShell as administrator**:

```powershell
New-NetFirewallRule -DisplayName "RoyanHealth HTTPS 443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

- [ ] Firewall allows 443

## Step 7: Router (MikroTik)

**First, don't lock yourself out:** on an office PC open the MikroTik's address (`http://172.16.0.1`, or ask Royan
IT). If it doesn't load, stop and do this step with Royan IT. **Don't edit or delete Placeware's rules.**

1. **IP → Firewall → NAT.** Check that no rule already uses **Dst. Port `9443`** with Dst. Address `102.223.1.15`
   (or no Dst. Address). If one does, pick another free port (e.g. `9444` or `10443`) and use it wherever this
   walkthrough says 9443, including `CORS_ALLOW_ORIGINS` in Step 3.
2. **Add New** (the internet → RoyanHealth). Leave everything else empty; don't tick the small boxes next to the
   fields (they mean "NOT"):

   | Field | Value |
   |---|---|
   | Chain | `dstnat` |
   | Dst. Address | `102.223.1.15` |
   | Protocol | `6 (tcp)` |
   | Dst. Port | `9443` |
   | Action | `dst-nat` |
   | To Addresses | `172.16.0.26` |
   | To Ports | `443` |
   | Comment | `royan https` |

3. **Add New** again (so staff **inside** the hospital can use the same address; without it the address only works
   from outside):

   | Field | Value |
   |---|---|
   | Chain | `srcnat` |
   | Src. Address | the hospital network the server is on, as shown in **IP → Addresses** (e.g. `172.16.0.0/16`) |
   | Dst. Address | `172.16.0.26` |
   | Protocol | `6 (tcp)` |
   | Dst. Port | `443` |
   | Action | `masquerade` |
   | Comment | `royan hairpin` |

   Drag it **above** any other `srcnat` rule in the list.
4. **IP → DHCP Server → Leases**: find `172.16.0.26` and click **Make Static**, so the server keeps its address.

- [ ] Both rules saved; port 9443 confirmed free; server address made static

## Step 8: Test, then get the certificate

1. On a phone **on mobile data**, open `https://royanhospitalaiapp.online:9443`. A certificate warning appears;
   tap Advanced → Proceed → the **RoyanHealth login** appears. Then try it on an office PC on hospital Wi-Fi too.
   - Placeware opens instead: the rule's port is wrong (Step 7.2 must be `9443` → `443` on `172.16.0.26`).
   - Nothing loads from outside: recheck Step 7.2 and Step 6; on the server `docker compose ps`.
   - Works from the phone but not inside the hospital: Step 7.3 is missing or below another `srcnat` rule.
2. On the server, in `<APP_FOLDER>\deploy`:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\issue-cert-dns.ps1 -Email <EMAIL> -Domain royanhospitalaiapp.online
   ```

   Four steps, each ending in a green **OK**, then "Done": a practice run with Let's Encrypt's test servers, the real
   certificate, installed, nginx reloaded.
3. Close all browser windows, open `https://royanhospitalaiapp.online:9443`: padlock, no warning. Phone too.

Renewal is automatic: `royan_certbot` checks twice a day (through the same Cloudflare token) and nginx picks up a
renewed certificate within 6 hours. Keep `cloudflare.ini` on the server.

- [ ] Padlock on the computer and the phone

## Step 9: Before the doors open

- [ ] Docker Desktop → Settings → General → **Start Docker Desktop when you sign in**; the server never sleeps and
      signs in after a power cut (or is on a UPS). Restart it once and check the app comes back.
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
| `issue-cert-dns.ps1`: "No certbot-secrets\cloudflare.ini" or "still the placeholder" | Step 5.4–5.5. |
| `issue-cert-dns.ps1` step 2: "The DNS check failed" | Cloudflare must show the domain **Active** (nameservers changed at the registrar), and the token must be the "Edit zone DNS" type for this domain. |
| "too many failed authorizations" | Let's Encrypt limits retries: wait an hour, fix the cause, try again. |
| Padlock still missing after "Done" | Close every browser window (they remember the old certificate), or try a private window. |
| Port 443 "already in use" when starting the app | Another program holds it (IIS, Skype, another web server). Admin PowerShell: `netstat -ano \| findstr ":443 "`, find the process ID in Task Manager → Details, stop it. |
| Restore prints warnings about extensions | Harmless; what counts is that the Step 2 counts match. |

## Never

- Change or delete Placeware's router rules.
- Delete the Docker volume `deploy_certbot_conf` (the certificate and the Let's Encrypt account) or `deploy\certbot-secrets\cloudflare.ini`.
- Turn on Cloudflare's orange-cloud proxy for this record (Cloudflare doesn't relay port 9443).
- Run `issue-cert-dns.ps1` on the laptop.
- Keep entering patients on the laptop after Step 2: from Step 4 the **server** is the hospital's system.
