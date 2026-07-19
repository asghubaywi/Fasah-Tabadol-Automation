# ADR 0009 — Extraction from the parent "ZeroClaw" system

**Status:** Inferred — Requires Human Confirmation

## Context
Several artifacts reference a larger prior system named "ZeroClaw," and the security gates are numbered 9–13 (implying 1–8 lived elsewhere).

## Decision (reconstructed)
This repository was carved out as a **standalone** extraction of the Fasah/Tabadol slice of ZeroClaw, keeping the browser worker's later gates and its schema/session conventions.

## Evidence from the project
- `worker.py:69-110` gates 9–13; `docs/architecture.md:100-111` "13 security gates" (really 9–13).
- Schema `$id`: `https://zeroclaw.gov/schemas/...` (`schemas/*.json`).
- Session default `/var/lib/zeroclaw/fasah/state/sessions`; UA `ZeroClaw-FasahWorker` (`worker.py:58-60,417`).
- `audit.py` docstring: "Replaces the ZeroClaw core_audit crate."
- `23a3754 feat: initial ... standalone project`.

## Alternatives
- Rebuild clean-room (loses battle-tested gates); keep inside the monorepo.

## Pros
- Inherits mature security gates and evidence conventions.

## Cons / Risks
- **Provenance leftovers** confuse readers: gate numbering with no 1–8, `zeroclaw.gov` schema IDs, `/var/lib/zeroclaw` paths — none are wrong functionally, but they look like dead references.
- Gates 1–8 (whatever they enforced) are **absent** — unknown security delta vs the parent.

## Revisit conditions
Human decision: either renumber/rebrand to this project's identity and document the intended gate set, or explicitly declare gates 1–8 out of scope with justification.
