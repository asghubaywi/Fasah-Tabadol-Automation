//! Browser Result Watcher — scans for completed browser worker results.
//!
//! Monitors `browser_results_dir` for `bundle.json` files produced by the
//! Python Playwright worker. Maps results back to declarations and generates
//! appropriate shipment status updates or escalations.
//!
//! ## Bundle Status → Action Mapping
//!
//! | Status | Action |
//! |--------|--------|
//! | FOUND + approval | → shipment_track: approved |
//! | FOUND + hold | → shipment_track: held |
//! | NOT_FOUND | → log warning |
//! | TRANSIENT_FAIL | → retry (max N) |
//! | AUTH_FAIL | → escalation to outbox |
//! | NEEDS_HUMAN | → escalation to outbox |

use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::path::Path;

use crate::dispatcher::BrowserDispatcher;

/// Parsed browser worker bundle.
#[derive(Debug, Deserialize)]
pub struct BrowserBundle {
    pub task_id: String,
    pub status: String,
    #[serde(default)]
    pub error_code: Option<String>,
    #[serde(default)]
    pub error_detail: Option<String>,
    #[serde(default)]
    pub record_url: Option<String>,
    #[serde(default)]
    pub current_status: Option<String>,
}

/// Result of processing a single bundle.
#[derive(Debug, Serialize)]
pub struct ResultAction {
    pub task_id: String,
    pub declaration_number: String,
    pub bundle_status: String,
    pub action_taken: String,
    pub new_shipment_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prediction_correct: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub predicted_action: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub actual_portal_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub risk_score: Option<u8>,
}

/// Escalation command written to outbox when human intervention is needed.
#[derive(Debug, Serialize)]
pub struct EscalationCommand {
    pub command_type: String,
    pub declaration_number: String,
    pub reason: String,
    pub browser_status: String,
    pub error_code: Option<String>,
    pub error_detail: Option<String>,
    pub timestamp: String,
}

/// Scan browser results directory and process completed bundles.
pub fn scan_results(
    browser_results_dir: &Path,
    dispatcher: &mut BrowserDispatcher,
    outbox_dir: &Path,
    max_retries: u32,
) -> anyhow::Result<Vec<ResultAction>> {
    let mut actions = Vec::new();

    if !browser_results_dir.exists() {
        return Ok(actions);
    }

    let entries = std::fs::read_dir(browser_results_dir)?;
    for entry in entries {
        let entry = entry?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }

        let bundle_path = path.join("bundle.json");
        if !bundle_path.exists() {
            continue;
        }

        match process_bundle(&bundle_path, dispatcher, outbox_dir, max_retries) {
            Ok(action) => {
                // Move processed result bundle to .processed/
                let processed_dir = browser_results_dir.join(".processed");
                std::fs::create_dir_all(&processed_dir)?;
                let dest = processed_dir.join(entry.file_name());
                if let Err(e) = std::fs::rename(&path, &dest) {
                    eprintln!(
                        "WARN: failed to move processed result {} → {}: {}",
                        path.display(),
                        dest.display(),
                        e
                    );
                }
                actions.push(action);
            }
            Err(e) => {
                eprintln!(
                    "ERROR: failed to process browser result {}: {}",
                    bundle_path.display(),
                    e
                );
            }
        }
    }

    Ok(actions)
}

fn process_bundle(
    bundle_path: &Path,
    dispatcher: &mut BrowserDispatcher,
    outbox_dir: &Path,
    max_retries: u32,
) -> anyhow::Result<ResultAction> {
    let content = std::fs::read_to_string(bundle_path)?;
    let bundle: BrowserBundle = serde_json::from_str(&content)?;

    let pending_task = dispatcher.get_pending_task(&bundle.task_id);
    let declaration_number = pending_task
        .map(|t| t.declaration_number.clone())
        .unwrap_or_else(|| "UNKNOWN".to_string());
    let predicted_action = pending_task.map(|t| t.predicted_outcome.clone());
    let original_risk_score = pending_task.map(|t| t.risk_score);

    let (action_taken, new_status) = match bundle.status.as_str() {
        "FOUND" => handle_found(&bundle, &declaration_number, outbox_dir)?,
        "NOT_FOUND" => ("logged_not_found".to_string(), None),
        "TRANSIENT_FAIL" => match dispatcher.retry(&bundle.task_id, max_retries)? {
            Some(new_id) => {
                return Ok(ResultAction {
                    task_id: bundle.task_id,
                    declaration_number,
                    bundle_status: "TRANSIENT_FAIL".to_string(),
                    action_taken: format!("retried_as_{}", new_id),
                    new_shipment_status: None,
                    prediction_correct: None,
                    predicted_action,
                    actual_portal_status: None,
                    risk_score: original_risk_score,
                });
            }
            None => {
                write_escalation(
                    outbox_dir,
                    &declaration_number,
                    "max retries exceeded for browser task",
                    &bundle,
                )?;
                ("escalated_max_retries".to_string(), None)
            }
        },
        "AUTH_FAIL" | "NEEDS_HUMAN" => {
            write_escalation(
                outbox_dir,
                &declaration_number,
                &format!("browser worker returned {}", bundle.status),
                &bundle,
            )?;
            (format!("escalated_{}", bundle.status.to_lowercase()), None)
        }
        _ => ("unknown_status".to_string(), None),
    };

    // Decision quality tracking
    let prediction_correct =
        if let (Some(predicted), Some(ref actual_status)) = (&predicted_action, &new_status) {
            Some(match predicted.as_str() {
                "hold" => actual_status == "held" || actual_status == "rejected",
                "escalate" => actual_status != "approved",
                _ => false,
            })
        } else {
            None
        };

    let actual_portal_status = bundle.current_status.clone();
    dispatcher.mark_completed(&bundle.task_id)?;

    Ok(ResultAction {
        task_id: bundle.task_id,
        declaration_number,
        bundle_status: bundle.status,
        action_taken,
        new_shipment_status: new_status,
        prediction_correct,
        predicted_action,
        actual_portal_status,
        risk_score: original_risk_score,
    })
}

fn handle_found(
    bundle: &BrowserBundle,
    declaration_number: &str,
    outbox_dir: &Path,
) -> anyhow::Result<(String, Option<String>)> {
    let portal_status = bundle
        .current_status
        .as_deref()
        .unwrap_or("")
        .to_lowercase();

    let approval_keywords = ["approved", "مقبول", "موافق", "released", "cleared", "مفسوح"];
    let hold_keywords = [
        "hold",
        "pending",
        "review",
        "معلق",
        "قيد المراجعة",
        "under review",
    ];
    let reject_keywords = ["rejected", "مرفوض", "denied", "refused"];

    let new_status = if approval_keywords
        .iter()
        .any(|kw| portal_status.contains(kw))
    {
        Some("approved")
    } else if reject_keywords.iter().any(|kw| portal_status.contains(kw)) {
        Some("rejected")
    } else if hold_keywords.iter().any(|kw| portal_status.contains(kw)) {
        Some("held")
    } else {
        None
    };

    if let Some(status) = new_status {
        let command = serde_json::json!({
            "command_type": "shipment_status_update",
            "declaration_number": declaration_number,
            "status": status,
            "previous_status": "checked",
            "timestamp": Utc::now().to_rfc3339(),
            "metadata": {
                "source": "browser_worker",
                "portal_status": bundle.current_status,
                "record_url": bundle.record_url,
            }
        });

        let filename = format!(
            "track_{}_{}.json",
            declaration_number.replace(['/', '\\', ' '], "_"),
            Utc::now().format("%Y%m%d_%H%M%S")
        );
        let path = outbox_dir.join(&filename);
        std::fs::write(&path, serde_json::to_string_pretty(&command)?)?;

        Ok((
            format!("status_updated_to_{}", status),
            Some(status.to_string()),
        ))
    } else {
        Ok(("portal_status_unrecognized".to_string(), None))
    }
}

fn write_escalation(
    outbox_dir: &Path,
    declaration_number: &str,
    reason: &str,
    bundle: &BrowserBundle,
) -> anyhow::Result<()> {
    let escalation = EscalationCommand {
        command_type: "escalation".to_string(),
        declaration_number: declaration_number.to_string(),
        reason: reason.to_string(),
        browser_status: bundle.status.clone(),
        error_code: bundle.error_code.clone(),
        error_detail: bundle.error_detail.clone(),
        timestamp: Utc::now().to_rfc3339(),
    };

    let filename = format!(
        "escalation_{}_{}.json",
        declaration_number.replace(['/', '\\', ' '], "_"),
        Utc::now().format("%Y%m%d_%H%M%S")
    );
    let path = outbox_dir.join(&filename);
    std::fs::write(&path, serde_json::to_string_pretty(&escalation)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_found_bundle() {
        let bundle_json = r#"{
            "task_id": "fasah-TEST-001-20260318_120000",
            "status": "FOUND",
            "record_url": "https://fasah.gov.sa/en/request/12345",
            "current_status": "Approved",
            "artifacts": [],
            "hashes": {}
        }"#;
        let bundle: BrowserBundle = serde_json::from_str(bundle_json).unwrap();
        assert_eq!(bundle.status, "FOUND");
        assert_eq!(bundle.current_status.as_deref(), Some("Approved"));
    }

    #[test]
    fn test_handle_found_approved() {
        let dir = tempfile::tempdir().unwrap();
        let bundle = BrowserBundle {
            task_id: "test-001".to_string(),
            status: "FOUND".to_string(),
            error_code: None,
            error_detail: None,
            record_url: Some("https://fasah.gov.sa/req/123".to_string()),
            current_status: Some("Approved - Released".to_string()),
        };

        let (action, status) = handle_found(&bundle, "FASAH-2026-00001", dir.path()).unwrap();
        assert_eq!(status, Some("approved".to_string()));
        assert!(action.contains("approved"));
    }

    #[test]
    fn test_handle_found_held() {
        let dir = tempfile::tempdir().unwrap();
        let bundle = BrowserBundle {
            task_id: "test-002".to_string(),
            status: "FOUND".to_string(),
            error_code: None,
            error_detail: None,
            record_url: None,
            current_status: Some("Under Review - Pending documents".to_string()),
        };

        let (_, status) = handle_found(&bundle, "FASAH-2026-00002", dir.path()).unwrap();
        assert_eq!(status, Some("held".to_string()));
    }

    #[test]
    fn test_write_escalation() {
        let dir = tempfile::tempdir().unwrap();
        let bundle = BrowserBundle {
            task_id: "test-003".to_string(),
            status: "AUTH_FAIL".to_string(),
            error_code: Some("E_AUTH_REQUIRED".to_string()),
            error_detail: Some("Login page detected".to_string()),
            record_url: None,
            current_status: None,
        };

        write_escalation(dir.path(), "FASAH-2026-00003", "auth failure", &bundle).unwrap();

        let files: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .collect();
        assert_eq!(files.len(), 1);
        assert!(files[0]
            .file_name()
            .to_string_lossy()
            .starts_with("escalation_"));
    }
}
