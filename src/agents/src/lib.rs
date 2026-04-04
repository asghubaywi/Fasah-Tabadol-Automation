//! fasah-engine — Fasah/Tabadol Customs Clearance Engine
//!
//! Standalone Rust library exposing CSV parsing and compliance checking
//! for Saudi customs declarations. Used by the Python orchestrator via
//! the `fasah-engine` CLI binary.

pub mod compliance;
pub mod dispatcher;
pub mod idempotency;
pub mod parser;
pub mod result_watcher;
pub mod shipment;
pub mod stability;
