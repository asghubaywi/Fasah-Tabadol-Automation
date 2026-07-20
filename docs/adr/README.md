# Architecture Decision Records / سجل القرارات المعمارية

These ADRs were **reverse-engineered from the codebase** during discovery. No ADRs existed before. Because none were documented by a human, every record here has status **`Inferred — Requires Human Confirmation`** unless/until a maintainer ratifies it. An inferred decision is **not** an approved human decision.

Template (each ADR): Title · Status · Context · Decision · Evidence from the project · Alternatives · Pros · Cons · Risks · Revisit conditions.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-hybrid-rust-python.md) | Hybrid Rust engine + Python orchestration | Inferred — Requires Human Confirmation |
| [0002](0002-file-based-message-bus.md) | Filesystem as the message bus (no DB/queue) | Inferred — Requires Human Confirmation |
| [0003](0003-yaml-configurable-rules.md) | YAML-configurable compliance rules | Inferred — Requires Human Confirmation |
| [0004](0004-python-fallback-degradation.md) | Dual-implementation Python fallbacks for degradation | Inferred — Requires Human Confirmation |
| [0005](0005-circuit-breaker-checkpoint.md) | Circuit breaker + checkpoint/resume resilience | Inferred — Requires Human Confirmation |
| [0006](0006-playwright-read-only-gates.md) | Playwright browser worker, read-only + security gates | Inferred — Requires Human Confirmation |
| [0007](0007-append-only-jsonl-audit.md) | Append-only JSONL audit with buffer fallback | Inferred — Requires Human Confirmation |
| [0008](0008-atomic-writes-idempotency.md) | Atomic writes + SHA-256 idempotency | Inferred — Requires Human Confirmation |
| [0009](0009-extracted-from-zeroclaw.md) | Extraction from the parent "ZeroClaw" system | Inferred — Requires Human Confirmation |
| [0010](0010-json-schema-contracts.md) | JSON-Schema file contracts (advisory) | Inferred — Requires Human Confirmation |
