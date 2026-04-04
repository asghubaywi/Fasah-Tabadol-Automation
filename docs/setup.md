# Setup Guide / دليل الإعداد

## Prerequisites / المتطلبات المسبقة

| Tool | Version | Notes |
|------|---------|-------|
| Rust | 1.75+ | [rustup.rs](https://rustup.rs) |
| Python | 3.11+ | With pip |
| Playwright | 1.40+ | Via pip |
| Git | Any | For version control |

## Quick Start / البداية السريعة

### 1. Clone & Build

```bash
git clone https://github.com/asghubaywi/Fasah-Tabadol-Automation.git
cd Fasah-Tabadol-Automation

# Build the Rust engine
cargo build --release

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

### 2. Configure

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your Fasah portal URL and credentials
# At minimum, set FASAH_BASE_URL
```

### 3. Test with Sample Data

```bash
# Parse the sample CSV
./target/release/fasah-engine parse examples/sample_declarations.csv

# Check compliance (expects approve/hold/reject mix)
./target/release/fasah-engine parse examples/sample_declarations.csv > /tmp/parsed.json
./target/release/fasah-engine check /tmp/parsed.json

# Run tests
cargo test
```

### 4. Run the Pipeline

```bash
# Terminal 1: Start the orchestrator
python src/pipeline/orchestrator.py

# Terminal 2 (optional): Start the browser worker
ZC_ENV=dev python src/browser/worker.py

# Drop a CSV into the inbox
cp examples/sample_declarations.csv workspace/inbox/
```

## Configuration Reference / مرجع الإعداد

### Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `AGENT_CONFIG` | `config/agent_fasah.yaml` | No | Agent config file path |
| `FASAH_RULES` | `config/fasah_rules.yaml` | No | Compliance rules file |
| `FASAH_BASE_URL` | `https://fasah.gov.sa` | In prod | Fasah portal URL |
| `FASAH_ENGINE_BIN` | `target/release/fasah-engine` | No | Rust binary path |
| `ZC_ENV` | `dev` | No | `dev` or `prod` |
| `ZC_INBOX` | `workspace/outbox/browser_tasks` | No | Browser worker inbox |
| `ZC_OUTBOX` | `workspace/outbox/browser_results` | No | Browser worker outbox |
| `ZC_POLL_INTERVAL` | `3` | No | Worker poll interval (seconds) |
| `AGENT_BROWSER_ALLOWED_DOMAINS` | _(none)_ | In prod | Domain allowlist |
| `RUST_LOG` | `info` | No | Rust log level |

### agent_fasah.yaml Fields

| Field | Default | Description |
|-------|---------|-------------|
| `inbox_dir` | `workspace/inbox` | Where to pick up declaration files |
| `outbox_dir` | `workspace/outbox` | Where to write compliance outputs |
| `audit_dir` | `workspace/audit` | Where to write daily JSONL audit logs |
| `poll_interval_secs` | `15` | Inbox scan frequency |

## CSV Format / صيغة ملف CSV

Required headers (order-independent):

```
declaration_number, hs_code, importer_name, importer_cr, origin_country,
declared_value_sar, weight_kg, port_of_entry, declaration_date, required_certificates
```

**Field details:**
- `hs_code`: 6-10 digit numeric, dots allowed (e.g., `8471.30.00`)
- `origin_country`: ISO 3166-1 alpha-2, 2 uppercase letters (e.g., `CN`, `SA`)
- `declared_value_sar`: Non-negative float, in Saudi Riyal
- `required_certificates`: Semicolon-separated (e.g., `SASO;CoC`)
- `declaration_date`: ISO 8601 date (e.g., `2026-02-15`)

## Production Deployment / النشر في الإنتاج

### Security Checklist

- [ ] Set `ZC_ENV=prod`
- [ ] Set `AGENT_BROWSER_ALLOWED_DOMAINS=*.fasah.gov.sa,fasah.gov.sa`
- [ ] Set `AGENT_BROWSER_ENCRYPTION_KEY` (base64 key)
- [ ] Set `FASAH_BASE_URL` to the production Fasah URL
- [ ] Store credentials in a secrets manager (not in `.env`)
- [ ] Run orchestrator and browser worker as separate system users
- [ ] Mount `workspace/` on a persistent volume
- [ ] Set up log rotation for `workspace/audit/*.jsonl`

### Using Docker Compose

```bash
# Set FASAH_BASE_URL and ZC_ENV=prod in .env
docker compose up -d

# Check logs
docker compose logs -f orchestrator
docker compose logs -f browser-worker
```

## Troubleshooting / استكشاف الأخطاء

### Binary not found
```
fasah-engine binary not found at target/release/fasah-engine
```
**Fix:** Run `cargo build --release`

### Playwright browser not installed
```
Error: Executable doesn't exist...
```
**Fix:** Run `playwright install chromium`

### Auth failure on Fasah portal
The browser worker returns `AUTH_FAIL` when:
- No session state exists yet (first run)
- Session has expired

**Fix:** Manually navigate to Fasah, log in, then copy the session storage to `workspace/state/sessions/fasah_agent/state.json`.

### Rule changes
Edit `config/fasah_rules.yaml` — no rebuild needed. The orchestrator reads it fresh each poll cycle.
