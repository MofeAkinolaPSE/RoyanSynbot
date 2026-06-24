# PCD Queue Management System — Full Analysis & Royanhealth Integration Guide

> **Purpose:** Complete breakdown of every backend and frontend element in `PCD_Queue`, with a step-by-step guide for porting it as a feature into Royanhealth.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Tech Stack](#2-tech-stack)
3. [Backend Architecture](#3-backend-architecture)
   - 3.1 Data Models
   - 3.2 API Endpoints
   - 3.3 Business Logic Services
   - 3.4 Real-Time (WebSocket)
   - 3.5 Authentication & RBAC
   - 3.6 Configuration
4. [Frontend Architecture](#4-frontend-architecture)
   - 4.1 Pages & Responsibilities
   - 4.2 API Client Layer
   - 4.3 Display Card Logic
   - 4.4 Real-Time (WebSocket in UI)
   - 4.5 Routing & Auth Guards
   - 4.6 Styling System
5. [Key Patterns to Replicate](#5-key-patterns-to-replicate)
6. [Royanhealth Integration Plan](#6-royanhealth-integration-plan)
7. [Verification Checklist](#7-verification-checklist)

---

## 1. System Overview

**PCD Queue Management System (PCD_QMS)** is a real-time patient queue orchestration platform for Premier Care Diagnostics. It handles:

- Patient registration and ticket generation
- Queue management across multiple departments
- Live display boards for waiting areas
- Analytics and KPI dashboards for supervisors
- Staff access control (RBAC: front_desk, radiographer, admin)
- External system integration via signed webhooks (eClinicPlus)

**Porting goal:** Embed all of the above as a self-contained **"Queue Management" feature/module** inside Royanhealth.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.11) |
| ORM | SQLAlchemy + Alembic |
| Database | PostgreSQL (psycopg2) |
| Cache / Queue | Redis (sorted sets) |
| Real-time | Native WebSockets (FastAPI) |
| Auth | JWT (HS256) + Refresh Tokens + TOTP MFA |
| Async Tasks | Celery (optional) |
| Containerisation | Docker + docker-compose |
| Frontend | React 18 + TypeScript 5 (Vite) |
| Styling | Tailwind CSS 3 + ShadcnUI (Radix primitives) |
| Charts | Recharts 2 |
| API State | TanStack React Query 5 |
| Routing | react-router-dom v6 |
| Notifications | Sonner (toast) |
| Real-time (FE) | Native WebSocket API |

---

## 3. Backend Architecture

### 3.1 Data Models

All models live in `app/models/`. Below is every table with all fields.

#### `tickets` (core entity)
| Field | Type | Notes |
|---|---|---|
| id | PK (int) | |
| ticket_number | String(50), indexed | Format: `{DEPT}-{SEQ:03d}` e.g. `RAD-042` |
| seq_date | Date | Day the ticket was issued |
| seq_number | Integer | Daily counter per department |
| ticket_day_key | String(30), indexed | ISO date string — for display caching |
| patient_id | FK → patients | |
| department_id | FK → departments | |
| service_id | FK → services | |
| priority | Enum | `emergency`, `paediatrics`, `elderly`, `expectant`, `normal` |
| status | Enum | `created → waiting → called → in_service → completed` or `skipped` |
| is_appointment | Boolean | Walk-in vs. appointment |
| is_late | Boolean | Arrived after appointment time |
| notes | String(255) | Optional freetext |
| registration_time | DateTime | Auto on creation |
| queue_entry_time | DateTime | Set when ticket enters queue |
| call_time | DateTime | Set when radiographer calls patient |
| service_start_time | DateTime | Set when service begins |
| service_end_time | DateTime | Set when service completes |
| created_by | FK → users | Who created the ticket |

**Unique constraint:** `(seq_date, department_id, seq_number)` — ensures daily per-dept sequence is unique.

**Status flow diagram:**
```
[created] → [waiting] → [called] → [in_service] → [completed]
                ↑           |
                └───────[skipped] (via reinsert)
```

#### `patients`
| Field | Type | Notes |
|---|---|---|
| id | PK | |
| external_id | String(100), indexed | ID from external systems (eClinicPlus) |
| first_name | String(100) | |
| last_name | String(100) | |
| dob | Date, nullable | |
| phone | String(30), nullable | |
| gender | String(20), nullable | |
| prefers_whatsapp | Boolean | Notification preference |
| prefers_sms | Boolean | Notification preference |
| is_active | Boolean | |
| created_at | DateTime | |

#### `departments`
| Field | Type | Notes |
|---|---|---|
| id | PK | |
| name | String(100), unique | e.g. Radiology |
| code | String(10), unique, indexed | e.g. `RAD` |
| target_wait_minutes | Integer, nullable | SLA threshold |
| created_at | DateTime | |

**Seeded on startup:** PAT, RAD, DIA, CAR

#### `services`
| Field | Type | Notes |
|---|---|---|
| id | PK | |
| name | String(100) | e.g. MRI Scan |
| code | String(20), indexed | e.g. `MRI` |
| avg_duration_min | Integer | Default 15 |
| department_id | FK → departments | |
| created_at | DateTime | |

**Seeded on startup:** 15 services across 4 departments (Biopsy, Blood Panel, Histology, Echo, EEG, MRI, CT, X-ray, US, HD, PD, ECG, Holter, etc.)

#### `users`
| Field | Type | Notes |
|---|---|---|
| id | PK | |
| username | String(150), unique, indexed | |
| hashed_password | String(255) | bcrypt |
| role | Enum | `front_desk`, `radiographer`, `admin` |
| is_active | Boolean | |
| mfa_enabled | Boolean | TOTP |
| mfa_secret | String(64), nullable | |
| created_at | DateTime | |

#### `audit_logs`
| Field | Type | Notes |
|---|---|---|
| id | PK | |
| ticket_id | FK → tickets, indexed | |
| action | String(100) | e.g. `ticket_created`, `service_started` |
| from_status | String(50), nullable | |
| to_status | String(50), nullable | |
| performed_by | FK → users, nullable | |
| details | JSON, nullable | Extra metadata |
| created_at | DateTime | |

#### Supporting tables
- **`auth_logs`** — All login attempts (user_id, event, success, ip, timestamp)
- **`refresh_tokens`** — Session management (user_id, token, expires_at, revoked)
- **`user_action_logs`** — Admin actions audit (actor, target, action, success, ip)

---

### 3.2 API Endpoints

All routes are prefixed with `/api`.

#### Auth (`/api/auth`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/token` | None | Login; returns `access_token` + `refresh_token` |
| GET | `/me` | Bearer | Current user info |
| POST | `/mfa/setup` | Bearer | Generate TOTP secret |
| POST | `/mfa/verify` | Bearer | Confirm TOTP enablement |
| POST | `/refresh` | None | Exchange refresh_token for new tokens |
| POST | `/logout` | None | Revoke refresh_token |

**Rate limiting:** 5 failed attempts → 15-min Redis lockout.

#### Tickets (`/api/tickets`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/` | front_desk/admin | Create ticket (generates seq, enqueues, broadcasts WS) |
| GET | `/{ticket_id}` | None | Get single ticket |
| GET | `/` | radiographer/admin | List tickets; filter by `department_code`, `status` |

**Ticket creation flow:**
1. Validate patient, department, service exist
2. Generate daily sequence number via Redis counter (`ticket:seq:{dept_code}:{date}`)
3. Format ticket number as `{DEPT}-{SEQ:03d}`
4. Insert ticket with `status=waiting`, set `queue_entry_time`
5. Push ticket ID to Redis sorted set with timestamp score
6. Write audit log entry
7. Broadcast `ticket_created` event via WebSocket

#### Queue (`/api/queue`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/{department_code}` | None | List waiting tickets in queue order |
| GET | `/{department_code}/summary` | None | `{queue_length, avg_wait_minutes}` |
| POST | `/{department_code}/next` | radiographer/admin | Pop and call next ticket |
| POST | `/tickets/{ticket_id}/call` | radiographer/admin | Call specific ticket |
| POST | `/tickets/{ticket_id}/start` | radiographer/admin | Start service (capacity-checked) |
| POST | `/tickets/{ticket_id}/complete` | radiographer/admin | Mark completed; send notification |
| POST | `/tickets/{ticket_id}/skip` | radiographer/admin | Move to skipped |
| POST | `/tickets/{ticket_id}/reinsert` | radiographer/admin | Re-queue a skipped ticket |

**Capacity rule:** Max 10 tickets in `in_service` state per department (configurable via `QUEUE_MAX_IN_SERVICE_PER_DEPARTMENT`).

#### Display (`/api/display`)
| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/` | `department_code?`, `limit` (1-50), `per_status_limit?` | Returns `called` + `in_service` tickets, sorted by recency |

This is the endpoint for the public waiting-room screen.

#### Metrics (`/api/metrics`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/department/{dept_code}` | admin | `{avg_wait, queue_length, sla%, completed_today}` |
| GET | `/throughput` | admin | Daily completed count per dept (range: today/week/month/all) |
| GET | `/peak-hours` | admin | Registrations grouped by hour |
| GET | `/overview` | admin | System-wide KPIs |
| GET | `/median-wait` | admin | Median wait vs target per dept |
| GET | `/funnel` | admin | Stage-by-stage timing (reg→queue→call→start→complete) |

#### Users (`/api/users`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/` | admin | Create user |
| GET | `/` | admin | List all users |
| PATCH | `/{user_id}/deactivate` | admin | Deactivate |
| DELETE | `/{user_id}` | admin | Delete (cannot delete self or other admins) |
| POST | `/me/change-password` | any | Change own password |
| POST | `/{user_id}/reset-password` | admin | Admin-forced password reset |

#### Departments (`/api/departments`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | None | List all (ordered by name) |
| PATCH | `/{dept_id}` | admin | Update `target_wait_minutes` |

#### Services (`/api/services`)
| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/` | `department_code?` | List services; optional dept filter |

#### Patients (`/api/patients`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/` | front_desk/admin | Create patient |
| GET | `/{patient_id}` | front_desk/admin | Get patient |

#### Integration (`/api/integrations`)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/events` | HMAC-SHA256 webhook signature | Ingest patient + ticket from external system |

**Signature format:** `sha256=hmac_sha256(ECLINIC_WEBHOOK_SECRET, raw_body).hexdigest()`  
**Deduplication:** Redis key per `event_id` with 24-hr TTL.

#### Health & WebSocket
| Type | Path | Description |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| WS | `/ws/{department_code}` | Real-time events per department |

---

### 3.3 Business Logic Services

#### Queue Engine (`app/services/queue_engine.py`)
Redis sorted-set backed FIFO queue, one per department:
- **Key pattern:** `queue:{department_code}`
- **Score:** `queue_entry_time` as Unix timestamp (ensures FIFO ordering)
- **Operations:** `enqueue`, `pop_next` (zpopmin), `remove` (zrem), `list_queue` (zrange), `reorder`

#### Notification Service (`app/services/notification.py`)
Event-driven notifications sent after ticket state transitions:
- `send_ticket_created` — After ticket POST
- `send_queue_approaching` — When patient is near the front
- `send_service_completed` — After complete
- `send_feedback_request` — Post-completion survey
- Channels: SMS (if `prefers_sms=True`) and/or WhatsApp (if `prefers_whatsapp=True`)
- Default provider: `LoggingChannelProvider` (logs to stdout — swap for real SMS/WA provider)

#### Seed Data (`app/services/seed_data.py`)
Idempotent on startup (`SEED_ON_STARTUP=true`):
- Upserts 4 departments and 15 services
- Creates bootstrap admin if `BOOTSTRAP_ADMIN_USERNAME` + `BOOTSTRAP_ADMIN_PASSWORD` are set

#### ID Generator (`app/utils/id_generator.py`)
```python
generate_ticket_number(dept_code, seq_number) → f"{dept_code}-{seq_number:03d}"
# "RAD-042"
```
Redis counter key: `ticket:seq:{dept_code}:{YYYY-MM-DD}` — increments atomically on each ticket creation, retries up to 5 times on collision.

---

### 3.4 Real-Time (WebSocket)

**Manager** (`app/realtime/websocket_manager.py`):
```python
class WebSocketManager:
    _rooms: dict[str, set[WebSocket]]  # dept_code → connected clients
    connect(ws, room)      # accept + add to room
    disconnect(ws, room)   # remove from room
    broadcast(room, msg)   # send JSON to all room clients; auto-cleans dead sockets
```

**Events emitted** (each is a JSON object with `event` key):
| Event | Emitted when |
|---|---|
| `ticket_created` | New ticket added to queue |
| `ticket_called` | Radiographer calls a ticket |
| `service_started` | Service begins |
| `service_completed` | Service complete |
| `ticket_skipped` | Ticket deferred |
| `ticket_reinserted` | Skipped ticket returned to queue |

**Usage:** Each department is a "room". The WS endpoint is `/ws/{department_code}`.

---

### 3.5 Authentication & RBAC

**Security** (`app/core/security.py`):
- Passwords: bcrypt via `passlib`
- Access token: JWT HS256, 60-min expiry, payload `{sub: username, exp: timestamp}`
- Refresh token: 48-byte URL-safe random, stored in DB, 7-day TTL
- OAuth2 scheme: `OAuth2PasswordBearer(tokenUrl="/api/auth/token")`

**RBAC** (`app/core/permissions.py`):
```python
require_roles(*roles)  # FastAPI dependency — raises 403 if user role not in list
```

**Roles:**
| Role | Can Do |
|---|---|
| `front_desk` | Create patients and tickets |
| `radiographer` | All queue operations (call, start, complete, skip) |
| `admin` | Everything above + user management + metrics + dept config |

---

### 3.6 Configuration (`app/core/config.py`)

Key environment variables:

```
DATABASE_URL=postgresql+psycopg2://...
REDIS_URL=redis://redis:6379/0
SECRET_KEY=<strong-random-key>
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_MAX_ATTEMPTS=5
AUTH_LOCKOUT_MINUTES=15
SLA_WAIT_MINUTES=30
QUEUE_MAX_IN_SERVICE_PER_DEPARTMENT=10
SEED_ON_STARTUP=true
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=<password>
ECLINIC_WEBHOOK_SECRET=<secret>
WHATSAPP_PROVIDER=log
SMS_PROVIDER=log
```

---

## 4. Frontend Architecture

### 4.1 Pages & Responsibilities

#### `Index.tsx` — Landing / Home
- Static marketing page describing the QMS
- Four entry-point cards: Front Desk, Queue Control, Supervisor, Public Display
- Department listing (PAT, RAD, DIA, CAR)
- Links to `/sign-in?target={module}`

#### `SignIn.tsx` — Authentication
- Username + password + optional MFA code
- Calls `POST /api/auth/token` (form-encoded)
- Calls `GET /api/auth/me` for role
- Stores `access_token`, `refresh_token`, `user_role`, `user_name` in `localStorage`
- Routes based on role: front_desk → `/front-desk`, radiographer → `/queue-control`, admin → `/supervisor`

#### `FrontDesk.tsx` — Patient Registration
- Creates patient then creates ticket in one flow
- Form fields: Patient name, phone, department (tab selector), service (dropdown), priority (5 options), notification preference (SMS / WhatsApp / both)
- Shows real-time queue status cards: "X patients in queue", "~Y min avg wait", status badge
- On success: displays the issued ticket number prominently

#### `RadiographerDashboard.tsx` — Queue Control
- Department tab switcher
- Stats row: Waiting / In Service / Completed / Total
- Live queue list — one card per ticket showing:
  - Position number
  - Ticket number
  - Patient name & service
  - Color-coded status badge
  - Priority badge (Emergency, Paediatrics flags)
  - Contextual action buttons (Call → In Service → Complete; Skip)
- WebSocket listener: auto-refreshes queue on any WS message for the selected department

#### `PublicDisplay.tsx` — Waiting Area Board
- Full-screen TV display (`h-screen`)
- Header: Logo, title, live clock + date (updated every second)
- Two columns: "Now Serving" (up to 6 in_service/called tickets) and "Queue" (up to 6 waiting)
- First ticket in each column highlighted with accent ring
- Large accessible text
- Dual update strategy: WebSocket on all departments + polling every 5 seconds (fallback)
- No personal patient info shown — ticket numbers only

#### `SupervisorDashboard.tsx` — Analytics & Admin
- **5 KPI stat cards:** Avg Wait, Completed Today, SLA Compliance %, Staff Utilization %, Peak Hour
- **8 chart panels** (Recharts):
  - Median Wait vs Target (BarChart)
  - Door-to-Service Funnel (horizontal BarChart)
  - Avg Wait by Department (BarChart)
  - Completed Tickets by Department (BarChart)
  - Peak Hours Analysis (LineChart)
  - Dept Throughput Comparison (BarChart)
  - SLA Compliance (RadarChart)
  - Queue Load (RadarChart)
- **Performance Summary Table:** Dept, Avg Wait, Completed, SLA%, Queue Length, Status badge
- **Time range filter:** today / week / month / all
- **Department filter:** dropdown
- **Service Standards editor:** Edit `target_wait_minutes` per department inline
- **Staff management panel:** Create user (username, password, role), list all users with Deactivate / Reset Password / Delete actions

#### `AnalyticsData.tsx` — Deep Analytics
- Route: `/analytics/:chartType` (8 chart types)
- Full-page view of a single chart with table, column headers adapt per chart type
- CSV export button
- Time range + department filters

---

### 4.2 API Client Layer (`QM_front/client/lib/api.ts`)

Single file, no external HTTP library. Key patterns:

**Base URL:** `import.meta.env.VITE_API_BASE_URL` (defaults to `http://localhost:8000`)

**`apiFetch<T>(path, options, retry)`** — core fetch wrapper:
- Injects `Authorization: Bearer {access_token}` header
- On 401: calls `POST /api/auth/refresh`, stores new tokens, retries original request once
- Parses JSON or throws descriptive error

**`cachedFetch<T>(path, ttlMs)`** — in-memory cache:
- Used for `/api/departments` and `/api/services` with 5-minute TTL
- `Map<string, {data, expiry}>` — checked before every fetch

**`buildDepartmentWebSocketUrl(departmentCode)`**:
```typescript
// http://localhost:8000/api → ws://localhost:8000/ws/RAD
```

**Full method list:**

| Method | HTTP | Endpoint |
|---|---|---|
| `login(username, password, mfaCode?)` | POST | `/auth/token` |
| `getMe()` | GET | `/auth/me` |
| `listDepartments()` | GET (cached 5m) | `/departments` |
| `updateDepartment(id, data)` | PATCH | `/departments/{id}` |
| `listServices(deptCode?)` | GET (cached 5m) | `/services` |
| `createPatient(data)` | POST | `/patients` |
| `createTicket(data)` | POST | `/tickets` |
| `getQueue(deptCode)` | GET | `/queue/{deptCode}` |
| `getQueueSummary(deptCode)` | GET | `/queue/{deptCode}/summary` |
| `listTickets(deptCode)` | GET | `/tickets?department_code=` |
| `listDisplayTickets(limit, perStatusLimit?)` | GET | `/display` |
| `callNext(deptCode)` | POST | `/queue/{deptCode}/next` |
| `callTicket(ticketId)` | POST | `/queue/tickets/{id}/call` |
| `startService(ticketId)` | POST | `/queue/tickets/{id}/start` |
| `completeService(ticketId)` | POST | `/queue/tickets/{id}/complete` |
| `skipTicket(ticketId)` | POST | `/queue/tickets/{id}/skip` |
| `reinsertTicket(ticketId)` | POST | `/queue/tickets/{id}/reinsert` |
| `getDepartmentMetrics(deptCode)` | GET | `/metrics/department/{code}` |
| `getThroughputMetrics(range)` | GET | `/metrics/throughput` |
| `getPeakHoursMetrics(range)` | GET | `/metrics/peak-hours` |
| `getOverviewMetrics(range)` | GET | `/metrics/overview` |
| `getMedianWaitKpi(range, deptCode?)` | GET | `/metrics/median-wait` |
| `getFunnelKpi(range, deptCode?)` | GET | `/metrics/funnel` |
| `listUsers()` | GET | `/users` |
| `createUser(data)` | POST | `/users` |
| `deactivateUser(userId)` | PATCH | `/users/{id}/deactivate` |
| `deleteUser(userId)` | DELETE | `/users/{id}` |
| `resetUserPassword(userId, pwd)` | POST | `/users/{id}/reset-password` |

---

### 4.3 Display Card Logic

This is the UI rendering logic for the queue board and dashboard cards.

#### Ticket Status Colors
```
waiting     → gray border/badge
called      → blue (accent) border/badge
in_service  → purple border/badge
completed   → green border/badge
skipped     → red border/badge
```

#### Priority Badges
```
emergency   → red "Emergency" pill (always shown prominently)
paediatrics → orange "Paediatric" pill
elderly     → orange "Elderly" pill
expectant   → orange "Expectant" pill
normal      → no extra badge
```

#### Queue Card (RadiographerDashboard)
```
┌──────────────────────────────────────────────────┐
│ #1   [RAD-042]  [● Called]     [⚡ Emergency]   │
│      Jane Doe · MRI Scan                         │
│                              [In Service] [Skip] │
└──────────────────────────────────────────────────┘
```
- Left border color = status color
- Position number on far left
- Ticket number + status badge in header row
- Priority badge in header row (if not normal)
- Patient name + service name body
- Contextual action buttons on right/bottom

#### Public Display Card (PublicDisplay)
```
┌─────────────────────┐
│   RAD-042           │  ← large text
│   ● In Service      │  ← status with colored dot
└─────────────────────┘
```
- First card in "Now Serving" gets `ring-2 ring-accent` highlight
- Minimal info: ticket number + status only (no patient name for privacy)

#### Queue Status Card (FrontDesk)
```
┌─────────────────────┐
│ 👥 Patients in Queue│
│        12           │  ← large number
│   ⚠ High Queue      │  ← badge: green "Normal Flow" / amber "High Queue"
└─────────────────────┘
```

#### KPI Stat Card (SupervisorDashboard)
```
┌─────────────────────┐
│ 📊 Avg Wait Time    │
│      14 min         │  ← large value
│   ↑ +2 from target  │  ← optional comparison
└─────────────────────┘
```

#### InteractiveHoverButton (`client/components/ui/interactive-hover-button.tsx`)
Custom button with: variants (primary/secondary/accent/destructive/success/warning), sizes (sm/md/lg), loading spinner, optional icon, full-width mode, shadow/scale hover animation. Used on every interactive element across all pages.

---

### 4.4 Real-Time (WebSocket in UI)

Two pages use WebSockets:

**RadiographerDashboard — single department socket:**
```typescript
useEffect(() => {
  const ws = new WebSocket(buildDepartmentWebSocketUrl(selectedDept));
  ws.onmessage = async () => { await refreshQueue(selectedDept); };
  return () => ws.close();
}, [selectedDept]);
```

**PublicDisplay — socket per department + polling fallback:**
```typescript
// Opens one socket per department
const sockets = departments.map(d => {
  const ws = new WebSocket(buildDepartmentWebSocketUrl(d.code));
  ws.onmessage = loadDisplay;
  return ws;
});
// Also polls every 5 seconds as fallback
const pollInterval = setInterval(loadDisplay, 5000);
return () => { sockets.forEach(s => s.close()); clearInterval(pollInterval); };
```

---

### 4.5 Routing & Auth Guards (`App.tsx`)

```
/ → Index (public)
/sign-in → SignIn (public)
/front-desk → FrontDesk (RequireAuth: front_desk, admin)
/queue-control → RadiographerDashboard (RequireAuth: radiographer, admin)
/supervisor → SupervisorDashboard (RequireAuth: admin)
/analytics/:chartType → AnalyticsData (RequireAuth: admin)
/display → PublicDisplay (RequireAuth: any authenticated role)
* → NotFound
```

**`RequireAuth` component:**
- Checks `localStorage.access_token` and `localStorage.user_role`
- Validates role is in `allowedRoles` array
- Redirects to `/sign-in?redirect={path}` on failure

---

### 4.6 Styling System

**Colors (CSS custom properties in `global.css`):**
```css
--primary: 288 82% 32%    /* Deep Purple  #790F94 */
--accent:  216 59% 46%    /* Medical Blue #3066B9 */
--destructive: 5 63% 46% /* Error Red    #C0392B */
--success: 120 100% 25%  /* Success Green        */
--warning: 45 100% 51%   /* Amber                */
--background: 90 5% 96%  /* Light Beige  #F6F7F5 */
```

**Fonts:** Inter (body) + Space Grotesk (headings) from Google Fonts.

**Animations:** `fadeUp` (700ms slide-in on mount), `float` (continuous vertical bounce).

**Component library:** ShadcnUI — 45+ pre-built Radix UI components. All in `client/components/ui/`.

---

## 5. Key Patterns to Replicate

### Pattern 1: Ticket Number Generation
```
Redis INCR ticket:seq:{dept_code}:{YYYY-MM-DD}
→ pad to 3 digits
→ prefix with department code
→ "RAD-042"
```
If Redis is unavailable, fall back to DB `MAX(seq_number) + 1` with a retry loop (max 5).

### Pattern 2: Queue as Redis Sorted Set
```
Key: queue:{dept_code}
Score: queue_entry_time.timestamp()  (float)
Member: ticket_id
```
Operations: `ZADD` (enqueue), `ZPOPMIN` (call next), `ZREM` (remove), `ZRANGE` (list in order).

### Pattern 3: Status State Machine
Only valid transitions (enforced in queue.py route handlers):
```
waiting → called (via call/callNext)
called → in_service (via start — capacity checked)
in_service → completed (via complete)
waiting/called → skipped (via skip)
skipped → waiting (via reinsert — re-enqueued)
```

### Pattern 4: Audit Trail on Every State Change
Every route that changes ticket status calls:
```python
db.add(AuditLog(
    ticket_id=ticket.id,
    action=action_name,
    from_status=old_status,
    to_status=new_status,
    performed_by=current_user.id,
    details={...}
))
```

### Pattern 5: WebSocket Broadcast After Every State Change
After every ticket mutation, call:
```python
await ws_manager.broadcast(department_code, {
    "event": "ticket_called",  # or whichever event
    "ticket_id": ticket.id,
    "ticket_number": ticket.ticket_number,
    ...
})
```

### Pattern 6: Frontend Token Refresh on 401
The `apiFetch` wrapper catches 401, calls `/auth/refresh`, stores new tokens, retries — completely transparent to all callers.

### Pattern 7: SLA Calculation
```sql
COUNT(tickets WHERE call_time - queue_entry_time <= target_wait_minutes * interval '1 minute')
/ COUNT(tickets WHERE status = 'completed') * 100
```

---

## 6. Royanhealth Integration Plan

### Step 1 — Assess Royanhealth's Existing Stack
Before porting, answer:
- What backend framework does Royanhealth use? (FastAPI, Django, Express, etc.)
- Does it already use PostgreSQL and Redis?
- Does it have an existing auth system? (To decide: reuse or integrate PCD's JWT layer)
- Does it use React on the frontend? What is the routing/state approach?
- Is there an existing design system / component library?

### Step 2 — Backend Integration

**Option A: Mount as a sub-app (recommended for FastAPI + FastAPI)**
```python
# In Royanhealth's main.py
from pcd_queue.app.main import create_app as create_qms_app

qms_app = create_qms_app()
royanhealth_app.mount("/qms", qms_app)
# Queue endpoints now at: /qms/api/queue/...
```

**Option B: Copy routes into existing app**
1. Copy `app/models/` → add to Royanhealth's `models/`
2. Copy `app/api/` (queue, tickets, display, metrics, departments, services, integration) → register on Royanhealth's router under `/qms/` prefix
3. Copy `app/services/queue_engine.py`, `notification.py`, `seed_data.py`
4. Copy `app/realtime/websocket_manager.py`
5. Share the existing `db.py` and `security.py` if compatible; otherwise copy and adjust imports
6. Run Alembic migrations to add the new tables alongside Royanhealth's existing schema

**Database considerations:**
- If Royanhealth already has a `users` table, do NOT duplicate — map PCD's `UserRole` enum to Royanhealth's role system and update the `require_roles()` dependency to query the right model
- If Royanhealth already has a `patients` / `clients` table, alias it — add `external_id` column if not present

**Redis:**
- Reuse Royanhealth's existing Redis connection if available; just ensure key namespacing (e.g., `royanhealth:queue:{dept}` instead of `queue:{dept}`)

### Step 3 — Alembic Migrations
Run the two migration files in order:
1. `20260222_0001_initial_schema.py` — creates all tables + enums
2. `20260226_0002_make_ticket_seq_unique_department.py` — fixes the unique constraint

Command:
```bash
alembic upgrade head
```

If Royanhealth already has Alembic configured, copy the migration files into its `alembic/versions/` directory; they are self-contained.

### Step 4 — Environment Variables
Add to Royanhealth's `.env`:
```
# Queue module
SLA_WAIT_MINUTES=30
QUEUE_MAX_IN_SERVICE_PER_DEPARTMENT=10
SEED_ON_STARTUP=true
ECLINIC_WEBHOOK_SECRET=<if integrating eClinicPlus>
WHATSAPP_PROVIDER=log
SMS_PROVIDER=log
```

### Step 5 — Frontend Integration

**Option A: Embed pages inside Royanhealth's React app**
1. Copy these files into Royanhealth's `src/`:
   - `client/lib/api.ts` → update `API_BASE_URL` to point at Royanhealth's backend
   - `client/pages/FrontDesk.tsx`
   - `client/pages/RadiographerDashboard.tsx`
   - `client/pages/PublicDisplay.tsx`
   - `client/pages/SupervisorDashboard.tsx`
   - `client/pages/AnalyticsData.tsx`
   - `client/components/ui/interactive-hover-button.tsx`
2. Add routes in Royanhealth's router:
   ```tsx
   <Route path="/queue/front-desk" element={<FrontDesk />} />
   <Route path="/queue/control" element={<RadiographerDashboard />} />
   <Route path="/queue/display" element={<PublicDisplay />} />
   <Route path="/queue/supervisor" element={<SupervisorDashboard />} />
   <Route path="/queue/analytics/:chartType" element={<AnalyticsData />} />
   ```
3. Wrap with Royanhealth's existing `<RequireAuth>` instead of PCD's, mapping roles accordingly

**Option B: Iframe embed (quickest, for display board)**
If only the `PublicDisplay` screen is needed in Royanhealth:
```html
<iframe src="https://pcd-qms.royanhealth.com/display" />
```

**Styling:**
- If Royanhealth uses Tailwind, copy `global.css` CSS variables — or remap to Royanhealth's brand colors
- ShadcnUI components can coexist with other Tailwind UIs; install via `npx shadcn-ui@latest add <component>`
- Replace `--primary` purple with Royanhealth's brand color

### Step 6 — Connect Auth
- **If reusing PCD's auth:** keep `/qms/api/auth/*` endpoints; update `api.ts` login calls accordingly
- **If Royanhealth has its own auth:** Remove PCD's auth routes; update `apiFetch` in `api.ts` to use Royanhealth's token (it already auto-injects from `localStorage.access_token` — just ensure the same key is used); update `RequireAuth` role mapping

### Step 7 — Seed Departments & Services
On first startup with `SEED_ON_STARTUP=true`, the system auto-creates:
- Departments: Pathology, Radiology, Dialysis, Cardiology
- 15 services across those departments

**To customize for Royanhealth** (e.g., different departments), edit `app/services/seed_data.py` before first run. The function is idempotent — safe to re-run.

### Step 8 — Notification Providers
Current default provider just logs to stdout. To enable real notifications:
1. In `app/services/notification.py`, add a new provider class implementing the `ChannelProvider` interface
2. Set `WHATSAPP_PROVIDER=your_provider` and `SMS_PROVIDER=your_provider` in `.env`
3. Register the provider in the factory lookup

### Step 9 — eClinicPlus Webhook (if needed)
If Royanhealth is also integrated with eClinicPlus:
- Set `ECLINIC_WEBHOOK_SECRET` in `.env`
- Register the `/api/integrations/events` endpoint
- eClinicPlus sends patient + ticket data; the system deduplicates via Redis and upserts

---

## 7. Verification Checklist

Use this to confirm the feature is working after integration:

### Backend
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `POST /api/auth/token` with valid credentials returns `access_token` + `refresh_token`
- [ ] `GET /api/departments` returns 4 seeded departments (or Royanhealth's custom list)
- [ ] `POST /api/patients` creates a patient record
- [ ] `POST /api/tickets` creates a ticket, returns ticket number in `{DEPT}-{SEQ:03d}` format
- [ ] `GET /api/queue/{dept_code}` returns the ticket in order
- [ ] `POST /api/queue/tickets/{id}/call` changes status to `called`, broadcasts WS event
- [ ] `POST /api/queue/tickets/{id}/start` changes status to `in_service` (check capacity limit)
- [ ] `POST /api/queue/tickets/{id}/complete` changes status to `completed`
- [ ] `POST /api/queue/tickets/{id}/skip` changes status to `skipped`
- [ ] `GET /api/display` returns called/in_service tickets for the display board
- [ ] `GET /api/metrics/overview` returns valid KPIs
- [ ] WebSocket `/ws/{dept_code}`: connect in browser console, trigger a queue action, confirm JSON event arrives

### Frontend
- [ ] Landing page renders with department list and role cards
- [ ] Login flow works for all 3 roles; correct page is shown after login
- [ ] FrontDesk: can register a patient and create a ticket; ticket number appears in success message
- [ ] FrontDesk: queue status card shows real-time count and wait time
- [ ] RadiographerDashboard: queue list appears; Call → In Service → Complete flow works; queue updates live via WebSocket
- [ ] PublicDisplay: full-screen board shows "Now Serving" and "Queue" columns; updates within 5 seconds
- [ ] SupervisorDashboard: all 5 KPI cards load; charts render; user management works
- [ ] CSV export on AnalyticsData page downloads a valid file
- [ ] 401 → automatic token refresh → request retried (test by letting access token expire)

---

*Document generated: 2026-06-11. Source project: `c:\Users\DELL\Desktop\Project PSE\Dev\PCD_Queue`.*
