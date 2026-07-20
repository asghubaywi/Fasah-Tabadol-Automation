# CLAUDE.md — Guidance for Claude Code

**Start here:** read **[`AGENTS.md`](AGENTS.md)** in full — it holds the binding rules for all AI agents on this repo, and they apply to you without exception. This file adds Claude-Code-specific guidance on top.

## Before you touch anything
1. Read **`.specify/memory/constitution.md`** (highest authority).
2. Read the domain spec in **`specs/current-system/`** for the area you're changing.
3. Skim **`docs/spec-driven/04-gap-analysis.md`** so you don't "rediscover" or accidentally step on a known issue.

## The rules in one screen (full text in AGENTS.md)
1. Constitution first. 2. Spec before code. 3. Only build what an approved spec/task defines. 4. Don't expand scope. 5. No contract change without an ADR + human approval. 6. Run the gates (below). 7. Update traceability. 8. Update the spec when behavior changes. 9. Record assumptions. 10. Stop at human-decision points (GAP-HUM-*). 11. No success claims without real output. 12. Say plainly what was and wasn't done.

## Gates to run (paste real output)
```bash
# Rust
cargo test
cargo fmt --all -- --check
cargo clippy -- -D warnings
# Python
python -m pytest tests/
ruff check src/
```
Don't regress `docs/spec-driven/06-baseline-verification.md`. Note: three gates (fmt, clippy, ruff) are **currently red** by pre-existing defects (GAP-QUAL-001/002/003) and two `pytest` tests fail (GAP-BUG-001/002). If your task isn't one of those fixes, make sure you don't add *new* failures; if it is, drive that gate to green.

## Claude-specific etiquette
- **Smallest reviewable diff** with a test or a documented verification. Prefer `Edit` over rewrites.
- **Use the plan/tasks docs** (`specs/project-evolution/tasks.md`) as your backlog; the recommended first five tasks are listed at the bottom of that file.
- **This is customs-clearance software.** When in doubt about compliance semantics, portal actions, verdict/state changes, or anything that could mis-clear or lose a declaration → **ask via a question, don't guess** (Constitution P10). These are the P10/GAP-HUM items.
- **Rust ⇄ Python parity:** if you change `compliance.rs`/`parser.rs`, also check `fallback_compliance.py`/`fallback_parser.py`, and keep/add equivalence tests (Constitution P14, GAP-DRIFT-001/002).
- **Never** rewrite audit logs, commit secrets, or add browser *write* actions to the Fasah portal.
- **Do not** put the model identifier or internal tooling notes into commits, PRs, or code — keep those to chat.

## When you finish a task, report
- Exactly which commands you ran and their results (pass/fail counts).
- What behavior changed vs. what stayed the same.
- Any assumption you made and any human-decision item you hit.
- Spec + traceability updates you made.

## Fast index
Constitution → `.specify/memory/constitution.md` · Specs → `specs/current-system/` · Architecture → `docs/spec-driven/03-current-architecture.md` · ADRs → `docs/adr/` · Gaps → `docs/spec-driven/04-gap-analysis.md` · Traceability → `docs/spec-driven/05-requirements-traceability.md` · Baseline → `docs/spec-driven/06-baseline-verification.md` · Plan/Tasks → `specs/project-evolution/`.
