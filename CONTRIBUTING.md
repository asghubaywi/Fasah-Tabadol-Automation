# Contributing / دليل المساهمة

شكرًا لاهتمامك بالمساهمة في هذا المشروع!

Thank you for your interest in contributing to this project!

---

## قبل البدء / Before You Start

1. **افتح issue أولًا** لمناقشة التغييرات الكبيرة قبل تنفيذها.
   **Open an issue first** to discuss major changes before implementing.

2. **للإصلاحات الصغيرة** (typos، توثيق) يمكنك فتح PR مباشرة.
   **For small fixes** (typos, docs) you can open a PR directly.

---

## إعداد بيئة التطوير / Development Setup

```bash
git clone https://github.com/asghubaywi/Fasah-Tabadol-Automation.git
cd Fasah-Tabadol-Automation

# Rust
cargo build
cargo test

# Python
pip install -r requirements.txt
pip install ruff  # للفحص / for linting
playwright install chromium
```

---

## معايير الكود / Code Standards

### Rust
```bash
cargo fmt --all              # تنسيق تلقائي / auto-format
cargo clippy -- -D warnings  # يجب أن يمر بدون تحذيرات / must pass clean
cargo test                   # يجب أن تنجح جميع الاختبارات / all tests must pass
```

### Python
```bash
ruff check src/              # فحص الكود / lint
ruff format src/             # تنسيق / format
```

---

## رسائل Commit / Commit Messages

نتبع [Conventional Commits](https://www.conventionalcommits.org/):

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(compliance): add new certificate requirement for chapter 26
fix(parser): handle BOM in UTF-8 CSV files
docs(setup): clarify production deployment steps
refactor(worker): extract session management into helper
test(compliance): add edge cases for high-value threshold
```

**الأنواع المقبولة / Accepted types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

---

## سير عمل PR / PR Workflow

1. Fork المستودع / Fork the repo
2. أنشئ فرعًا / Create a branch: `feat/<scope>` أو `fix/<scope>`
3. أجرِ تغييراتك مع اختبارات / Make changes with tests
4. تأكد من نجاح CI: `cargo test && cargo clippy -- -D warnings`
5. افتح PR مع وصف واضح / Open PR with a clear description

---

## قواعد الامتثال / Compliance Rules

تعديلات `config/fasah_rules.yaml` لا تتطلب إعادة بناء — لكن تأكد من:

Changes to `config/fasah_rules.yaml` don't need a rebuild — but ensure:
- رموز HS صحيحة (2-10 أرقام) / Valid HS codes (2-10 digits)
- رموز الدول ISO 3166-1 alpha-2 صحيحة / Valid ISO 3166-1 alpha-2 country codes
- أسماء الشهادات متسقة مع CSV الوارد / Certificate names consistent with input CSV

---

## الإبلاغ عن مشكلة / Reporting Issues

استخدم [قوالب GitHub Issues](https://github.com/asghubaywi/Fasah-Tabadol-Automation/issues/new/choose) وضمِّن:

Use the [GitHub Issue templates](https://github.com/asghubaywi/Fasah-Tabadol-Automation/issues/new/choose) and include:

- نسخة Rust / Python / Playwright
- خطوات إعادة الإنتاج / Steps to reproduce
- المخرجات المتوقعة والفعلية / Expected vs actual output
- محتوى `workspace/audit/` ذو الصلة (بعد إزالة البيانات الحساسة)
  Relevant `workspace/audit/` content (after redacting sensitive data)

---

## الترخيص / License

بمساهمتك توافق على ترخيص MIT المذكور في [LICENSE](LICENSE).

By contributing you agree to the MIT License in [LICENSE](LICENSE).
