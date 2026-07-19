# AGENTS.md — Instructions for AI Agents / تعليمات وكلاء الذكاء الاصطناعي

This repository is spec-driven. Any AI agent (Claude Code, Codex, or other) MUST follow these rules. They are binding, derived from the project's constitution and real state.

## 0. Read these first, in order / اقرأ أولًا
1. **`.specify/memory/constitution.md`** — the highest-authority engineering rules. Read it before touching code.
2. The **spec for the area you will change** in `specs/current-system/` (see its `README.md` index).
3. `docs/spec-driven/03-current-architecture.md` (how it really fits together) and `04-gap-analysis.md` (known issues — don't rediscover or "fix" them blindly).

## The 12 rules / القواعد الاثنتا عشرة

1. **Read the constitution first.** Every session, before editing.
2. **Read the related spec before modifying code.** If no spec exists for what you're changing, write/extend the spec first.
3. **Do not implement anything not in an approved spec or task** (`specs/project-evolution/tasks.md`). No unrequested features.
4. **Do not expand scope automatically.** Stay within the task. Note adjacent issues; don't silently fix them.
5. **Do not change public contracts without an ADR.** Contracts = `schemas/*.json`, the `ComplianceAction` verdict taxonomy (`compliance.rs`), the shipment state machine (`shipment.rs`), CLI argv shapes, and file formats in `workspace/`. Add an ADR in `docs/adr/` and get human approval first.
6. **Run the appropriate tests.** Rust: `cargo test`, `cargo fmt --all -- --check`, `cargo clippy -- -D warnings`. Python: `pytest tests/`, `ruff check src/`. Don't worsen the current baseline (`docs/spec-driven/06-baseline-verification.md`).
7. **Update the traceability matrix** (`docs/spec-driven/05-requirements-traceability.md`) whenever you change what a requirement does or how it's tested.
8. **Update the spec if behavior changes.** The spec must always match reality (Constitution P3).
9. **Record assumptions** explicitly in your output and in the relevant doc — never bury a guess in code.
10. **Stop at human-decision points.** For anything in the human-decision register (`04-gap-analysis.md` GAP-HUM-*) or Constitution P10 (compliance semantics, portal write actions, verdict taxonomy/state-machine changes, security gates, anything that could mis-clear or lose a declaration), **ask a human** — do not decide.
11. **Never claim success without real run results.** No "done/ready/secure/verified" without command output. Paste what you actually ran.
12. **State clearly what was done and what was not.** Separate current state, target state, gap, proposed work, and work actually performed.

## Project-specific hard constraints / قيود خاصة بالمشروع
- **This system clears customs declarations.** A wrong `approve` or a lost/mis-audited declaration has legal consequences. Prefer fail-safe/fail-closed (Constitution P6).
- **Rust and Python compliance/parse logic must stay equivalent** (Constitution P14). If you touch one, touch the other and add/keep equivalence tests. Known divergences are logged as GAP-DRIFT-001/002 — align *toward the canonical decision* (GAP-HUM-001), never widen the gap.
- **The browser worker is read-only** on the Fasah portal (`download`/`upload` blocked). Do not add write/submit actions without GAP-HUM-002 (legal basis) + an ADR + human approval.
- **Never rewrite audit history** (`workspace/audit/*.jsonl`) — append only (Constitution P5).
- **No secrets in the repo** — env/secret-manager only (Constitution P7).
- **Atomic writes** (tmp→fsync→rename) for anything durable (Constitution P1).
- The browser worker is **POSIX-only** (`fcntl`); keep that in mind for portability changes.

## How to make a change (workflow)
1. Confirm a task exists in `specs/project-evolution/tasks.md` (or create/spec one and get approval).
2. Read the constitution + the domain spec + the relevant gap entries.
3. Make the **smallest reviewable change** with a test or a documented verification.
4. Run the gates in rule 6. Paste results.
5. Update the spec + traceability matrix if behavior/coverage changed.
6. In your summary: state exactly what ran, what passed/failed, assumptions, and any human-decision item you hit.

## Where things are / خريطة سريعة
| Need | Path |
|------|------|
| Constitution | `.specify/memory/constitution.md` |
| Current specs (by domain) | `specs/current-system/` |
| Architecture (as-built) | `docs/spec-driven/03-current-architecture.md` |
| ADRs | `docs/adr/` |
| Known issues + priorities | `docs/spec-driven/04-gap-analysis.md` |
| Traceability | `docs/spec-driven/05-requirements-traceability.md` |
| Baseline (real test results) | `docs/spec-driven/06-baseline-verification.md` |
| Plan & tasks | `specs/project-evolution/` |
| Rust engine | `src/agents/src/` |
| Python orchestration/browser/utils | `src/pipeline/`, `src/browser/`, `src/utils/` |

## Current baseline reality (2026-07-19) — don't be surprised
- `cargo test` ✅ 19/19 · `pytest` ⚠ 52/54 (2 known failures: GAP-BUG-001/002).
- `cargo fmt`/`cargo clippy`/`ruff` all currently **fail** (GAP-QUAL-001/002/003) — the first cleanup tasks fix these.
- CI is disconnected (branch `main` vs default `master`, GAP-CI-001); Docker build is broken (no `Dockerfile`, GAP-DEPLOY-001).
- The browser worker has **no tests** (GAP-TEST-001). Treat it with extra care.
