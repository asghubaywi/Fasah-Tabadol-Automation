# Domain: Declaration Parsing / تحليل البيانات الجمركية

**Primary code:** `src/agents/src/parser.rs` (authoritative) · `src/pipeline/fallback_parser.py` (degraded mode)

## Goal / الهدف
Turn a raw Tabadol export (CSV or JSON) into a validated, structured list of `DeclarationRecord`s plus a content hash, rejecting malformed rows without aborting the whole file.

## Actors / الأدوار
- Orchestrator (calls `fasah-engine parse <file>` as a subprocess) — `orchestrator.py:143`.
- Fallback path (in-process Python) when Rust is unavailable — `orchestrator.py:165`.

## Inputs / المدخلات
- CSV with header row; 10 required columns (order-independent, matched case-insensitively) — `parser.rs:68-91`.
- OR a JSON array of records (`--json` or `.json` extension) — `main.rs:64-71`, `parser.rs:214`.

## Outputs / المخرجات
`ParseResult { total_records, valid_records, invalid_records, records[], errors[], content_hash }` as pretty JSON on stdout — `parser.rs:37-45`.

## Business rules / قواعد العمل (proven)
| Rule | Detail | Evidence |
|------|--------|----------|
| REQ-PARSE-001 | Every one of the 10 headers must be present, else a per-field error is emitted | `parser.rs:69-91` |
| REQ-PARSE-002 | A data row must split into ≥10 fields; else error, row skipped | `parser.rs:101-108` |
| REQ-PARSE-003 | `declared_value_sar` parsed as `f64`, must be ≥ 0 | `parser.rs:111-129` |
| REQ-PARSE-004 | `weight_kg` parsed as `f64`, must be ≥ 0 | `parser.rs:132-142` |
| REQ-PARSE-005 | `hs_code`: only digits + `.`; ≥6 digits after removing dots | `parser.rs:152-162` |
| REQ-PARSE-006 | `origin_country`: exactly 2 ASCII uppercase letters | `parser.rs:165-173` |
| REQ-PARSE-007 | `required_certificates`: `;`-separated, trimmed, empties dropped | `parser.rs:144-149` |
| REQ-PARSE-008 | `content_hash` = SHA-256 of the whole file content | `parser.rs:191-193` |
| REQ-PARSE-010 | Invalid rows are skipped (via `continue`); valid rows still collected | `parser.rs:94-188` |

## Use cases / حالات الاستخدام
1. Parse a clean CSV → all rows valid.
2. Parse a CSV with some bad rows → valid rows returned, `errors[]` populated, `invalid_records` counted.
3. Parse a JSON array (e.g., re-feeding engine output).

## Main scenario / السيناريو الأساسي
Header validated → each non-empty data row validated field-by-field → valid `DeclarationRecord` pushed with `source_line` → hash computed → counts derived.

## Exception scenarios / السيناريوهات الاستثنائية
- Missing header field → error at line 1, but rows still processed (`parser.rs:83-91`).
- Bad numeric/HS/country field → that row error-skipped, others continue.

## Failure scenarios / حالات الفشل
- Empty file → `Err("empty file")` (Rust) — `parser.rs:63-65`.
- **Fallback divergence / bug:** `fallback_parser.parse_csv` computes the SHA-256 **before** the read try/except, so a **missing file raises `FileNotFoundError`** instead of returning an error result — `fallback_parser.py:149` vs `155-184`. This is **GAP-BUG-001** (test `test_parse_nonexistent_file` FAILS).

## Permissions / الصلاحيات
None; pure computation. Read-only on the input file.

## State changes / تغييرات الحالة
None (pure). No files written by the parser itself.

## Data / البيانات
`DeclarationRecord` fields — `parser.rs:9-34`: declaration_number, hs_code, importer_name (Arabic-safe), importer_cr, origin_country, declared_value_sar, weight_kg, port_of_entry, declaration_date (ISO string, **not validated**), required_certificates[], source_line.

## Integrations / التكاملات
Invoked as CLI subprocess by orchestrator; output consumed by compliance stage.

## Proven behavior / السلوك المثبت
`fasah-engine parse examples/sample_declarations.csv` → `total 5, valid 5, invalid 0` (`06-baseline-verification.md`). Rust unit tests cover valid CSV, invalid country, negative value.

## Tests / الاختبارات
- Rust: `parser::tests::test_parse_valid_csv`, `test_parse_invalid_country_code`, `test_parse_negative_value` — `parser.rs:234-279` (pass).
- Python: `TestFallbackParser::*` — `test_dropout.py:70-127` (5 pass, `test_parse_nonexistent_file` FAILS).

## Known constraints / القيود المعروفة
- CSV split is naive on `,` — **no quoted-field / embedded-comma support** in the Rust parser (`parser.rs:100`). The Python fallback uses `csv.DictReader` (quote-aware), so the two parsers can disagree on quoted CSVs → **GAP-DRIFT-002**.
- `declaration_date` is stored but never validated as a real date.
- Rust requires positional field order for values (indexes `fields[5]`, `fields[6]`, etc.) even though headers are matched by name — a column-reordered CSV would misparse in Rust but not in Python. → drift risk.

## Open questions / الأسئلة غير المحسومة
- Should HS max length (10) be enforced? Rust only checks the lower bound (≥6). (Docs say 6–10.)
- Is column-order independence a real requirement, or is positional parsing acceptable? (Human decision.)
