//! Browser Dispatch — generates browser worker task JSON from compliance verdicts.
//!
//! When a compliance check returns `HoldPendingCertificates` or `EscalateHighValue`,
//! this module creates a task envelope that the Python browser worker can pick up
//! and execute on the Fasah portal via Playwright.
//!
//! ## Task Format (matches `schemas/fasah_task.schema.json`)
//!
//! ```json
//! {
//!   "task_id": "fasah-FASAH-2026-00002-20260318_120000",
//!   "playbook": "fasah_search_inspect_v1",
//!   "params": { "base_url": "https://fasah.gov.sa", "query": "FASAH-2026-00002" },
//!   "session_name": "fasah_agent",
//!   "outputs": { "out_dir": "fasah-FASAH-2026-00002-20260318_120000" }
//! }
//! ```

use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use crate::compliance::ComplianceAction;

/// A pending browser task entry.
#[derive(Debug, Serialize, Deserialize)]
pub struct PendingTask {
    pub declaration_number: String,
    pub dispatched_at: String,
    pub attempt: u32,
    pub action: String,
    /// Original compliance risk score (0-100) for decision quality tracking.
    #[serde(default)]
    pub risk_score: u8,
    /// What the agent predicted the outcome would be ("hold", "escalate").
    #[serde(default)]
    pub predicted_outcome: String,
}

/// Manages pending browser tasks and generates task envelopes.
pub struct BrowserDispatcher {
    browser_tasks_dir: PathBuf,
    pending_tasks_path: PathBuf,
    pending: BTreeMap<String, PendingTask>,
    fasah_base_url: String,
}

impl BrowserDispatcher {
    pub fn new(browser_tasks_dir: &Path) -> anyhow::Result<Self> {
        std::fs::create_dir_all(browser_tasks_dir)?;

        let pending_tasks_path = browser_tasks_dir.join(".pending_tasks.json");
        let pending = if pending_tasks_path.exists() {
            let content = std::fs::read_to_string(&pending_tasks_path)?;
            serde_json::from_str(&content).unwrap_or_default()
        } else {
            BTreeMap::new()
        };

        let fasah_base_url =
            std::env::var("FASAH_BASE_URL").unwrap_or_else(|_| "https://fasah.gov.sa".to_string());

        Ok(Self {
            browser_tasks_dir: browser_tasks_dir.to_path_buf(),
            pending_tasks_path,
            pending,
            fasah_base_url,
        })
    }

    /// Check if a compliance action should trigger a browser task.
    pub fn needs_browser_verification(action: &ComplianceAction) -> bool {
        matches!(
            action,
            ComplianceAction::HoldPendingCertificates | ComplianceAction::EscalateHighValue
        )
    }

    /// Dispatch a browser task for a declaration. Returns the task_id.
    #[allow(dead_code)]
    pub fn dispatch(
        &mut self,
        declaration_number: &str,
        action: &ComplianceAction,
    ) -> anyhow::Result<String> {
        self.dispatch_with_score(declaration_number, action, 0)
    }

    /// Dispatch a browser task with risk score for decision quality tracking.
    pub fn dispatch_with_score(
        &mut self,
        declaration_number: &str,
        action: &ComplianceAction,
        risk_score: u8,
    ) -> anyhow::Result<String> {
        let now = Utc::now();
        let safe_decl = declaration_number.replace(['/', '\\', ' '], "_");
        let task_id = format!("fasah-{}-{}", safe_decl, now.format("%Y%m%d_%H%M%S_%3f"));

        let task_envelope = serde_json::json!({
            "task_id": task_id,
            "playbook": "fasah_search_inspect_v1",
            "params": {
                "base_url": self.fasah_base_url,
                "query": declaration_number,
            },
            "session_name": "fasah_agent",
            "outputs": {
                "out_dir": task_id,
            }
        });

        // Atomic write: tmp → fsync → rename
        let filename = format!("{}.json", task_id);
        let tmp_path = self.browser_tasks_dir.join(format!(".tmp_{}", filename));
        let final_path = self.browser_tasks_dir.join(&filename);

        let content = serde_json::to_string_pretty(&task_envelope)?;
        {
            use std::io::Write;
            let mut file = std::fs::File::create(&tmp_path)?;
            file.write_all(content.as_bytes())?;
            file.sync_all()?;
        }

        std::fs::rename(&tmp_path, &final_path)?;

        let predicted_outcome = match action {
            ComplianceAction::HoldPendingCertificates => "hold",
            ComplianceAction::EscalateHighValue => "escalate",
            _ => "unknown",
        };

        self.pending.insert(
            task_id.clone(),
            PendingTask {
                declaration_number: declaration_number.to_string(),
                dispatched_at: now.to_rfc3339(),
                attempt: 1,
                action: format!("{:?}", action),
                risk_score,
                predicted_outcome: predicted_outcome.to_string(),
            },
        );
        self.save_pending()?;

        Ok(task_id)
    }

    /// Re-dispatch a failed task (retry). Returns new task_id.
    pub fn retry(&mut self, old_task_id: &str, max_retries: u32) -> anyhow::Result<Option<String>> {
        let old_entry = match self.pending.remove(old_task_id) {
            Some(e) => e,
            None => return Ok(None),
        };

        if old_entry.attempt >= max_retries {
            self.save_pending()?;
            return Ok(None);
        }

        let now = Utc::now();
        let safe_decl = old_entry.declaration_number.replace(['/', '\\', ' '], "_");
        let task_id = format!("fasah-{}-{}", safe_decl, now.format("%Y%m%d_%H%M%S_%3f"));

        let task_envelope = serde_json::json!({
            "task_id": task_id,
            "playbook": "fasah_search_inspect_v1",
            "params": {
                "base_url": self.fasah_base_url,
                "query": old_entry.declaration_number,
            },
            "session_name": "fasah_agent",
            "outputs": {
                "out_dir": task_id,
            }
        });

        let filename = format!("{}.json", task_id);
        let tmp_path = self.browser_tasks_dir.join(format!(".tmp_{}", filename));
        let final_path = self.browser_tasks_dir.join(&filename);

        let content = serde_json::to_string_pretty(&task_envelope)?;
        {
            use std::io::Write;
            let mut file = std::fs::File::create(&tmp_path)?;
            file.write_all(content.as_bytes())?;
            file.sync_all()?;
        }
        std::fs::rename(&tmp_path, &final_path)?;

        self.pending.insert(
            task_id.clone(),
            PendingTask {
                declaration_number: old_entry.declaration_number,
                dispatched_at: now.to_rfc3339(),
                attempt: old_entry.attempt + 1,
                action: old_entry.action,
                risk_score: old_entry.risk_score,
                predicted_outcome: old_entry.predicted_outcome,
            },
        );
        self.save_pending()?;

        Ok(Some(task_id))
    }

    /// Get the declaration number for a task_id.
    #[allow(dead_code)]
    pub fn get_declaration_number(&self, task_id: &str) -> Option<&str> {
        self.pending
            .get(task_id)
            .map(|e| e.declaration_number.as_str())
    }

    /// Get the full pending task entry for quality tracking.
    pub fn get_pending_task(&self, task_id: &str) -> Option<&PendingTask> {
        self.pending.get(task_id)
    }

    /// Remove a completed task from pending.
    pub fn mark_completed(&mut self, task_id: &str) -> anyhow::Result<()> {
        self.pending.remove(task_id);
        self.save_pending()
    }

    /// Get count of pending tasks.
    pub fn pending_count(&self) -> usize {
        self.pending.len()
    }

    fn save_pending(&self) -> anyhow::Result<()> {
        let content = serde_json::to_string_pretty(&self.pending)?;
        std::fs::write(&self.pending_tasks_path, &content)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_needs_browser_verification() {
        assert!(BrowserDispatcher::needs_browser_verification(
            &ComplianceAction::HoldPendingCertificates
        ));
        assert!(BrowserDispatcher::needs_browser_verification(
            &ComplianceAction::EscalateHighValue
        ));
        assert!(!BrowserDispatcher::needs_browser_verification(
            &ComplianceAction::Approve
        ));
        assert!(!BrowserDispatcher::needs_browser_verification(
            &ComplianceAction::Reject
        ));
    }

    #[test]
    fn test_dispatch_creates_task_file() {
        let dir = tempfile::tempdir().unwrap();
        let mut dispatcher = BrowserDispatcher::new(dir.path()).unwrap();

        let task_id = dispatcher
            .dispatch(
                "FASAH-2026-00001",
                &ComplianceAction::HoldPendingCertificates,
            )
            .unwrap();

        assert!(task_id.starts_with("fasah-FASAH-2026-00001-"));

        let task_file = dir.path().join(format!("{}.json", task_id));
        assert!(task_file.exists());

        let content = std::fs::read_to_string(&task_file).unwrap();
        let task: serde_json::Value = serde_json::from_str(&content).unwrap();
        assert_eq!(task["playbook"], "fasah_search_inspect_v1");
        assert_eq!(task["params"]["query"], "FASAH-2026-00001");
        assert!(dir.path().join(".pending_tasks.json").exists());
        assert_eq!(dispatcher.pending_count(), 1);
    }

    #[test]
    fn test_retry_increments_attempt() {
        let dir = tempfile::tempdir().unwrap();
        let mut dispatcher = BrowserDispatcher::new(dir.path()).unwrap();

        let task_id = dispatcher
            .dispatch("FASAH-2026-00002", &ComplianceAction::EscalateHighValue)
            .unwrap();

        let retry_id = dispatcher.retry(&task_id, 3).unwrap();
        assert!(retry_id.is_some());
        assert_ne!(task_id, retry_id.unwrap());
        assert_eq!(dispatcher.pending_count(), 1);
    }

    #[test]
    fn test_retry_max_exceeded() {
        let dir = tempfile::tempdir().unwrap();
        let mut dispatcher = BrowserDispatcher::new(dir.path()).unwrap();

        let t1 = dispatcher
            .dispatch(
                "FASAH-2026-00003",
                &ComplianceAction::HoldPendingCertificates,
            )
            .unwrap();
        let t2 = dispatcher.retry(&t1, 3).unwrap().unwrap();
        let t3 = dispatcher.retry(&t2, 3).unwrap().unwrap();

        let t4 = dispatcher.retry(&t3, 3).unwrap();
        assert!(t4.is_none(), "should not retry after max attempts");
    }
}
