# Alert Analytics Workflow — Command Reference

## Set Server IP (run once per session)

```bash
export SERVER_IP=$(hostname -I | awk '{print $1}')
echo "SERVER_IP=$SERVER_IP"
```

---

## Service Management

```bash
sudo cp alert-analytics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alert-analytics
sudo systemctl start alert-analytics

sudo systemctl start alert-analytics
sudo systemctl stop alert-analytics
sudo systemctl restart alert-analytics
sudo systemctl status alert-analytics
```

---

## Logs

```bash
# Live log stream
sudo journalctl -u alert-analytics -f

# Last 100 lines
sudo journalctl -u alert-analytics -n 100

# Logs since last boot
sudo journalctl -u alert-analytics -b

# Logs between timestamps
sudo journalctl -u alert-analytics --since "2026-04-14 09:00:00" --until "2026-04-14 10:00:00"
```

---

## API Endpoints

```bash
# Health check
curl -s http://$SERVER_IP:6666/health

# List recent alerts (only pending / error shown — completed ones are auto-deleted)
curl -s http://$SERVER_IP:6666/alerts | python3 -m json.tool

# List with custom limit
curl -s "http://$SERVER_IP:6666/alerts?limit=20" | python3 -m json.tool

# Send a manual test alert
curl -s -X POST http://$SERVER_IP:6666/alert \
  -H "Content-Type: application/json" \
  -d @test_alert.json | python3 -m json.tool

# Check a specific alert status
curl -s http://$SERVER_IP:6666/alert/TEST-001/status | python3 -m json.tool
```

---

## Testing

```bash
# Test Zabbix API connectivity
venv/bin/python test_zabbix.py

# Test Zabbix connectivity + item check for a specific host
venv/bin/python test_zabbix.py <zabbix-hostname>

# Send a sample HTML email to all recipients
venv/bin/python test_email.py
```

---

## Database

```bash
sqlite3 alert_analytics.db

# Inside sqlite3:
.tables
# Active / error alerts only (completed ones are auto-deleted)
SELECT alert_id, host, alert_type, status, created_at FROM alerts ORDER BY created_at DESC LIMIT 20;
# Process history (kept permanently for recurring detection)
SELECT host, alert_type, process_name, process_value, snapshot_time FROM process_snapshots ORDER BY snapshot_time DESC LIMIT 20;
.quit
```

---

## Virtual Environment

```bash
source venv/bin/activate
pip install -r requirements.txt

# Run in dev mode with auto-reload
venv/bin/uvicorn main:app --host 0.0.0.0 --port 6666 --reload
```

---

## Zabbix Connector URL

```
https://alert.yourdomain.com/zabbix/events
```
