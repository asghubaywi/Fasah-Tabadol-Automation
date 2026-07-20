# ADR 0003 — YAML-configurable compliance rules

**Status:** Inferred — Requires Human Confirmation

## Context
Customs/SFDA/SASO regulations change; recompiling Rust to change a banned HS code or threshold is operationally unacceptable.

## Decision
Externalize all compliance parameters (banned HS prefixes, sanctioned countries, thresholds, certificate requirements) into `config/fasah_rules.yaml`, loaded fresh by `fasah-engine check --rules` each run; built-in defaults exist as a safety net.

## Evidence from the project
- `compliance.rs:16-87` (`ComplianceRules` + defaults); `main.rs:93-101` loads YAML.
- `config/fasah_rules.yaml`; README "no rebuild required" (`README.md:156-173`).

## Alternatives
- Hardcode rules in Rust; use a database-backed rules service.

## Pros
- Ops can change policy without a build; defaults prevent a totally-unconfigured system.

## Cons / Risks
- No schema validation of the YAML; a malformed rules file makes Rust `check` **error out** while the Python fallback silently uses different defaults (GAP-DRIFT-001 #5).
- No versioning of rules against regulation effective-dates; no audit of *which* rule set judged a declaration.
- `sanctioned_countries` ships **empty** — sanction screening is off until configured.

## Revisit conditions
Add rules-file schema validation, rule-set versioning/hash in the audit, and a policy for default-vs-file precedence before relying on this in production.
