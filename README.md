# Alert Analytics Workflow

An automated service that monitors CPU and Memory alerts from **Zabbix**, waits to confirm the alert is real, analyzes which processes are causing the issue, and delivers a detailed report via **email**, **Microsoft Teams**, or both — all without any manual intervention.

---

## What Does It Do?

When your server has high CPU or Memory usage, Zabbix fires an alert. But many alerts resolve themselves within minutes — they are just spikes. This service:

1. **Receives** the alert from Zabbix
2. **Waits 3 minutes** to see if it resolves on its own
3. If still active → **fetches the top processes** consuming CPU/Memory from Zabbix
4. **Compares against 30 days of history** — is this a recurring issue or something new?
5. **Sends notifications** with full analysis — to email, Microsoft Teams, or both

No more investigating every noisy alert. You only get notified when something actually matters.

---

## How It Works — Flow

```
Zabbix fires a CPU/Memory alert
            │
            ▼
  POST /zabbix/events   ← Zabbix Connector sends event here
            │
            │  Ignored automatically:
            │  ✗ Alert resolved on its own (value = 0)
            │  ✗ Not a CPU or Memory alert
            │  ✗ Same alert received twice
            │
            ▼
  Saved to database  →  Status: "pending"
            │
            ▼
  Waits 3 minutes  (configurable)
            │
            ├─ Alert resolved? → Status: "resolved"  (no email, done)
            │
            └─ Still active?
                      │
                      ▼
            Fetch Top-N processes from Zabbix (current snapshot)
                      │
                      ▼
            Fetch last 30 days of process history from Zabbix
                      │
                      ▼
            Analyze each process:
              • How many times has it appeared before?
              • Is it Recurring or a New issue?
              • Who is the primary contributor?
                      │
                      ▼
            Send notifications (independently enabled):
              • Email  — HTML report via Gmail SMTP
              • Teams  — Adaptive Card to channel webhook
                      │
                      ▼
            Status: "notifications sent"
```

---

## Requirements

- Ubuntu / Debian Linux server
- Python 3.10 or higher
- Zabbix 6.4+ (tested on Zabbix 7.4.6)
- Gmail account with App Password enabled (for email notifications)
- Microsoft Teams channel with a webhook configured (for Teams notifications)
- Port open for the service (default: 6666) — or use Cloudflare Tunnel (recommended)

---

## Step-by-Step Setup Guide

### Step 1 — Install Python

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

---

### Step 2 — Clone the Repository

```bash
git clone git@github.com:VectorParkarDevOrg/Alert-Analytics-Workflow.git
cd Alert-Analytics-Workflow
```

---

### Step 3 — Create Virtual Environment and Install Dependencies

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

> A virtual environment keeps the project's Python packages isolated from the rest of your system.

---

### Step 4 — Configure Environment Variables

Copy the example config file and fill in your values:

```bash
cp .env.example .env
nano .env
```

Here is what each variable means:

```env
# ── Zabbix API ──────────────────────────────────────────────────────
# URL to your Zabbix server's API endpoint
ZABBIX_URL=https://your-zabbix-server/api_jsonrpc.php

# API token from Zabbix (see "Zabbix API Token" section below)
ZABBIX_TOKEN=your_api_token_here

# The exact names of the Zabbix items that return top process data
# These must match what exists in your Zabbix templates
CPU_TOP_ITEM_NAME=Top 5 Processes by CPU Utilization
MEMORY_TOP_ITEM_NAME=Top 5 Processes by Memory Utilization

# ── Email / SMTP ────────────────────────────────────────────────────
# Your Gmail address
GMAIL_USER=you@gmail.com

# App Password from Google (NOT your login password — see section below)
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# SMTP server settings — these defaults work for Gmail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Who receives the alert emails — comma-separated
EMAIL_RECIPIENTS=ops@company.com,manager@company.com

# ── Microsoft Teams ──────────────────────────────────────────────────
# Set TEAMS_ENABLED=true and paste your webhook URL to post to a channel.
# Leave TEAMS_ENABLED=false to disable Teams notifications entirely.
TEAMS_ENABLED=false
TEAMS_WEBHOOK_URL=

# ── App ─────────────────────────────────────────────────────────────
# Path to SQLite database file
DB_PATH=./alert_analytics.db

# Port the service listens on
APP_PORT=6666

# ── Alert Processing ─────────────────────────────────────────────────
# How long to wait (seconds) before checking if alert is still active
# Default: 180 = 3 minutes
ALERT_WAIT_SECONDS=180

# How many days of Zabbix history to compare against
HISTORY_DAYS=30

# Maximum number of history snapshots to fetch from Zabbix
HISTORY_LIMIT=500

# How many top processes to include in the report
TOP_PROCESS_COUNT=5
```

---

### Step 5 — Get Your Zabbix API Token

1. Log in to your Zabbix web interface
2. Click your **username** in the top-right corner
3. Go to **API tokens**
4. Click **Create API token**
5. Give it a name (e.g. `alert-analytics`)
6. Set expiry to **never** (or a long duration)
7. Click **Add** and copy the token
8. Paste it as `ZABBIX_TOKEN` in your `.env` file

> **Important:** Zabbix 6.4+ uses Bearer token authentication. Do NOT use username/password.

---

### Step 6 — Get Your Gmail App Password

You cannot use your regular Gmail password. Google requires an App Password for SMTP access.

1. Go to your [Google Account](https://myaccount.google.com)
2. Click **Security**
3. Under "How you sign in to Google", click **2-Step Verification** (enable it if not already)
4. Scroll to the bottom and click **App passwords**
5. Select app: **Mail** — Select device: **Other** → type `Alert Analytics`
6. Click **Generate**
7. Copy the 16-character password and paste it as `GMAIL_APP_PASSWORD` in your `.env`

---

### Step 7 — Configure Notification Channels

The service supports **Email**, **Microsoft Teams**, or **both at the same time**. Each channel is independently controlled via `.env`.

---

#### Option A — Email Only

```env
# Email on, Teams off
EMAIL_RECIPIENTS=ops@company.com,manager@company.com
TEAMS_ENABLED=false
TEAMS_WEBHOOK_URL=
```

Email is always active as long as `EMAIL_RECIPIENTS` is set and Gmail credentials are valid.

---

#### Option B — Microsoft Teams Only

```env
# Teams on, Email off (clear the recipients list)
EMAIL_RECIPIENTS=
TEAMS_ENABLED=true
TEAMS_WEBHOOK_URL=https://your-workflow-webhook-url
```

> When `EMAIL_RECIPIENTS` is empty the email step is skipped automatically.

**Getting the Teams webhook URL — pick one method:**

**Method 1 — Workflow Connector (new Teams, recommended by Microsoft):**
1. Open the Teams channel you want alerts posted to
2. Click **···** next to the channel name → **Workflows**
3. Search for **"Post to a channel when a webhook request is received"**
4. Click it → follow the setup wizard → copy the generated HTTPS URL

**Method 2 — Incoming Webhook (classic Teams):**
1. Open the Teams channel
2. Click **···** → **Connectors**
3. Find **Incoming Webhook** → **Configure**
4. Give it a name (e.g. `Alert Analytics`) → click **Create**
5. Copy the webhook URL

Paste whichever URL you get into `TEAMS_WEBHOOK_URL`.

---

#### Option C — Both Email and Teams

```env
# Both channels active simultaneously
EMAIL_RECIPIENTS=ops@company.com,manager@company.com
TEAMS_ENABLED=true
TEAMS_WEBHOOK_URL=https://your-workflow-webhook-url
```

Both notifications are sent for every confirmed alert. A failure in one channel does not block the other.

---

### Step 8 — Test Zabbix Connection

Before starting the service, verify that your Zabbix credentials are correct:

```bash
source venv/bin/activate
python test_zabbix.py
```

You should see:
```
✓ HTTP 200 — server reachable
✓ Zabbix API version: 7.x.x
✓ Token valid — API token accepted
```

To check if a specific host has the required process items:

```bash
python test_zabbix.py your-hostname
```

---

### Step 9 — Test Email

Send a sample HTML email to all configured recipients:

```bash
python test_email.py
```

Check your inbox — if you receive the email, SMTP is working correctly.

---

### Step 10 — Test Teams Notification

Post a sample Adaptive Card to your configured Teams channel:

```bash
python test_teams.py
```

You should see the card appear in the channel within a few seconds. The card includes:
- Alert type, host, severity, and time
- Top 5 processes with usage values
- Recurring vs. new process classification
- Analysis summary

If the script prints `Notification posted` but nothing appears in Teams, verify that the Power Automate flow (or Incoming Webhook connector) is active and the URL in `.env` is correct.

> Skip this step if you are not using Teams (`TEAMS_ENABLED=false`).

---

### Step 11 — Install as a System Service

The service runs as a background daemon that starts automatically on boot.

First, update the service file with the correct path for your server:

```bash
nano alert-analytics.service
```

Change these lines to match your setup:

```ini
User=your-linux-username
WorkingDirectory=/path/to/Alert-Analytics-Workflow
EnvironmentFile=/path/to/Alert-Analytics-Workflow/.env
ExecStart=/path/to/Alert-Analytics-Workflow/venv/bin/uvicorn main:app --host 0.0.0.0 --port ${APP_PORT}
```

Then install and start it:

```bash
sudo cp alert-analytics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alert-analytics
sudo systemctl start alert-analytics
```

Check it is running:

```bash
sudo systemctl status alert-analytics
```

You should see `Active: active (running)`.

---

### Step 12 — Make the Service Reachable

**Option A — Cloudflare Tunnel (Recommended)**

If you use Cloudflare, this is the cleanest option — no ports need to be opened.

1. Go to **Cloudflare Zero Trust** → Networks → Tunnels → your tunnel → **Public Hostnames**
2. Click **Add a hostname**

| Field | Value |
|-------|-------|
| Subdomain | `alert` |
| Domain | `yourdomain.com` |
| Type | `HTTP` |
| URL | `localhost:6666` |

3. Save — Cloudflare handles SSL automatically
4. Your service is now available at `https://alert.yourdomain.com`

**Option B — Direct Port (No Cloudflare)**

Open port 6666 in your firewall:

```bash
sudo ufw allow 6666/tcp
```

Also open port 6666 in your cloud provider's security group (AWS / Azure / GCP) if applicable.

---

### Step 13 — Configure Zabbix Connector

The Zabbix Connector automatically pushes all events to your service in real time.

In Zabbix: **Administration → Connectors → Create connector**

| Field | Value |
|-------|-------|
| Name | Alert Analytics Workflow |
| Data type | Events |
| URL | `https://alert.yourdomain.com/zabbix/events` |
| HTTP method | POST |
| Timeout | 10s |

> If not using Cloudflare, use `http://YOUR_SERVER_IP:6666/zabbix/events`

Click **Add** to save.

---

### Step 14 — Verify Everything Works

```bash
# Health check
curl -s https://alert.yourdomain.com/health
# Expected: {"status":"ok"}

# Check for incoming alerts
curl -s https://alert.yourdomain.com/alerts
```

Watch live logs while waiting for an alert:

```bash
sudo journalctl -u alert-analytics -f
```

---

## Zabbix Item Requirements

The service fetches process data from specific Zabbix items. These items must exist on your monitored hosts and return **JSON format**.

| Alert Type | Zabbix Item Name |
|------------|-----------------|
| CPU | `Top 5 Processes by CPU Utilization` |
| Memory | `Top 5 Processes by Memory Utilization` |

The item's value must look like this:

```json
{"nginx": 45.2, "mysqld": 22.1, "python3": 12.4, "node": 8.3, "sshd": 2.1}
```

If your item names are different, update `CPU_TOP_ITEM_NAME` and `MEMORY_TOP_ITEM_NAME` in your `.env` file.

Run this to discover item names on a specific host:

```bash
python test_zabbix.py your-hostname
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/zabbix/events` | Receives events from Zabbix Connector |
| `POST` | `/alert` | Manually inject an alert (for testing) |
| `GET` | `/alert/{alert_id}/status` | Check the status of a specific alert |
| `GET` | `/alerts` | List recent alerts (default: last 50) |
| `GET` | `/health` | Liveness check |

### Manually send a test alert

```bash
curl -s -X POST https://alert.yourdomain.com/alert \
  -H "Content-Type: application/json" \
  -d @test_alert.json | python3 -m json.tool
```

### Check alert status

```bash
curl -s https://alert.yourdomain.com/alert/ALERT-ID/status | python3 -m json.tool
```

---

## Alert Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Alert received, waiting for the 3-minute analysis window |
| `resolved` | Alert cleared itself before analysis ran — no email sent |
| `email_sent` | Full analysis complete, email delivered to recipients |
| `error` | Something went wrong — check the logs |

---

## Day-to-Day Operations

```bash
# View live logs
sudo journalctl -u alert-analytics -f

# View last 100 log lines
sudo journalctl -u alert-analytics -n 100

# Restart after a config change
sudo systemctl restart alert-analytics

# Stop / Start
sudo systemctl stop alert-analytics
sudo systemctl start alert-analytics

# Check service status
sudo systemctl status alert-analytics
```

### View alerts in the database directly

```bash
sqlite3 alert_analytics.db "SELECT alert_id, host, alert_type, status, created_at FROM alerts ORDER BY created_at DESC LIMIT 20;"
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Service won't start | Wrong path in service file | Check `WorkingDirectory` and `ExecStart` paths in `alert-analytics.service` |
| `{"status":"ok"}` not returned | Service not running or port blocked | Run `systemctl status alert-analytics` and check firewall |
| No alerts appearing | Zabbix Connector URL wrong | Verify URL in Zabbix → Administration → Connectors |
| Alert stuck on `pending` | Still within 3-minute wait | Wait 3 minutes, then check logs with `journalctl -u alert-analytics -f` |
| Status `error` | Zabbix unreachable or item missing | Check logs for exact error, run `python test_zabbix.py <hostname>` |
| No email received | Wrong App Password or recipients | Run `python test_email.py` to isolate SMTP issues |
| No Teams notification | Channel not configured | Check `TEAMS_ENABLED=true` and `TEAMS_WEBHOOK_URL` is set in `.env` |
| Teams card not appearing | Webhook URL invalid or flow inactive | Run `python test_teams.py` — if it prints `Notification posted` but nothing appears, check that the Power Automate flow or Incoming Webhook connector is active |
| Zabbix token error | Using old username/password format | Zabbix 6.4+ needs Bearer token — generate one from Zabbix UI |
| Item not found | Item name mismatch | Run `python test_zabbix.py <hostname>` and update `CPU_TOP_ITEM_NAME` / `MEMORY_TOP_ITEM_NAME` in `.env` |

---

## Project Structure

```
Alert-Analytics-Workflow/
├── main.py                # FastAPI app — all HTTP endpoints
├── alert_processor.py     # Background workflow: wait → check → analyze → notify
├── zabbix_client.py       # Zabbix API client (Bearer token, JSON-RPC)
├── process_analyzer.py    # Analysis logic — recurring vs new processes
├── email_notifier.py      # Gmail SMTP sender with HTML template
├── teams_notifier.py      # Microsoft Teams Adaptive Card via webhook
├── models.py              # Database tables (Alert, ProcessSnapshot)
├── database.py            # SQLite setup
├── config.py              # All settings loaded from .env
├── templates/
│   └── alert_email.html   # HTML email template
├── alert-analytics.service # Systemd service file
├── requirements.txt
├── .env.example           # Template — copy to .env and fill in values
├── test_zabbix.py         # Test Zabbix API connectivity and items
├── test_email.py          # Test SMTP — sends a real sample email
├── test_teams.py          # Test Teams webhook — posts a sample card to channel
├── test_alert.json        # Sample alert payload for manual testing
└── COMMANDS.md            # Quick command reference
```

---

## Deploying to a New Server

```bash
# 1. Clone the repo
git clone git@github.com:VectorParkarDevOrg/Alert-Analytics-Workflow.git
cd Alert-Analytics-Workflow

# 2. Install Python venv package if needed
sudo apt install -y python3.12-venv

# 3. Create virtualenv and install dependencies
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
nano .env   # fill in all values

# 5. Test connections
venv/bin/python test_zabbix.py
venv/bin/python test_email.py
venv/bin/python test_teams.py   # skip if Teams not configured

# 6. Update service file paths, then install
nano alert-analytics.service
sudo cp alert-analytics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alert-analytics

# 7. Verify
curl -s http://localhost:6666/health
```
