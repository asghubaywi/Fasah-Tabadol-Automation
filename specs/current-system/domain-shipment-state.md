# Domain: Shipment State Machine / آلة حالة الشحنة

**Primary code:** `src/agents/src/shipment.rs`

## Goal / الهدف
Model the lifecycle of a declaration and enforce which status transitions are legal, plus write tracking commands.

## Actors / الأدوار
Result watcher and orchestrator (as the conceptual state owners; the enum/transition logic is a shared library).

## Inputs / Outputs
Input: current + proposed `ShipmentStatus`. Output: boolean transition validity; `track_*.json` tracking command.

## States (proven) / الحالات
`Received, Parsed, Checked, Approved, ApprovedWithConditions, Held, Rejected, Released` — `shipment.rs:19-30`.

## Business rules / قواعد العمل
| ID | Rule | Evidence |
|----|------|----------|
| REQ-SHIP-001 | 8-state enum, snake_case serialized | `shipment.rs:19-30` |
| REQ-SHIP-002 | Legal transitions only (e.g., Received→Parsed; Checked→{Approved,ApprovedWithConditions,Held,Rejected}) | `shipment.rs:34-56` |
| REQ-SHIP-003 | `Rejected` & `Released` are terminal (no transitions) | `shipment.rs:53-54` |
| REQ-SHIP-004 | `write_tracking_command` emits `track_<decl>_<ts>.json` | `shipment.rs:76-101` |

Transition map: Approved→Released; ApprovedWithConditions→{Released,Held}; Held→{Approved,Rejected,Checked}.

## Use cases / scenarios
Validate a Checked→Approved transition (allowed); reject Checked→Released (must pass through Approved); Held can return to Checked (re-evaluation loop).

## Permissions / State changes / Data
Pure logic + optional file write. `TrackingCommand{command_type, declaration_number, status, previous_status, timestamp, metadata}`.

## Integrations
`ShipmentStatus` values are the vocabulary used in outbox tracking commands (though the orchestrator currently writes raw strings, not via this type — see constraint).

## Proven behavior / Tests
Rust-tested: valid transitions, terminal states, held→checked — `shipment.rs:107-131` (pass).

## Known constraints / القيود
- **Not wired into the live orchestrator**: `orchestrator.py` writes tracking-command JSON by hand with its own `status_map` (`orchestrator.py:389-397`) instead of going through this state machine, so **transition validity is not actually enforced at runtime**. The state machine is a well-tested library that the running pipeline bypasses → **GAP-ARCH-003**.
- No persistent per-declaration state store; "current status" is implicit in the latest outbox command.

## Open questions
- Should the orchestrator/result-watcher enforce `can_transition_to` before writing status? (Would prevent illegal jumps; currently unchecked.)
