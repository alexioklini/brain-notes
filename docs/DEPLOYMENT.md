# Deployment & Administration Handbook

## Prerequisites

| Requirement | Version | Purpose |
|------------|---------|---------|
| Python | 3.12+ | Runtime |
| pip | Latest | Package management |
| QMD | Latest | Semantic search (optional) |
| Git | Any | Version control |

### Optional
| Requirement | Purpose |
|------------|---------|
| Caddy/nginx | Reverse proxy with HTTPS |
| launchd/systemd | Process management |
| QMD with embeddings | Semantic search for project resources |

## Installation

### 1. Clone and Setup

```bash
git clone https://github.com/alexioklini/brain-notes.git
cd brain-notes

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install flask flask-cors mcp werkzeug
```

### 2. Configure Environment

Create `.env` file (optional — for AI features):

```bash
# LLM Configuration (for AI chat/inline features)
LLM_BASE_URL=https://api.minimax.io/v1
LLM_API_KEY=sk-your-api-key
LLM_MODEL=MiniMax-M2.1

# App Configuration
SECRET_KEY=your-random-secret-key-here
PORT=5006
```

If no `.env` is provided, the app runs without AI features. A random secret key is generated at startup.

### 3. Initialize Database

The database is created automatically on first run:

```bash
python3.12 app.py
```

Default admin account: `admin` / `admin`

> ⚠️ **Change the admin password immediately after first login!**

### 4. Verify Installation

```bash
curl -s http://localhost:5006/ | head -5
# Should return HTML
```

## Configuration

### LLM Providers (`llm_config.json`)

Brain Notes supports multiple LLM providers configured at runtime through the UI (Settings → LLM Configuration) or via the config file:

```json
{
  "default_provider": "provider_id",
  "default_model": "MiniMax-M2.1",
  "system_prompt": "You are a helpful notes assistant...",
  "providers": {
    "minimax": {
      "name": "MiniMax",
      "base_url": "https://api.minimax.io/v1",
      "api_key": "sk-...",
      "models": ["MiniMax-M2.1", "MiniMax-M2.5"]
    }
  }
}
```

**Supported providers:** Any OpenAI-compatible API (MiniMax, OpenAI, Anthropic via proxy, Ollama, LM Studio, etc.)

### Port Configuration

Default port: `5006`. Change via:

```python
# In app.py (bottom of file)
app.run(host='0.0.0.0', port=5006)
```

Or set `PORT` environment variable.

### QMD Configuration

QMD uses its global configuration. Ensure it's installed and the embedding model is available:

```bash
# Check QMD status
qmd status

# Verify embedding model
qmd embed --help
```

No additional QMD configuration is needed — Brain Notes creates collections automatically when indexing resources.

## Deployment Options

### Option A: Direct (Development)

```bash
cd brain-notes
python3.12 app.py
```

### Option B: launchd (macOS Production)

Create `~/Library/LaunchAgents/com.brain.notes-app.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.brain.notes-app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3.12</string>
        <string>/path/to/brain-notes/app.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/brain-notes</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/brain-notes/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/brain-notes/logs/stderr.log</string>
</dict>
</plist>
```

```bash
# Load
launchctl load ~/Library/LaunchAgents/com.brain.notes-app.plist

# Start/stop
launchctl start com.brain.notes-app
launchctl stop com.brain.notes-app

# Check status
launchctl list | grep notes
```

### Option C: systemd (Linux Production)

Create `/etc/systemd/system/brain-notes.service`:

```ini
[Unit]
Description=Brain Notes
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/brain-notes
ExecStart=/opt/brain-notes/.venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable brain-notes
sudo systemctl start brain-notes
```

### Option D: Reverse Proxy (HTTPS)

**Caddy** (recommended — automatic HTTPS):

```
notes.yourdomain.com {
    reverse_proxy localhost:5006
}
```

**nginx:**

```nginx
server {
    listen 443 ssl;
    server_name notes.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/notes.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/notes.yourdomain.com/privkey.pem;
    
    location / {
        proxy_pass http://127.0.0.1:5006;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Administration

### User Management

**Via UI:** Login as admin → Settings (gear icon) → Admin Panel → Users

**Via API:**
```bash
# List users
curl -b cookies.txt http://localhost:5006/api/admin/users

# Create user
curl -b cookies.txt -X POST http://localhost:5006/api/admin/users \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","password":"secure123","role":"user","display_name":"New User"}'

# Delete user
curl -b cookies.txt -X DELETE http://localhost:5006/api/admin/users/USER_ID
```

### Team Management

```bash
# Create team
curl -b cookies.txt -X POST http://localhost:5006/api/teams \
  -H "Content-Type: application/json" \
  -d '{"name":"Engineering","description":"Engineering team"}'

# Add member
curl -b cookies.txt -X POST http://localhost:5006/api/teams/TEAM_ID/members \
  -H "Content-Type: application/json" \
  -d '{"user_id":"USER_ID","role":"member"}'
```

### Database Backup

```bash
# Simple backup (while app is running — SQLite WAL mode is safe)
cp notes.db notes.db.backup-$(date +%Y%m%d)

# Full backup including WAL
sqlite3 notes.db ".backup notes.db.backup-$(date +%Y%m%d)"
```

### Database Maintenance

```bash
# Vacuum (reclaim space)
sqlite3 notes.db "VACUUM"

# Check integrity
sqlite3 notes.db "PRAGMA integrity_check"

# Show table sizes
sqlite3 notes.db "SELECT name, COUNT(*) FROM sqlite_master WHERE type='table' GROUP BY name"
```

### QMD Index Maintenance

```bash
# List all Notes collections
qmd collection list | grep notes-

# Re-index all collections
qmd update

# Re-embed all (e.g., after model change)
qmd embed -f

# Clean up orphaned data
qmd cleanup
```

### Log Management

Application logs go to stdout/stderr. With launchd, they're in the configured log paths:

```bash
# View recent logs
tail -100 /path/to/brain-notes/logs/stderr.log

# Search for errors
grep ERROR /path/to/brain-notes/logs/stderr.log
```

### Health Checks

```bash
# App is running
curl -s -o /dev/null -w "%{http_code}" http://localhost:5006/
# Expected: 200

# API is responding
curl -s http://localhost:5006/api/auth/me
# Expected: 401 (not logged in) or user JSON

# Database is accessible
sqlite3 notes.db "SELECT COUNT(*) FROM pages"
```

## Troubleshooting

### App won't start

```bash
# Check port in use
lsof -i :5006

# Check Python version
python3.12 --version

# Check dependencies
python3.12 -c "import flask, mcp; print('OK')"
```

### Database locked

SQLite WAL mode should prevent most locking issues. If persistent:

```bash
# Check for WAL files
ls -la notes.db*

# Force checkpoint
sqlite3 notes.db "PRAGMA wal_checkpoint(TRUNCATE)"
```

### QMD indexing fails

```bash
# Check QMD status
qmd status

# Verify path exists
ls -la /path/to/resource

# Check for existing collection with same path
qmd collection list

# Remove conflicting collection
qmd collection remove COLLECTION_NAME
```

### AI features not working

1. Check `llm_config.json` exists and has valid provider config
2. Verify API key is correct
3. Test provider directly:
```bash
curl -X POST https://api.minimax.io/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"MiniMax-M2.1","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

## Upgrading

```bash
cd brain-notes
git pull origin main

# Restart
launchctl stop com.brain.notes-app
launchctl start com.brain.notes-app
```

Database migrations run automatically on startup (`init_db()` handles schema additions with `ALTER TABLE` fallbacks).
