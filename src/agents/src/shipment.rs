//! Fasah Shipment Status Tracking
//!
//! Tracks the lifecycle of customs declarations through processing stages.
//!
//! # Stages
//!
//! 1. `received`   — declaration file ingested
//! 2. `parsed`     — declaration successfully parsed
//! 3. `checked`    — compliance check completed
//! 4. `approved`   — declaration approved (or approved_with_conditions)
//! 5. `held`       — pending certificates or review
//! 6. `rejected`   — failed compliance
//! 7. `released`   — goods cleared for release

use chrono::Utc;
use serde::{Deserialize, Serialize};

/// Shipment processing stages.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ShipmentStatus {
    Received,
    Parsed,
    Checked,
    Approved,
    ApprovedWithConditions,
    Held,
    Rejected,
    Released,
}

impl ShipmentStatus {
    /// Valid transitions from this status.
    pub fn valid_transitions(&self) -> Vec<ShipmentStatus> {
        match self {
            ShipmentStatus::Received => vec![ShipmentStatus::Parsed],
            ShipmentStatus::Parsed => vec![ShipmentStatus::Checked],
            ShipmentStatus::Checked => vec![
                ShipmentStatus::Approved,
                ShipmentStatus::ApprovedWithConditions,
                ShipmentStatus::Held,
                ShipmentStatus::Rejected,
            ],
            ShipmentStatus::Approved => vec![ShipmentStatus::Released],
            ShipmentStatus::ApprovedWithConditions => {
                vec![ShipmentStatus::Released, ShipmentStatus::Held]
            }
            ShipmentStatus::Held => vec![
                ShipmentStatus::Approved,
                ShipmentStatus::Rejected,
                ShipmentStatus::Checked,
            ],
            ShipmentStatus::Rejected => vec![], // terminal
            ShipmentStatus::Released => vec![], // terminal
        }
    }

    /// Check if transition to new_status is valid.
    pub fn can_transition_to(&self, new_status: &ShipmentStatus) -> bool {
        self.valid_transitions().contains(new_status)
    }
}

/// Output command written to the outbox.
#[derive(Debug, Serialize, Deserialize)]
pub struct TrackingCommand {
    pub command_type: String,
    pub declaration_number: String,
    pub status: ShipmentStatus,
    pub previous_status: Option<ShipmentStatus>,
    pub timestamp: String,
    pub metadata: serde_json::Value,
}

/// Write a tracking command JSON to the outbox directory.
pub fn write_tracking_command(
    outbox_dir: &std::path::Path,
    declaration_number: &str,
    new_status: ShipmentStatus,
    previous_status: Option<ShipmentStatus>,
    metadata: serde_json::Value,
) -> anyhow::Result<()> {
    let now = Utc::now().to_rfc3339();
    let command = TrackingCommand {
        command_type: "shipment_status_update".to_string(),
        declaration_number: declaration_number.to_string(),
        status: new_status,
        previous_status,
        timestamp: now,
        metadata,
    };
    let filename = format!(
        "track_{}_{}.json",
        declaration_number.replace(['/', '\\', ' '], "_"),
        Utc::now().format("%Y%m%d_%H%M%S")
    );
    let path = outbox_dir.join(&filename);
    let json = serde_json::to_string_pretty(&command)?;
    std::fs::write(&path, json)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_transitions() {
        let received = ShipmentStatus::Received;
        assert!(received.can_transition_to(&ShipmentStatus::Parsed));
        assert!(!received.can_transition_to(&ShipmentStatus::Approved));

        let checked = ShipmentStatus::Checked;
        assert!(checked.can_transition_to(&ShipmentStatus::Approved));
        assert!(checked.can_transition_to(&ShipmentStatus::Rejected));
        assert!(checked.can_transition_to(&ShipmentStatus::Held));
        assert!(!checked.can_transition_to(&ShipmentStatus::Released));
    }

    #[test]
    fn test_terminal_states() {
        assert!(ShipmentStatus::Rejected.valid_transitions().is_empty());
        assert!(ShipmentStatus::Released.valid_transitions().is_empty());
    }

    #[test]
    fn test_held_can_return_to_checked() {
        let held = ShipmentStatus::Held;
        assert!(held.can_transition_to(&ShipmentStatus::Checked));
        assert!(held.can_transition_to(&ShipmentStatus::Approved));
    }
}
