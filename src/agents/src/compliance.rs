//! Fasah Compliance Checker
//!
//! Validates customs declarations against Saudi regulatory rules:
//! - HS code restrictions (banned/restricted goods)
//! - Certificate requirements (SASO, SFDA, Halal, etc.)
//! - Value thresholds requiring additional scrutiny
//! - Origin-country sanctions and trade agreements
//!
//! Pure functions — no I/O, fully testable.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

use crate::parser::DeclarationRecord;

/// Compliance rules loaded from YAML configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceRules {
    /// HS code prefixes that are completely banned (e.g., weapons, narcotics).
    #[serde(default)]
    pub banned_hs_prefixes: Vec<String>,

    /// HS code prefixes requiring specific certificates.
    /// Key: HS prefix, Value: list of required certificate types.
    #[serde(default)]
    pub certificate_requirements: BTreeMap<String, Vec<String>>,

    /// Countries under trade sanctions (ISO alpha-2).
    #[serde(default)]
    pub sanctioned_countries: BTreeSet<String>,

    /// Value threshold (SAR) above which enhanced scrutiny is required.
    #[serde(default = "default_high_value_threshold")]
    pub high_value_threshold_sar: f64,

    /// Maximum weight (kg) per declaration before physical inspection is mandated.
    #[serde(default = "default_max_weight")]
    pub max_weight_kg: f64,
}

fn default_high_value_threshold() -> f64 {
    500_000.0
}
fn default_max_weight() -> f64 {
    50_000.0
}

impl Default for ComplianceRules {
    fn default() -> Self {
        let mut certificate_requirements = BTreeMap::new();
        // Food products (HS chapters 01-24) require SFDA + Halal
        for prefix in &[
            "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14",
            "15", "16", "17", "18", "19", "20", "21", "22", "23", "24",
        ] {
            certificate_requirements.insert(
                prefix.to_string(),
                vec!["SFDA".to_string(), "Halal".to_string()],
            );
        }
        // Electronics (HS 84-85) require SASO
        for prefix in &["84", "85"] {
            certificate_requirements.insert(prefix.to_string(), vec!["SASO".to_string()]);
        }
        // Chemicals (HS 28-38) require SASO + HazMat
        for prefix in &[
            "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38",
        ] {
            certificate_requirements.insert(
                prefix.to_string(),
                vec!["SASO".to_string(), "HazMat".to_string()],
            );
        }

        Self {
            banned_hs_prefixes: vec![
                "9301".to_string(), // Military weapons
                "9302".to_string(), // Revolvers/pistols
                "2403".to_string(), // Certain tobacco products (restricted)
            ],
            certificate_requirements,
            sanctioned_countries: BTreeSet::new(),
            high_value_threshold_sar: default_high_value_threshold(),
            max_weight_kg: default_max_weight(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ComplianceAction {
    /// Declaration is compliant — approve.
    Approve,
    /// Minor issues — approve with conditions.
    ApproveWithConditions,
    /// Missing certificates — hold until provided.
    HoldPendingCertificates,
    /// High-value: requires enhanced review.
    EscalateHighValue,
    /// Banned goods — reject.
    Reject,
    /// Sanctioned origin — reject and flag.
    RejectSanctioned,
    /// Overweight — mandate physical inspection.
    MandateInspection,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceVerdict {
    pub declaration_number: String,
    pub action: ComplianceAction,
    pub reasons: Vec<String>,
    pub missing_certificates: Vec<String>,
    pub risk_score: u8, // 0-100
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ComplianceResult {
    pub total_checked: usize,
    pub approved: usize,
    pub held: usize,
    pub escalated: usize,
    pub rejected: usize,
    pub verdicts: Vec<ComplianceVerdict>,
}

pub struct ComplianceChecker;

impl ComplianceChecker {
    /// Check a single declaration against the compliance rules.
    pub fn check_declaration(
        record: &DeclarationRecord,
        rules: &ComplianceRules,
    ) -> ComplianceVerdict {
        let mut reasons = Vec::new();
        let mut missing_certs = Vec::new();
        let mut risk_score: u8 = 0;
        let mut action = ComplianceAction::Approve;

        // 1. Sanctioned country check (highest priority)
        if rules.sanctioned_countries.contains(&record.origin_country) {
            reasons.push(format!(
                "origin country '{}' is under trade sanctions",
                record.origin_country
            ));
            risk_score = 100;
            action = ComplianceAction::RejectSanctioned;
        }

        // 2. Banned HS code check
        let hs_clean = record.hs_code.replace('.', "");
        for banned in &rules.banned_hs_prefixes {
            let banned_clean = banned.replace('.', "");
            if hs_clean.starts_with(&banned_clean) {
                reasons.push(format!(
                    "HS code '{}' matches banned prefix '{}'",
                    record.hs_code, banned
                ));
                risk_score = 100;
                action = ComplianceAction::Reject;
            }
        }

        // If already rejected, return early
        if action == ComplianceAction::Reject || action == ComplianceAction::RejectSanctioned {
            return ComplianceVerdict {
                declaration_number: record.declaration_number.clone(),
                action,
                reasons,
                missing_certificates: missing_certs,
                risk_score,
            };
        }

        // 3. Certificate requirements
        let hs_prefix_2 = if hs_clean.len() >= 2 {
            &hs_clean[..2]
        } else {
            &hs_clean
        };
        let hs_prefix_4 = if hs_clean.len() >= 4 {
            &hs_clean[..4]
        } else {
            &hs_clean
        };

        let mut required_certs: BTreeSet<String> = BTreeSet::new();
        if let Some(certs) = rules.certificate_requirements.get(hs_prefix_2) {
            required_certs.extend(certs.iter().cloned());
        }
        if let Some(certs) = rules.certificate_requirements.get(hs_prefix_4) {
            required_certs.extend(certs.iter().cloned());
        }

        let provided: BTreeSet<String> = record.required_certificates.iter().cloned().collect();
        for req in &required_certs {
            if !provided.contains(req) {
                missing_certs.push(req.clone());
            }
        }

        if !missing_certs.is_empty() {
            reasons.push(format!(
                "missing certificates: {}",
                missing_certs.join(", ")
            ));
            risk_score = risk_score.max(60);
            action = ComplianceAction::HoldPendingCertificates;
        }

        // 4. High-value check
        if record.declared_value_sar > rules.high_value_threshold_sar {
            reasons.push(format!(
                "declared value {} SAR exceeds threshold {} SAR",
                record.declared_value_sar, rules.high_value_threshold_sar
            ));
            risk_score = risk_score.max(70);
            if action == ComplianceAction::Approve {
                action = ComplianceAction::EscalateHighValue;
            }
        }

        // 5. Overweight check
        if record.weight_kg > rules.max_weight_kg {
            reasons.push(format!(
                "weight {} kg exceeds inspection threshold {} kg",
                record.weight_kg, rules.max_weight_kg
            ));
            risk_score = risk_score.max(50);
            if action == ComplianceAction::Approve {
                action = ComplianceAction::MandateInspection;
            }
        }

        // 6. Minor notes → conditional approval
        if action == ComplianceAction::Approve && !reasons.is_empty() {
            action = ComplianceAction::ApproveWithConditions;
            risk_score = risk_score.max(20);
        }

        ComplianceVerdict {
            declaration_number: record.declaration_number.clone(),
            action,
            reasons,
            missing_certificates: missing_certs,
            risk_score,
        }
    }

    /// Check all declarations and return aggregated results.
    pub fn check_all(records: &[DeclarationRecord], rules: &ComplianceRules) -> ComplianceResult {
        let verdicts: Vec<ComplianceVerdict> = records
            .iter()
            .map(|r| Self::check_declaration(r, rules))
            .collect();

        let approved = verdicts
            .iter()
            .filter(|v| {
                matches!(
                    v.action,
                    ComplianceAction::Approve | ComplianceAction::ApproveWithConditions
                )
            })
            .count();
        let held = verdicts
            .iter()
            .filter(|v| matches!(v.action, ComplianceAction::HoldPendingCertificates))
            .count();
        let escalated = verdicts
            .iter()
            .filter(|v| {
                matches!(
                    v.action,
                    ComplianceAction::EscalateHighValue | ComplianceAction::MandateInspection
                )
            })
            .count();
        let rejected = verdicts
            .iter()
            .filter(|v| {
                matches!(
                    v.action,
                    ComplianceAction::Reject | ComplianceAction::RejectSanctioned
                )
            })
            .count();

        ComplianceResult {
            total_checked: verdicts.len(),
            approved,
            held,
            escalated,
            rejected,
            verdicts,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::DeclarationRecord;

    fn sample_declaration(
        hs_code: &str,
        origin: &str,
        value: f64,
        certs: Vec<&str>,
    ) -> DeclarationRecord {
        DeclarationRecord {
            declaration_number: "FASAH-TEST-001".to_string(),
            hs_code: hs_code.to_string(),
            importer_name: "Test Importer".to_string(),
            importer_cr: "1010000001".to_string(),
            origin_country: origin.to_string(),
            declared_value_sar: value,
            weight_kg: 1000.0,
            port_of_entry: "SAJED".to_string(),
            declaration_date: "2026-02-15".to_string(),
            required_certificates: certs.iter().map(|s| s.to_string()).collect(),
            source_line: 1,
        }
    }

    #[test]
    fn test_approve_compliant_electronics() {
        let rules = ComplianceRules::default();
        let decl = sample_declaration("8471.30.00", "CN", 50000.0, vec!["SASO"]);
        let verdict = ComplianceChecker::check_declaration(&decl, &rules);
        assert_eq!(verdict.action, ComplianceAction::Approve);
        assert!(verdict.missing_certificates.is_empty());
    }

    #[test]
    fn test_hold_missing_certificate() {
        let rules = ComplianceRules::default();
        let decl = sample_declaration("0402.10.00", "NZ", 50000.0, vec![]);
        let verdict = ComplianceChecker::check_declaration(&decl, &rules);
        assert_eq!(verdict.action, ComplianceAction::HoldPendingCertificates);
        assert!(verdict.missing_certificates.contains(&"SFDA".to_string()));
        assert!(verdict.missing_certificates.contains(&"Halal".to_string()));
    }

    #[test]
    fn test_reject_banned_hs_code() {
        let rules = ComplianceRules::default();
        let decl = sample_declaration("9301.00.00", "US", 10000.0, vec![]);
        let verdict = ComplianceChecker::check_declaration(&decl, &rules);
        assert_eq!(verdict.action, ComplianceAction::Reject);
        assert_eq!(verdict.risk_score, 100);
    }

    #[test]
    fn test_escalate_high_value() {
        let rules = ComplianceRules::default();
        let decl = sample_declaration("8471.30.00", "JP", 600000.0, vec!["SASO"]);
        let verdict = ComplianceChecker::check_declaration(&decl, &rules);
        assert_eq!(verdict.action, ComplianceAction::EscalateHighValue);
    }

    #[test]
    fn test_reject_sanctioned_country() {
        let mut rules = ComplianceRules::default();
        rules.sanctioned_countries.insert("XX".to_string());
        let decl = sample_declaration("8471.30.00", "XX", 1000.0, vec!["SASO"]);
        let verdict = ComplianceChecker::check_declaration(&decl, &rules);
        assert_eq!(verdict.action, ComplianceAction::RejectSanctioned);
    }
}
