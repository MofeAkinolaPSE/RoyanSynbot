# SynbotHealth / RoyanHealth — Deployment Walkthrough

> **Current situation:** You are connected to the client's Ubuntu/Windows server via Remote Desktop (RDP) or SSH from your dev laptop.
> Everything you do in this guide happens inside that session — on the server — unless a step explicitly says "on your dev laptop."
>
> **Plan:** Push the repo to GitHub first, then deploy the full stack on the server, restore the patient data dump, and run the PESE validation script to confirm the system is live.
>
> **Estimated time:** 1.5 – 2 hours (first-time setup). Subsequent redeploys via CI/CD take under 5 minutes.

---

## What Are We Deploying?

**SynbotHealth** — a full-stack hospital management system (HMS) running 6 Docker services:

| Service | What It Does | URL Path |
|---|---|---|
| **backend** | FastAPI REST API + AI clinical assistant | `/api/` |
| **db** | PostgreSQL 17 + pgvector (259k+ patient records) | internal only |
| **frontend** | SynbotUI — staff HMS dashboard | `/` |
| **patient_portal** | Patient-facing PWA (lab results, bills, vitals) | `/portal/` |
| **nginx** | Reverse proxy, SSL termination, rate limiting | port 80/443 |
| **backup** | Automated daily PostgreSQL dumps at 02:00 | internal only |

Once deployed:
- Staff log into `https://SERVER_IP` and access the full HMS
- Patients access `https://SERVER_IP/portal/` with MRN + phone
- Every code push from your laptop auto-redeploys via GitHub Actions

---

## Glossary

- **WSL2** — Linux environment inside Windows. Required if the server is Windows.
- **Docker** — Runs all services in isolated containers. Identical behaviour everywhere.
- **GitHub Actions** — Automates build and deploy on every `git push`.
- **Self-hosted runner** — Background service on the server that picks up CI/CD jobs.
- **PESE** — Patient Encounter Simulation Engine — our end-to-end validation script. 68 checks.
- **Data dump** — `synbot_health_ready.dump` — PostgreSQL binary export of all 259k patient records from the Hope ETL migration. This is the production dataset for the client.

---

## Progress Map

```
PART 1 (Today — App Live):
[ PREP ] → [ Push Code ] → [ Server Setup ] → [ Clone + .env ] → [ Start Stack ]
        → [ Data Dump Restore ] → [ Sequences Reset ] → [ PESE 68/68 ] → [ Watchdog ]

PART 2 (After Verified):
[ Hope Bridge ] → [ SMS/WhatsApp Termii ] -> [ Paystack Payments ] -> [ Let's Encrypt TLS ]
```

---

## RDP / SSH Tips Before You Start

- **Copy-paste into RDP:** Copy on your laptop → click inside RDP → right-click → Paste
- **File transfer via RDP:** In Remote Desktop Connection → Show Options → Local Resources → More → tick your C: drive. The server will see it as `\\tsclient\C\`
- **File transfer via SCP (SSH):** `scp yourfile.dump user@SERVER_IP:~/`
- **Open terminal on server:** VSCode → Ctrl+` — or open Ubuntu terminal from Start menu
- **PowerShell as Administrator:** Start → search PowerShell → right-click → Run as administrator

---

---

# PART 1 — Get SynbotHealth Live

---

## PREP — Before Anything Else (on your dev laptop)

---

### PREP 1 — Generate Your Secrets

Open a terminal **on your dev laptop** and run each command. Copy and save every output — you will need them in the next step.

**Database password** — choose a strong one yourself (no `@` or `$` characters):
```
Example: RoyanHMS2026!
```

**JWT Secret** — run this and copy the 128-char output:
```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

**Encryption Key (at-rest)** — run this and copy the 32-char output:
```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

Keep all three values in a safe place (notes app, secure text file). You will paste them into GitHub now.

---

### PREP 2 — Add GitHub Secrets

These are the credentials the deployment pipeline injects into the server at every deploy. They never go into the code.

1. Go to your GitHub repository in a browser
2. Click **Settings** (top tab) → left sidebar → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each row below

| Secret Name | What to put |
|---|---|
| `POSTGRES_PASSWORD` | Your database password from PREP 1 |
| `JWT_SECRET` | The 128-char hex from PREP 1 |
| `AT_REST_KEY` | The 32-char encryption key from PREP 1 |
| `ADMIN_EMAIL` | Email address you will log into the HMS with |
| `ADMIN_PASSWORD` | Strong password for the admin account |
| `DEEPSEEK_API_KEY` | Your DeepSeek API key (from platform.deepseek.com) |
| `DEEPSEEK_MODEL` | `deepseek-chat` |
| `EMAIL_FROM` | Gmail address for system notifications |
| `EMAIL_PASS` | Gmail App Password (Google Account → Security → App Passwords) |
| `TERMII_API_KEY` | Termii API key for SMS/WhatsApp (termii.com — can add later) |
| `PAYSTACK_SECRET_KEY` | Paystack secret key (dashboard.paystack.com — can add later) |
| `DEV_TOKEN_ENABLED` | `0` for production. Use `1` only during demo/testing |
| `CORS_ALLOW_ORIGINS` | `https://SERVER_IP` — replace with actual IP after Step 6 |

> You should have **13 secrets** when done. The pipeline will fail immediately if `POSTGRES_PASSWORD`, `JWT_SECRET`, or `ADMIN_EMAIL` are missing.

---

### PREP 3 — Final Code Check and Commit

On your **dev laptop**, open a terminal in the project folder:

```bash
cd C:\Users\DELL\Desktop\Moe\RoyanSynbot
```

Run the PESE one final time to confirm 68/68 locally before pushing:
```powershell
$env:PYTHONUTF8="1"; python backend/tests/e2e_pese.py --url https://localhost --dev-token
```

Confirm the output ends with:
```
ALL 68 CHECKS PASSED — DEMO READY
```

Then stage and commit everything:
```bash
git add .
git commit -m "feat: SynbotHealth v1 — full HMS + patient portal, 68/68 PESE validated"
```

> **Do NOT run `git push` yet.** Pushing triggers the deployment pipeline. The server runner must be set up first or the pipeline will fail with no runner available. You will push at Step 8.

---

---

## ON THE SERVER

> Everything from here until Step 8 happens **on the client's server** (inside RDP or SSH).

---

### Step 1 — Check What Is Already Installed

Open a terminal on the server and run these checks. Skip any step where the check passes.

**Check WSL2 (Windows servers only):**
```powershell
wsl --status
```
- Shows `Default Version: 2` → skip Step 2A
- Error or nothing → Do Step 2A

**Check Ubuntu (Windows servers only):**
```powershell
wsl -l -v
```
- Shows `Ubuntu-22.04` with `VERSION 2` → skip Step 2B
- Nothing → Do Step 2B

**Check Docker:**
```bash
docker --version
```
- Shows a version → skip Step 3
- "not recognized" or "not found" → Do Step 3

**Check Git:**
```bash
git --version
```
- Shows a version → skip git install in Step 3

---

### Step 2A — Enable WSL2 (Windows servers only — skip if already enabled)

In **PowerShell as Administrator**, use the single-command method (works on Windows 10 build 18362+):
```powershell
wsl --install
```

This enables WSL, enables Virtual Machine Platform, and queues Ubuntu 22.04 for install — all in one step. The older `dism.exe` method can fail with Error 1017 on some Windows 10 22H2 machines; use this instead.

**Restart the server:**
```powershell
Restart-Computer
```

Reconnect via RDP. Ubuntu will open automatically — create a username (e.g. `royan`) and password when prompted.

**Verify WSL2 is active:**
```powershell
wsl -l -v
```
Should show `Ubuntu` with `VERSION 2`.

---

### Step 2B — Install Ubuntu (Windows servers only — skip if already installed)

**Option A — USB/offline installer:**
```powershell
Add-AppxPackage -Path "D:\Ubuntu_2204.AppxBundle"
```

**Option B — Download directly:**
```powershell
wsl --install -d Ubuntu-22.04
```

Open Ubuntu from Start menu when complete. Create a username (e.g. `royan`) and password when prompted.

**Enable systemd** (inside the Ubuntu terminal):
```bash
sudo tee /etc/wsl.conf <<EOF
[boot]
systemd=true
EOF
```
Then in PowerShell: `wsl --shutdown` — reopen Ubuntu.

---

### Step 3 — Install Docker

**Windows (Docker Desktop):**

Download Docker Desktop from the Docker website inside the RDP session.

Run the installer → keep **"Use WSL2 based engine"** checked.

After install, connect Docker to Ubuntu:
- Docker Desktop → Settings → Resources → WSL Integration → toggle on **Ubuntu-22.04** → Apply & Restart

**Ubuntu/Linux servers (no Docker Desktop):**
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```
Close and reopen terminal.

**Verify (both paths):**
```bash
docker ps
```
Expected: empty table, no error.

---

### Step 4 — Install the GitHub Actions Runner

This is the background service that watches GitHub for new pushes and runs the deploy job on this server.

**Get your unique setup link:**
1. GitHub repo → **Settings** → **Actions** → **Runners** → **New self-hosted runner**
2. Select **Linux** and **x64** — leave this page open

**In the Ubuntu terminal on the server:**
```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
```

Copy and run the **`curl` download command** from the GitHub page, then:
```bash
tar xzf ./actions-runner-linux-x64-*.tar.gz
```

Copy and run the **`./config.sh` command** from the GitHub page (includes a one-time token):
```bash
./config.sh --url https://github.com/YOUR_ORG/YOUR_REPO --token YOUR_TOKEN
```
Press Enter for all prompts. Type `royan-server` when asked for runner name.

**Install as a permanent service:**
```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```
Look for `active (running)`.

**Confirm on GitHub:** Repo → Settings → Actions → Runners → green dot + **Idle** status = ready.

---

### Step 5 — Open Firewall Ports

**Windows (PowerShell as Administrator):**
```powershell
netsh advfirewall firewall add rule name="SynbotHealth HTTPS" dir=in action=allow protocol=TCP localport=443
netsh advfirewall firewall add rule name="SynbotHealth HTTP" dir=in action=allow protocol=TCP localport=80
```
Both should print `Ok.`

**Ubuntu/Linux:**
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

---

### Step 6 — Confirm the Server's IP

```bash
ip addr show | grep "inet " | grep -v "127.0.0.1"
```

Pick the line matching your **physical network card** (e.g. `eth0` or `ens3`) — not Docker virtual networks (`172.17.x.x`, `172.19.x.x`).

```
inet 192.168.1.50/24  ...  eth0       <- this is your server's real IP
inet 172.17.0.1/16    ...  docker0    <- ignore — Docker internal
```

Verify from your dev laptop:
```powershell
ping 192.168.1.50
```
Getting replies = correct IP.

> **Write this IP down.** This is your HMS URL: `https://192.168.1.50`
> Go back to GitHub now and update the `CORS_ALLOW_ORIGINS` secret to `https://192.168.1.50`.

---

### Step 7 — Clone the Repo and Create the .env

**Clone into the standard deploy path:**
```bash
sudo mkdir -p /opt/royan && sudo chown $USER /opt/royan
cd /opt/royan
git clone https://github.com/YOUR_ORG/YOUR_REPO.git .
```

If the repo is private, use a Personal Access Token when git asks for a password (GitHub → Settings → Developer settings → Personal access tokens → Tokens classic → check `repo` scope).

After cloning:
```bash
ls /opt/royan
```
You should see: `backend/`, `SynbotUI/`, `patient-portal/`, `deploy/`, `data-assimilation/`

**Create the .env from the template:**
```bash
cd /opt/royan/deploy
cp .env.example .env
nano .env
```

Fill in these values (use arrow keys to navigate):
```
POSTGRES_PASSWORD=         <- your DB password from PREP 1
JWT_SECRET=                <- your 128-char JWT secret
AT_REST_KEY=               <- your 32-char encryption key
ADMIN_EMAIL=               <- admin login email
ADMIN_PASSWORD=            <- admin password
DEEPSEEK_API_KEY=          <- your DeepSeek key
DEEPSEEK_MODEL=deepseek-chat
DEV_TOKEN_ENABLED=0        <- 0 for production
CORS_ALLOW_ORIGINS=https://192.168.1.50   <- your actual server IP
```

**Save:** Ctrl+O → Enter → Ctrl+X

Verify:
```bash
grep "POSTGRES_PASSWORD" .env
```
Should show your actual password, not a placeholder.

---

### Step 8 — Push Code and Build the Stack

**On your dev laptop** — this triggers the GitHub Actions pipeline:
```bash
git push origin main
```

Go to GitHub → **Actions** tab — you should see a new workflow run start within seconds.

**Back on the server**, simultaneously bring up the stack:
```bash
cd /opt/royan/deploy
docker compose up -d --build
```

- `--build` builds fresh Docker images (required on first run)
- `-d` runs everything in the background
- This takes **8–12 minutes** on first run — a lot of output is normal

Watch progress:
```bash
docker compose logs -f
```
Press Ctrl+C to stop watching. Containers keep running.

**Confirm all services are healthy:**
```bash
docker compose ps
```

Expected — all showing `Up` or `healthy`:
```
NAME                        STATUS
deploy-backend-1            Up (healthy)
deploy-db-1                 Up (healthy)
deploy-frontend-1           Up (healthy)
deploy-patient_portal-1     Up (healthy)
deploy-nginx-1              Up
```

If any show `Exit` or `Restarting`, check logs:
```bash
docker compose logs backend --tail 30
```

---

---

## DATA DUMP — Restore the Patient Database

> **What this is:** `synbot_health_ready.dump` contains the full Hope ETL data — 259,000+ patients, encounters, billing records, and clinical history imported from the client's existing DRM Hope system. Without this step, the HMS launches empty.
>
> **Do this AFTER the stack is healthy** from Step 8. The stack must be running before you restore.

---

### Step 9A — Transfer the Dump File to the Server

The dump file lives on your **dev laptop** at:
```
C:\Users\DELL\Desktop\Moe\RoyanSynbot\synbot_health_ready.dump
```

**Option A — Via RDP mapped drive (Windows server):**
1. On your dev laptop, open Remote Desktop Connection
2. Click **Show Options** → **Local Resources** → **More...**
3. Tick your **C: drive** → Connect
4. Inside RDP: open File Explorer → This PC → you will see `Local Disk (C: on YOUR-LAPTOP)`
5. Copy `synbot_health_ready.dump` from there to `C:\Users\USERNAME\` on the server
6. In the Ubuntu terminal on the server:
```bash
cp /mnt/c/Users/YOUR_USERNAME/synbot_health_ready.dump ~/
```

**Option B — Via SCP (SSH server):**

On your **dev laptop** (PowerShell or bash):
```bash
scp "C:\Users\DELL\Desktop\Moe\RoyanSynbot\synbot_health_ready.dump" user@192.168.1.50:~/
```

**Option C — Via USB drive:**
Copy the dump to a USB stick, plug into the server, then:
```bash
cp /media/USB_DRIVE_NAME/synbot_health_ready.dump ~/
```

**Verify the file arrived on the server:**
```bash
ls -lh ~/synbot_health_ready.dump
```
Should show the file size (expect 50MB–500MB depending on compression).

---

### Step 9B — Copy the Dump Into the Database Container

```bash
cd /opt/royan/deploy
docker compose cp ~/synbot_health_ready.dump db:/tmp/synbot_health_ready.dump
```

Verify it is inside the container:
```bash
docker compose exec db ls -lh /tmp/synbot_health_ready.dump
```

---

### Step 9C — Restore the Patient Data

```bash
docker compose exec db pg_restore \
  --username postgres \
  --dbname synbot_health \
  --no-owner \
  --no-acl \
  --data-only \
  --disable-triggers \
  --verbose \
  /tmp/synbot_health_ready.dump
```

- `--data-only` — skips schema creation (tables already exist from migrations)
- `--disable-triggers` — bypasses FK checks during bulk load for speed
- `--verbose` — shows each table as it loads; you will see hundreds of lines scrolling

**This takes 2–10 minutes** depending on server speed. Done when the shell prompt returns.

If you see errors like `relation "X" does not exist` — the migrations did not fully complete. Fix:
```bash
docker compose restart backend
sleep 30
docker compose exec db pg_restore --username postgres --dbname synbot_health --no-owner --no-acl --data-only --disable-triggers /tmp/synbot_health_ready.dump
```

---

### Step 9D — Reset PostgreSQL Sequences (CRITICAL — do not skip)

> **Why:** The Hope ETL inserted rows with explicit IDs (e.g. patient ID 66810 from a 259k import). PostgreSQL sequences still sit at their post-migration defaults (around 3). Without this reset, the very next new patient or bill you create will collide on the primary key and the system throws a 500 error.

Run all of these in one command:
```bash
docker compose exec db psql -U postgres -d synbot_health -c "
SELECT setval(pg_get_serial_sequence('royan_patients','id'),      (SELECT MAX(id) FROM royan_patients));
SELECT setval(pg_get_serial_sequence('royan_encounters','id'),    (SELECT MAX(id) FROM royan_encounters));
SELECT setval(pg_get_serial_sequence('royan_billing','id'),       (SELECT MAX(id) FROM royan_billing));
SELECT setval(pg_get_serial_sequence('royan_lab_orders','id'),    (SELECT MAX(id) FROM royan_lab_orders));
SELECT setval(pg_get_serial_sequence('royan_prescriptions','id'), (SELECT MAX(id) FROM royan_prescriptions));
"
```

Each line prints the new sequence value:
```
 setval
--------
 294624
 525567
 ...
```

**Verify the patient count loaded correctly:**
```bash
docker compose exec db psql -U postgres -d synbot_health -c "SELECT COUNT(*) FROM royan_patients;"
```
Expected: `259077` or similar (the total number of imported patients).

---

---

## VERIFY — Confirm the System Is Live

---

### Step 10 — Open the App in a Browser

From any browser on the network, go to:
```
https://192.168.1.50
```
(Use your actual server IP from Step 6)

**You will see a security warning** — "Your connection is not private." This is expected with a self-signed certificate.
- Chrome: Advanced → Proceed to site
- Firefox: Advanced → Accept the Risk and Continue
- Edge: Advanced → Continue to site

You do this once. The browser remembers it.

**Log in** with your `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

**Checklist — confirm each works:**
- [ ] Login page loaded
- [ ] Logged in → reached HMS Dashboard
- [ ] Queue board shows existing patients (from the dump)
- [ ] Patient search → type a name → results appear
- [ ] Patient portal: go to `https://192.168.1.50/portal/` → login screen loads

---

### Step 11 — Run PESE Validation (Final System Check)

This runs 68 automated checks against the live server — from patient registration through billing, labs, prescriptions, vitals, and all portal endpoints.

**On your dev laptop** (if the server IP is reachable from the network):
```powershell
$env:PYTHONUTF8="1"
python backend/tests/e2e_pese.py `
  --url https://192.168.1.50 `
  --admin-email YOUR_ADMIN_EMAIL `
  --admin-password YOUR_ADMIN_PASSWORD `
  --db-url "postgresql://postgres:YOUR_DB_PASSWORD@192.168.1.50:5433/synbot_health"
```

**Or on the server directly (Ubuntu terminal):**
```bash
cd /opt/royan
pip install requests psycopg2-binary 2>/dev/null
PYTHONUTF8=1 python backend/tests/e2e_pese.py \
  --url https://localhost \
  --admin-email YOUR_ADMIN_EMAIL \
  --admin-password YOUR_ADMIN_PASSWORD \
  --db-url "postgresql://postgres:YOUR_DB_PASSWORD@localhost:5433/synbot_health"
```

Expected final output:
```
══════════════════════════════════════════════════════════════
  ALL 68 CHECKS PASSED — DEMO READY
  Scenario A  (PASS):  MRN = RH16-xx     <- existing patient from dump
  Scenario B  (PASS):  MRN = RH2026xxxx  <- freshly registered patient
  Frontend    (PASS):  21/21 contract checks
  Duration:  ~5s
══════════════════════════════════════════════════════════════
```

If any checks fail, see the TROUBLESHOOTING section.

---

### Step 12 — Install the Watchdog (Auto-Recovery)

The watchdog restarts any crashed container automatically, without needing a redeploy.

```bash
sudo tee /etc/systemd/system/royan-watchdog.service <<'EOF'
[Unit]
Description=RoyanHealth Stack Watchdog
After=docker.service
[Service]
ExecStart=/bin/bash -c 'while true; do cd /opt/royan/deploy && docker compose up -d 2>&1 | grep -v "up-to-date"; sleep 60; done'
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now royan-watchdog
sudo systemctl status royan-watchdog
```

Look for `active (running)`.

---

### Step 13 — Test Auto-Redeploy (CI/CD Confirmation)

Confirms future code changes from your laptop deploy automatically to this server.

**On your dev laptop**, push any tiny change:
```bash
git commit --allow-empty -m "test: verify CI/CD auto-redeploy on client server"
git push origin main
```

1. Go to GitHub → **Actions** tab — a new job starts within seconds
2. The HMS stays **fully usable** while the deploy runs (~4–6 minutes)
3. After the job succeeds → hard-refresh the browser (Ctrl+Shift+R)

Green checkmark on GitHub Actions = CI/CD is live. Every future code fix you push will deploy automatically with zero downtime.

---

### Step 14 — Hand Over to Client

Share these access details:

```
HMS (Staff):       https://192.168.1.50
Patient Portal:    https://192.168.1.50/portal/
First visit:       Accept the security warning once (Advanced -> Proceed)

Admin credentials: [ADMIN_EMAIL] / [ADMIN_PASSWORD]
New user accounts: Log in as admin -> Settings -> Users -> Invite
Portal login:      Patient uses their MRN + registered phone number
```

---

---

# PART 2 — Integrations (After App Verified)

> Come back here once the client confirms the HMS is usable day-to-day.

**Hope Bridge (Legacy DRM sync):**
Update `HOPE_BRIDGE_URL` in `/opt/royan/deploy/.env` to point at the Windows machine running the bridge service. Restart the backend: `docker compose restart backend`

**SMS / WhatsApp (Termii):**
Add `TERMII_API_KEY` and `TERMII_SENDER_ID` to GitHub Secrets — the notification system activates automatically on the next deploy.

**Payments (Paystack):**
Add `PAYSTACK_SECRET_KEY` and `PAYSTACK_PUBLIC_KEY` to GitHub Secrets — the Pay Now button on the patient portal becomes live.

**Let's Encrypt TLS (production domain):**
```bash
cd /opt/royan/deploy
sudo bash setup-letsencrypt.sh --domain royan.yourhospital.com --email admin@yourhospital.com
```

---

---

# TROUBLESHOOTING

### Deployment Issues

| Problem | Fix |
|---|---|
| GitHub runner shows Offline | Ubuntu: `cd ~/actions-runner && sudo ./svc.sh start` |
| `docker ps` gives permission denied | `sudo usermod -aG docker $USER` — reopen terminal |
| Stack starts but backend shows `Restarting` | `docker compose logs backend --tail 40` — usually a missing env var |
| `duplicate key value violates unique constraint` | Re-run Step 9D (sequence reset) |
| Portal login fails (MRN + phone) | Phone in DB must match exactly. Check: `docker compose exec db psql -U postgres -d synbot_health -c "SELECT mrn, phone FROM royan_patients WHERE mrn='MRN_HERE';"` |
| PESE fails on `register_patient 500` | Sequences not reset — run Step 9D again |
| PESE fails on `create_bill 500` | Billing sequence not reset — run Step 9D again |
| App unreachable from other machines | Re-run the firewall commands from Step 5 |
| Containers healthy but app shows 502 | nginx not started: `docker compose restart nginx` |
| Dump restore fails with "already exists" | Add `--clean --if-exists` flags to the pg_restore command |

### Useful Commands (Ubuntu terminal on server)

```bash
# Check all service statuses
docker compose -f /opt/royan/deploy/docker-compose.yml ps

# Read backend logs live
docker compose -f /opt/royan/deploy/docker-compose.yml logs backend -f

# Restart one service without touching the others
docker compose -f /opt/royan/deploy/docker-compose.yml restart backend

# Check patient count in DB
docker compose exec db psql -U postgres -d synbot_health -c "SELECT COUNT(*) FROM royan_patients;"

# Check current sequence value (should match MAX patient ID after dump)
docker compose exec db psql -U postgres -d synbot_health -c "SELECT last_value FROM royan_patients_id_seq;"

# Run PESE validation directly on server
cd /opt/royan && PYTHONUTF8=1 python backend/tests/e2e_pese.py --url https://localhost --dev-token

# Check watchdog status
sudo systemctl status royan-watchdog

# Get server LAN IP
hostname -I
```

---

## Production Readiness Checklist (NL-implement-guide1.md)

Run through these gates **before** cutting over from DRM Hope to Synbot Health as the primary HMS.

### 1. Database Migrations
- [ ] All migrations 001–135 applied in order (`psql -f backend/migrations/*.sql`)
- [ ] Migration 136 applied (`136_schema_namespacing.sql`) — creates `workflow`, `knowledge`, `integration`, `audit`, `configuration`, `master` schemas
- [ ] Verify schemas exist: `SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('workflow','knowledge','integration');`

### 2. Master Data (MDM)
- [ ] Departments seeded — `SELECT COUNT(*) FROM public.royan_departments;` (expect > 0)
- [ ] Staff records loaded — `SELECT COUNT(*) FROM public.royan_staff;`
- [ ] Lab catalog seeded — `SELECT COUNT(*) FROM public.royan_lab_catalog;`
- [ ] Drug formulary seeded — `SELECT COUNT(*) FROM public.royan_drug_formulary;`
- [ ] Diagnosis catalog seeded — `SELECT COUNT(*) FROM public.royan_diagnosis_catalog;`
- [ ] Workflow definitions seeded — `SELECT COUNT(*) FROM configuration.workflow_definitions;` (expect 4)

### 3. Hope Data Migration (SIF Orchestrator)
- [ ] Bronze watermarks initialized — `SELECT * FROM public.royan_hope_sync_runs LIMIT 5;`
- [ ] Run dry-run against sample Hope dump: `python data-assimilation/orchestrator.py --dump /path/hope.sql --dry-run`
- [ ] No critical errors in dry-run output
- [ ] Full run completed: `python data-assimilation/orchestrator.py --dump /path/hope.sql`
- [ ] Row counts match Hope totals across all 5 domains (patients, encounters, lab, rx, billing)
- [ ] Quality scores logged — `SELECT domain, COUNT(*) FROM public.royan_import_rejections GROUP BY domain;`
- [ ] Rejection rate < 5% per domain

### 4. Canonical API Verification
- [ ] `GET /api/v1/patients/{mrn}/summary` returns populated PatientSummary
- [ ] `GET /api/v1/patients/{mrn}/timeline` returns encounter history
- [ ] `POST /api/v1/capabilities/register-patient` creates patient with MRN (format `RH-YYYYNNNNNN`)
- [ ] `POST /api/v1/capabilities/start-encounter` creates encounter + workflow instance
- [ ] `POST /api/v1/capabilities/complete-consultation/{id}` transitions encounter status
- [ ] `GET /api/v1/workspaces/doctor/{encounter_id}` returns DoctorWorkspace in < 500ms
- [ ] `GET /api/v1/workspaces/nurse/{encounter_id}` returns NurseWorkspace
- [ ] `GET /api/v1/workspaces/billing/{encounter_id}` returns BillingWorkspace

### 5. Workflow State Machine
- [ ] `SELECT COUNT(*) FROM workflow.instances;` > 0 after encounter tests
- [ ] `GET /api/v1/workflow/entity/encounter/{id}` returns current state
- [ ] Encounter lifecycle completes: registered → triaged → in_consultation → billing_pending → discharged
- [ ] Lab order lifecycle: pending → collected → resulted → verified
- [ ] Prescription lifecycle: active → dispensed

### 6. Observability Endpoints
- [ ] `GET /api/v1/ops/health` returns `{"status": "ok"}`
- [ ] `GET /api/v1/ops/clinical-kpis` returns live queue and throughput data
- [ ] `GET /api/v1/ops/workflow-health` shows 0 stuck instances on fresh system
- [ ] `GET /api/v1/ops/data-quality/latest` returns silver_layer_totals
- [ ] `GET /api/v1/ops/knowledge-freshness` responds without error
- [ ] `GET /api/v1/ops/workflow-performance` returns completion rates

### 7. Privacy & Audit (NDPA)
- [ ] `GET /api/v1/privacy/consent/{patient_id}` returns consent records
- [ ] Clinical event log writing confirmed: `SELECT COUNT(*) FROM public.royan_clinical_event_log;`
- [ ] `X-Correlation-ID` header present in all API responses
- [ ] Audit log entries created on patient registration and encounter start

### 8. Clinical Integration Tests
- [ ] Run test suite: `pytest backend/tests/clinical/ -v`
- [ ] All tests in `test_patient_workflow.py` pass or gracefully skip
- [ ] All tests in `test_canonical_capabilities.py` pass or gracefully skip
- [ ] Policy service unit tests pass: `pytest backend/tests/clinical/ -k TestPolicyService -v`

### 9. Performance Baselines
- [ ] `GET /workspaces/doctor/{id}` p95 < 800ms under load
- [ ] `GET /patients/{mrn}/summary` p95 < 400ms
- [ ] DB connection pool healthy: no pool exhaustion under 50 concurrent users
- [ ] Memory usage stable after 1 hour under normal clinic load

### 10. Go-Live Sign-off
- [ ] PESE 68/68 tests pass: `python backend/tests/e2e_pese.py --url https://SERVER_IP --dev-token`
- [ ] Backup confirmed: `docker compose logs backup | grep success`
- [ ] Watchdog active: `sudo systemctl status royan-watchdog`
- [ ] Clinical staff trained on new canonical endpoints and workspace views
- [ ] DRM Hope read-only mode activated (prevent new data entry in legacy system)
- [ ] Rollback plan documented and tested
