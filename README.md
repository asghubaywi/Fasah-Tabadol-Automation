# Fasah-Tabadol-Automation

**أتمتة التخليص الجمركي بين منصة تبادل وبوابة فسح**

**Automated customs clearance pipeline between the Tabadol trade platform and the Fasah clearance portal.**

---

## 📚 التوثيق التفصيلي / Spec-Driven Documentation

The authoritative, evidence-based specification lives under [`docs/spec-driven/`](docs/spec-driven/) and [`specs/`](specs/):
constitution ([`.specify/memory/constitution.md`](.specify/memory/constitution.md)), current-system specs ([`specs/current-system/`](specs/current-system/)),
as-built architecture, ADRs ([`docs/adr/`](docs/adr/)), gap analysis, traceability, and the phased plan.
**AI agents must read [`AGENTS.md`](AGENTS.md) + the constitution before changing code.**

Notes that supersede older prose in this README: the pipeline has a full **resilience layer** (circuit breaker, Python
fallbacks, checkpoint/resume, degradation manager, resilient audit); the browser worker enforces **security gates 9–13**
(inherited numbering) and is **POSIX-only** (`fcntl`).

---

## ما هذا المشروع؟ / What is this?

يقوم هذا المشروع بأتمتة دورة التخليص الجمركي من البداية إلى النهاية:
يأخذ ملفات CSV التي تصدرها منصة **تبادل**، يفحص كل بيان جمركي وفق قواعد الامتثال لهيئة الزكاة والجمارك (ZATCA) والـ SFDA والـ SASO، ثم يُدخِل النتائج تلقائيًا إلى بوابة **فسح** عبر متصفح Playwright.

This project automates the end-to-end customs clearance cycle: it ingests CSV exports from the **Tabadol** trade platform, evaluates each customs declaration against ZATCA / SFDA / SASO compliance rules, and drives the **Fasah** clearance portal automatically using a Playwright browser worker.

---

## خط المعالجة / Pipeline Flow

```
ملف CSV من تبادل / Tabadol CSV Export
           │
           ▼
    [workspace/inbox/]
           │
           ▼
    orchestrator.py  ──► fasah-engine parse   ──► بيانات منظَّمة / Parsed Records
           │
           ├──► fasah-engine check  ──► قرار الامتثال / Compliance Verdict
           │
           ├── موافقة / مرفوض ──────────────────► outbox/track_*.json
           │   APPROVE / REJECT
           │
           └── تعليق / تصعيد ─────────────────► outbox/browser_tasks/*.json
               HOLD / ESCALATE                            │
                                                          ▼
                                               browser/worker.py  (Playwright)
                                                          │
                                                          ▼
                                               بوابة فسح / Fasah Portal
                                                          │
                                                          ▼
                                               outbox/browser_results/<id>/bundle.json
                                                          │
                                                          ▼
                                               fasah-engine watch ──► outbox/track_*.json
```

### قرارات الامتثال / Compliance Verdicts

| القرار / Verdict | الإجراء / Action |
|-----------------|-----------------|
| `approve` | تسجيل مباشر في الصادر / Direct outbox write |
| `approve_with_conditions` | تسجيل مباشر | Direct outbox write |
| `reject` / `reject_sanctioned` | رفض / Rejection record |
| `hold_pending_certificates` | إرسال للمتصفح / Browser task |
| `escalate_high_value` | إرسال للمتصفح / Browser task |
| `mandate_inspection` | أمر تعليق / Hold command |

---

## المتطلبات / Prerequisites

| أداة / Tool | الإصدار / Version | ملاحظات / Notes |
|-------------|-------------------|-----------------|
| Rust | 1.75+ | [rustup.rs](https://rustup.rs) |
| Python | 3.11+ | مع pip / With pip |
| Playwright | 1.40+ | عبر pip / Via pip |
| Git | أي إصدار / Any | للتحكم بالإصدارات / Version control |

---

## التثبيت السريع / Quick Start

```bash
# 1. استنسخ المستودع / Clone the repo
git clone https://github.com/asghubaywi/Fasah-Tabadol-Automation.git
cd Fasah-Tabadol-Automation

# 2. ابنِ محرك Rust / Build the Rust engine
cargo build --release

# 3. ثبِّت متطلبات Python / Install Python dependencies
pip install -r requirements.txt
playwright install chromium

# 4. انسخ ملف الإعداد / Copy config
cp .env.example .env
# عدِّل .env وضع FASAH_BASE_URL على الأقل / Edit .env — set FASAH_BASE_URL at minimum

# 5. اختبر على البيانات النموذجية / Test with sample data
./target/release/fasah-engine parse examples/sample_declarations.csv
```

---

## تشغيل خط المعالجة / Running the Pipeline

```bash
# الطرفية الأولى: المُنسِّق / Terminal 1: Orchestrator
python src/pipeline/orchestrator.py

# الطرفية الثانية (اختياري): عامل المتصفح / Terminal 2 (optional): Browser worker
ZC_ENV=dev python src/browser/worker.py

# أسقِط ملف CSV في صندوق الوارد / Drop a CSV into the inbox
cp examples/sample_declarations.csv workspace/inbox/
```

---

## هيكل الملفات / Project Layout

```
Fasah-Tabadol-Automation/
├── src/
│   ├── agents/              # محرك Rust (CSV + الامتثال) / Rust engine (CSV + compliance)
│   │   └── src/
│   │       ├── main.rs      # نقطة دخول CLI / CLI entry point
│   │       ├── parser.rs    # محلل CSV → DeclarationRecord[]
│   │       ├── compliance.rs# قواعد الامتثال / Compliance rules + checker
│   │       ├── dispatcher.rs# مُرسِل مهام المتصفح / Browser task dispatcher
│   │       ├── result_watcher.rs # معالج نتائج المتصفح / Browser result processor
│   │       ├── shipment.rs  # آلة حالة الشحنة / Shipment state machine
│   │       ├── idempotency.rs # منع التكرار / Duplicate prevention
│   │       └── stability.rs # استقرار الملفات / File stability tracker
│   ├── pipeline/
│   │   └── orchestrator.py  # حلقة الأحداث الرئيسية / Main event loop (Python)
│   ├── browser/
│   │   └── worker.py        # أتمتة Playwright / Playwright browser automation
│   └── utils/
│       └── audit.py         # مسجِّل المراجعة JSONL / JSONL audit logger
├── config/
│   ├── agent_fasah.yaml     # إعداد العميل / Agent runtime config
│   └── fasah_rules.yaml     # قواعد الامتثال (قابلة للتعديل) / Compliance rules (no rebuild)
├── schemas/
│   ├── fasah_task.schema.json   # مخطط مهمة المتصفح / Browser task envelope schema
│   └── fasah_bundle.schema.json # مخطط حزمة النتيجة / Result bundle schema
├── examples/
│   └── sample_declarations.csv  # بيانات نموذجية / Sample data (5 declarations)
├── workspace/               # بيانات وقت التشغيل / Runtime data (git-ignored)
│   ├── inbox/               # أسقط CSV هنا / Drop CSV files here
│   ├── outbox/              # نتائج الامتثال / Compliance outputs
│   ├── audit/               # سجلات JSONL / JSONL audit logs
│   └── state/               # جلسات المتصفح / Browser sessions
├── docs/
│   ├── architecture.md      # وثيقة المعمارية / Architecture document
│   └── setup.md             # دليل الإعداد التفصيلي / Detailed setup guide
└── .env.example             # قالب متغيرات البيئة / Environment variable template
```

---

## إعداد الامتثال / Compliance Configuration

تُحدِّد `config/fasah_rules.yaml` قواعد الامتثال — **لا يلزم إعادة البناء** عند تعديلها:

`config/fasah_rules.yaml` defines all compliance rules — **no rebuild required** on change:

```yaml
# رموز HS المحظورة / Banned HS prefixes (auto-reject)
banned_hs_prefixes:
  - "9301"   # أسلحة عسكرية / Military weapons
  - "9302"   # مسدسات / Pistols

# حد القيمة العالية (ريال سعودي) / High-value threshold (SAR)
high_value_threshold_sar: 500000.0

# متطلبات الشهادات / Certificate requirements
certificate_requirements:
  "84": [SASO]      # إلكترونيات / Electronics
  "04": [SFDA, Halal]  # منتجات الألبان / Dairy
```

---

## أوامر CLI / CLI Commands

```bash
# تحليل CSV / Parse CSV
./target/release/fasah-engine parse examples/sample_declarations.csv

# فحص الامتثال / Check compliance
./target/release/fasah-engine parse file.csv > /tmp/records.json
./target/release/fasah-engine check /tmp/records.json --rules config/fasah_rules.yaml

# مراقبة نتائج المتصفح / Watch browser results
./target/release/fasah-engine watch workspace/outbox/browser_results workspace/outbox
```

---

## متغيرات البيئة / Environment Variables

| المتغير / Variable | القيمة الافتراضية / Default | الوصف / Description |
|-------------------|---------------------------|---------------------|
| `FASAH_BASE_URL` | `https://fasah.gov.sa` | رابط بوابة فسح / Fasah portal URL |
| `ZC_ENV` | `dev` | `dev` أو / or `prod` |
| `ZC_INBOX` | `workspace/outbox/browser_tasks` | صندوق وارد المتصفح / Browser worker inbox |
| `ZC_OUTBOX` | `workspace/outbox/browser_results` | صندوق صادر المتصفح / Browser worker outbox |
| `AGENT_BROWSER_ALLOWED_DOMAINS` | _(مطلوب في الإنتاج / prod required)_ | قائمة النطاقات المسموحة / Domain allowlist |
| `RUST_LOG` | `info` | مستوى تسجيل Rust / Rust log level |

للتفاصيل الكاملة راجع [`docs/setup.md`](docs/setup.md).

---

## الاختبارات / Tests

```bash
# اختبارات Rust / Rust tests
cargo test

# اختبار محدد / Specific test
cargo test -p fasah-engine

# فحص التنسيق / Format check
cargo fmt --all -- --check

# فحص الكود / Lint
cargo clippy -- -D warnings
```

---

## سجل المراجعة / Audit Trail

تُكتَب جميع أحداث العميل في `workspace/audit/agent_fasah_YYYY-MM-DD.jsonl`:

All agent events are written to `workspace/audit/agent_fasah_YYYY-MM-DD.jsonl`:

```json
{"ts": "2026-04-05T10:00:00Z", "agent_id": "agent_fasah", "action": "AgentStarted"}
{"ts": "2026-04-05T10:00:01Z", "action": "ToolCompleted", "tool": "fasah_declaration_parse", "outcome": "success"}
{"ts": "2026-04-05T10:00:02Z", "action": "ToolCompleted", "tool": "fasah_compliance_check", "verdict": "approve"}
{"ts": "2026-04-05T10:00:03Z", "action": "ToolInvoked", "tool": "browser_dispatch", "task_id": "abc123"}
```

---

## النشر في الإنتاج / Production Deployment

```bash
# عبر Docker Compose / Via Docker Compose
docker compose up -d

# راجع السجلات / Check logs
docker compose logs -f orchestrator
docker compose logs -f browser-worker
```

**قائمة فحص الأمان / Security Checklist:**
- [ ] `ZC_ENV=prod`
- [ ] `AGENT_BROWSER_ALLOWED_DOMAINS=*.fasah.gov.sa,fasah.gov.sa`
- [ ] `AGENT_BROWSER_ENCRYPTION_KEY` مضبوط / set (base64)
- [ ] بيانات اعتماد في مدير أسرار / Credentials in secrets manager (not `.env`)
- [ ] تدوير سجلات المراجعة / Audit log rotation configured

للتفاصيل راجع [`docs/setup.md`](docs/setup.md#production-deployment--النشر-في-الإنتاج).

---

## المساهمة / Contributing

نرحب بالمساهمات! راجع [CONTRIBUTING.md](CONTRIBUTING.md) للتفاصيل.

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## الترخيص / License

MIT License — Copyright (c) 2024-2026 Aziz asghubaywi. See [LICENSE](LICENSE).
