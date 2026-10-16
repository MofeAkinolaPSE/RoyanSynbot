# RoyanHealth go-live walkthrough

Gets the latest RoyanHealth (code **and** data) from the laptop onto Royan's server, reachable at
**`https://royanhospitalaiapp.online:9443`** with a padlock. Tick each box as you go.

Everything the app needs travels in **one database dump**: patients, visits, bills, Roy Books, users and roles,
settings, prices, patient signatures. The only thing outside the database is the settings file `deploy\.env`,
because it holds the password the app needs to open the database in the first place.

**Order:**

| When | Steps |
|---|---|
| Now (while the new Hope dump is on its way) | 3 (code on the server), 5–8 (domain, firewall, router + Placeware add-on, certificate) |
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
| Ports on the server | nginx `443` (HTTPS, reached from the internet through 9443) and `80` (only Let's Encrypt's check, passed on by Placeware's server). Database `127.0.0.1:5433`, Redis `6379`, GlitchTip `8090` stay on the server only. |
| Certificate | Let's Encrypt, the same method as Placeware. Its check always arrives on port 80, which goes to Placeware's server; a small add-on there (`royan-acme.conf`) passes checks for the Royan domain to the Royan server. Issued once by `deploy\issue-cert.ps1`, renewed automatically by `royan_certbot`. Each company keeps its own certificate on its own server. |
| Database | `synbot_health`, user `postgres`, in container `royan_db` (laptop and server alike) |

Still to collect:

| What | From whom |
|---|---|
| A shared IT email for certificate expiry warnings (`<EMAIL>`) | Royan IT |
| MikroTik login | Royan IT / the consultant |
| Namecheap login (where `royanhospitalaiapp.online` is registered) | you |
| Access to the Placeware server (`192.168.0.112`) for the one-time add-on in Step 7 | you |
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

Write down the last line (the counts). The dump is about 270 MB.

**Copy it to the server** (the server is Windows): in your Remote Desktop session to `172.16.0.26`, copy
`royan-golive.dump` on the laptop (Ctrl+C) and paste it on the server's Desktop (Ctrl+V); Remote Desktop carries
files through the clipboard. A USB stick works too. It holds patient data: never email it; wipe the USB after.
(The settings file is not copied: the server keeps its own, see Step 3.)

**Dump made 14 Oct 2026, 14:39** (current Hope data from the 25 Jan 2026 dumps, test activity cleared), on the
laptop's Desktop as `royan-golive.dump`. Its counts:

```
patients=60929  bills=259067  users=4  books_diff=0.00
```

The same dump was restored into a fresh database on the laptop as a rehearsal of Step 4: no errors, same counts.

- [ ] Dump copied to the server; counts noted: ____________________

## Step 3: Update the code on the server

**Where:** the server, Windows PowerShell, Docker Desktop showing **Engine running**.

```powershell
cd "<APP_FOLDER>"
git pull
cd deploy
```

**The settings file.** Keep the server's own `deploy\.env` (database login `postgres`, database `synbot_health`,
the same as the laptop). Open it in Notepad and change only these:

| Line | Set to | Why |
|---|---|---|
| `CORS_ALLOW_ORIGINS` | `https://royanhospitalaiapp.online:9443,https://localhost` | the address staff use |
| `INTERNAL_SIGNAL_KEY` (only if empty) | a long random value, e.g. from `python -c "import secrets; print(secrets.token_hex(32))"` | the app's error watcher drops its alerts while this is empty |
| `GLITCHTIP_SECRET_KEY` (only if empty) | another long random value | the error-tracking service needs it to start |

Leave everything else as it is (`DEV_TOKEN_ENABLED=0` is already right).

```powershell
docker compose build
docker compose up -d
docker compose ps
```

The first build takes several minutes. `docker compose ps` must show `royan_nginx` with `0.0.0.0:443->443`.
Open `https://localhost` on the server: the login page appears (a certificate warning is expected until Step 8).

- [ ] Code pulled, `.env` in place and checked, app running on the server

## Step 4: Replace the server's database with the dump (after Step 2)

In `<APP_FOLDER>\deploy` on the server, Windows PowerShell.

The server's database is `synbot_health`, user `postgres` (from its `.env`). First confirm it is there:

```powershell
docker exec royan_db psql -U postgres -d postgres -c "\l"
```

The list must include `synbot_health`. Then the swap; the first two lines keep a copy of what the server had:

```powershell
docker exec royan_db pg_dump -U postgres -d synbot_health -Fc -f /tmp/server-before.dump
docker cp royan_db:/tmp/server-before.dump "$HOME\Desktop\server-before.dump"
docker compose stop backend backup
docker cp "$HOME\Desktop\royan-golive.dump" royan_db:/tmp/royan.dump
docker exec royan_db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS synbot_health WITH (FORCE)"
docker exec royan_db psql -U postgres -d postgres -c "CREATE DATABASE synbot_health"
docker exec royan_db pg_restore -U postgres -d synbot_health --no-owner /tmp/royan.dump
docker compose up -d
```

The restore takes about 5 minutes and should print no `error:` lines. Then the counts on the server:

```powershell
docker exec royan_db psql -U postgres -d synbot_health -Atc "SELECT 'patients=' || (SELECT count(*) FROM royan_patients) || '  bills=' || (SELECT count(*) FROM royan_billing) || '  users=' || (SELECT count(*) FROM royan_users) || '  books_diff=' || (SELECT COALESCE(sum(debit)-sum(credit),0) FROM fin_journal_lines)"
```

It must print exactly `patients=60929  bills=259067  users=4  books_diff=0.00`. If it differs, don't go live:
restore again.

- [ ] Server counts match the laptop; sign-in works

## Step 5: Point the domain at the hospital (Namecheap)

Namecheap → **Domain List** → **Manage** next to `royanhospitalaiapp.online` → **Advanced DNS**:

1. Delete the existing parking records for host `@` and `www` (the `CNAME`/`URL Redirect` records Namecheap adds).
2. **Add New Record**: Type `A Record`, Host `@`, Value `102.223.1.15`, TTL Automatic. Click the green ✔.

Check on any PC: `nslookup royanhospitalaiapp.online 8.8.8.8` must answer `102.223.1.15` (minutes to a few hours).

- [ ] `nslookup` returns `102.223.1.15`

## Step 6: Open the Royan server's firewall

On the Royan server (`172.16.0.26`), **PowerShell as administrator**:

```powershell
New-NetFirewallRule -DisplayName "RoyanHealth HTTPS 443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
New-NetFirewallRule -DisplayName "RoyanHealth HTTP 80 (certificate checks)" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
```

- [ ] Firewall allows 443 and 80

## Step 7: Router (MikroTik) and the Placeware add-on

**First, don't lock yourself out:** on an office PC open `http://172.16.0.1` (the MikroTik). If it doesn't load,
stop and do this step with the consultant. **Don't edit or delete Placeware's existing rules.**

1. **IP → Firewall → NAT.** Check that no rule already uses **Dst. Port `9443`**. If one does, pick another free
   port (e.g. `9444`) and use it wherever this walkthrough says 9443, including `CORS_ALLOW_ORIGINS` in Step 3 and
   the `:9443` in the Placeware add-on (Step 7.5). The server itself always listens on 443.
2. **Add New** (the internet → RoyanHealth). Leave every other field empty; don't tick the small boxes next to the
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

3. **Add New** again, so staff **inside** the hospital can use the same address (without it the address only
   works from outside):

   | Field | Value |
   |---|---|
   | Chain | `srcnat` |
   | Src. Address | the hospital network the server is on, as shown in **IP → Addresses** (e.g. `172.16.0.0/16`) |
   | Dst. Address | `172.16.0.26` |
   | Protocol | `6 (tcp)` |
   | Dst. Port | `443` |
   | Action | `masquerade` |
   | Comment | `royan hairpin` |

   Drag it **above** any other `srcnat` rule.
4. **IP → DHCP Server → Leases**: find `172.16.0.26` → **Make Static**, so the server keeps its address.
5. **The Placeware add-on** (once; passes Let's Encrypt's checks for the Royan domain to the Royan server; Placeware's
   own traffic is untouched). It is committed in the Placeware repo (`backend\nginx-extra\royan-acme.conf` and one
   mount line in `backend\docker-compose.yml`, commit "Pass Let's Encrypt checks for royanhospitalaiapp.online…").
   - On the laptop, in the Placeware folder: `git push origin main`.
   - On the **Placeware server**, PowerShell in the Placeware folder (`...\Chat Assisant  placeware x1`):
     ```powershell
     git pull
     cd backend
     docker compose up -d frontend
     docker compose exec frontend nginx -t
     ```
     The last line must say `syntax is ok` / `test is successful`. No rebuild is needed (the add-on is mounted, not
     built in); Placeware is back within seconds.

- [ ] Both MikroTik rules saved; 9443 confirmed free; server address static; Placeware add-on in place

## Step 8: Test, then get the certificate

1. On a phone **on mobile data**: open `https://royanhospitalaiapp.online:9443`. A certificate warning appears; tap
   Advanced → Proceed → the **RoyanHealth login** appears. Then try it on an office PC on hospital Wi-Fi.
   - Placeware opens instead: Step 7.2 must be `9443` → `172.16.0.26` : `443`.
   - Nothing loads from outside: recheck Step 7.2 and Step 6; on the server `docker compose ps`.
   - Works from the phone but not inside: Step 7.3 is missing or below another `srcnat` rule.
2. Still on mobile data, open `http://royanhospitalaiapp.online`: it must jump to
   `https://royanhospitalaiapp.online:9443` (that proves port 80 reaches the Placeware add-on).
3. On the Royan server, in `<APP_FOLDER>\deploy`:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\issue-cert.ps1 -Email <EMAIL> -Domain royanhospitalaiapp.online
   ```

   Five steps, each ending in a green **OK**, then "Done": start nginx and certbot, check the local check folder, a
   practice run with Let's Encrypt's test servers, the real certificate, install and reload.
4. Close all browser windows, open `https://royanhospitalaiapp.online:9443`: padlock, no warning. Phone too.

Renewal is automatic: `royan_certbot` checks twice a day (through the same port-80 path) and nginx picks up a
renewed certificate within 6 hours.

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
| `issue-cert.ps1` step 2: "did not return the check file" | On the Royan server: `docker compose up -d --force-recreate nginx`, run it again. |
| `issue-cert.ps1` step 3: "could not reach this server on port 80" | Port 80 isn't getting through: Step 5 (A record), Step 7.5 (Placeware add-on in place and `docker compose up -d frontend` done), Step 6 (Royan firewall allows 80). From mobile data, `http://royanhospitalaiapp.online/.well-known/acme-challenge/cert-check` should show `cert-ok` while the script waits. |
| "too many failed authorizations" | Let's Encrypt limits retries: wait an hour, fix the cause, try again. |
| Padlock still missing after "Done" | Close every browser window (they remember the old certificate), or try a private window. |
| Port 443 or 80 "already in use" when starting the app | Another program holds it (IIS, Skype, another web server). Admin PowerShell: `netstat -ano \| findstr ":443 "`, find the process ID in Task Manager → Details, stop it. |
| `pg_restore` prints any `error:` | The rehearsal restored with none, so stop: send me the message. The server's old database copy (`server-before.dump`) is on the Desktop. |
| `docker compose` says `failed to read ... .env: line N: unexpected character` | A line in `.env` is not `NAME=value` or a `#` comment: fix that line (Step 3's corrected `.env.example` has none). |
| The app can't sign in / backend keeps restarting after Step 3 | The database login in `.env` differs from the one the server's database was created with: put back `POSTGRES_USER` and `POSTGRES_PASSWORD` from `.env.old`, then `docker compose up -d`. |

## Never

- Change or delete Placeware's router rules, or remove the `royan-acme.conf` add-on from Placeware's server (Royan's renewals use it).
- Delete the Docker volume `deploy_certbot_conf` (the certificate and the Let's Encrypt account).
- Run `issue-cert.ps1` on the laptop.
- Keep entering patients on the laptop after Step 2: from Step 4 the **server** is the hospital's system.
