//! Fasah Declaration Parser
//!
//! Parses customs declaration files (CSV/JSON) from the Tabadol/Fasah system.
//! Pure functions — no I/O dependencies, fully testable.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// A single customs declaration record.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeclarationRecord {
    /// Fasah declaration number (e.g., "FASAH-2026-00012345")
    pub declaration_number: String,
    /// Harmonized System code for the goods
    pub hs_code: String,
    /// Importer name / entity (supports Arabic)
    pub importer_name: String,
    /// Importer CR (commercial registration) number
    pub importer_cr: String,
    /// Country of origin (ISO 3166-1 alpha-2)
    pub origin_country: String,
    /// Declared value in SAR
    pub declared_value_sar: f64,
    /// Shipment weight in kg
    pub weight_kg: f64,
    /// Port of entry code (e.g., SAJED, SAKHI)
    pub port_of_entry: String,
    /// Declaration date (ISO 8601)
    pub declaration_date: String,
    /// List of required compliance certificates
    pub required_certificates: Vec<String>,
    /// Raw line/record number from source file
    pub source_line: usize,
}

/// Parsed output from a declaration file.
#[derive(Debug, Serialize, Deserialize)]
pub struct ParseResult {
    pub total_records: usize,
    pub valid_records: usize,
    pub invalid_records: usize,
    pub records: Vec<DeclarationRecord>,
    pub errors: Vec<ParseError>,
    pub content_hash: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ParseError {
    pub line: usize,
    pub field: String,
    pub message: String,
}

pub struct DeclarationParser;

impl DeclarationParser {
    /// Parse CSV content — pure function, no I/O.
    pub fn parse_csv(content: &str) -> Result<ParseResult, String> {
        let mut records = Vec::new();
        let mut errors = Vec::new();
        let lines: Vec<&str> = content.lines().collect();

        if lines.is_empty() {
            return Err("empty file".to_string());
        }

        // Validate header
        let header = lines[0].to_lowercase();
        let expected_fields = [
            "declaration_number",
            "hs_code",
            "importer_name",
            "importer_cr",
            "origin_country",
            "declared_value_sar",
            "weight_kg",
            "port_of_entry",
            "declaration_date",
            "required_certificates",
        ];

        let header_fields: Vec<&str> = header.split(',').map(|s| s.trim()).collect();
        for expected in &expected_fields {
            if !header_fields.contains(expected) {
                errors.push(ParseError {
                    line: 1,
                    field: expected.to_string(),
                    message: format!("missing required header field: {}", expected),
                });
            }
        }

        // Parse data rows
        for (idx, line) in lines.iter().enumerate().skip(1) {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }

            let fields: Vec<&str> = line.split(',').map(|s| s.trim()).collect();
            if fields.len() < 10 {
                errors.push(ParseError {
                    line: idx + 1,
                    field: "row".to_string(),
                    message: format!("expected at least 10 fields, got {}", fields.len()),
                });
                continue;
            }

            // Parse declared_value
            let declared_value = match fields[5].parse::<f64>() {
                Ok(v) if v >= 0.0 => v,
                Ok(v) => {
                    errors.push(ParseError {
                        line: idx + 1,
                        field: "declared_value_sar".to_string(),
                        message: format!("negative value not allowed: {}", v),
                    });
                    continue;
                }
                Err(_) => {
                    errors.push(ParseError {
                        line: idx + 1,
                        field: "declared_value_sar".to_string(),
                        message: format!("invalid number: '{}'", fields[5]),
                    });
                    continue;
                }
            };

            // Parse weight
            let weight = match fields[6].parse::<f64>() {
                Ok(v) if v >= 0.0 => v,
                _ => {
                    errors.push(ParseError {
                        line: idx + 1,
                        field: "weight_kg".to_string(),
                        message: format!("invalid weight: '{}'", fields[6]),
                    });
                    continue;
                }
            };

            // Parse certificates (semicolon-separated)
            let certificates: Vec<String> = fields[9]
                .split(';')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect();

            // Validate HS code (6-10 digit numeric, dots allowed)
            let hs_code = fields[1].trim();
            if !hs_code.chars().all(|c| c.is_ascii_digit() || c == '.')
                || hs_code.replace('.', "").len() < 6
            {
                errors.push(ParseError {
                    line: idx + 1,
                    field: "hs_code".to_string(),
                    message: format!("invalid HS code format: '{}'", hs_code),
                });
                continue;
            }

            // Validate origin country (2-letter ISO code)
            let origin = fields[4].trim();
            if origin.len() != 2 || !origin.chars().all(|c| c.is_ascii_uppercase()) {
                errors.push(ParseError {
                    line: idx + 1,
                    field: "origin_country".to_string(),
                    message: format!("invalid ISO country code: '{}'", origin),
                });
                continue;
            }

            records.push(DeclarationRecord {
                declaration_number: fields[0].trim().to_string(),
                hs_code: hs_code.to_string(),
                importer_name: fields[2].trim().to_string(),
                importer_cr: fields[3].trim().to_string(),
                origin_country: origin.to_string(),
                declared_value_sar: declared_value,
                weight_kg: weight,
                port_of_entry: fields[7].trim().to_string(),
                declaration_date: fields[8].trim().to_string(),
                required_certificates: certificates,
                source_line: idx + 1,
            });
        }

        // Content hash for idempotency
        let mut hasher = Sha256::new();
        hasher.update(content.as_bytes());
        let content_hash = hex::encode(hasher.finalize());

        let total = records.len()
            + errors
                .iter()
                .filter(|e| e.field != "row" || e.line > 1)
                .count();
        let valid = records.len();
        let invalid = total - valid;

        Ok(ParseResult {
            total_records: total,
            valid_records: valid,
            invalid_records: invalid,
            records,
            errors,
            content_hash,
        })
    }

    /// Parse JSON content — expects array of DeclarationRecord.
    pub fn parse_json(content: &str) -> Result<ParseResult, String> {
        let records: Vec<DeclarationRecord> =
            serde_json::from_str(content).map_err(|e| format!("JSON parse error: {}", e))?;

        let mut hasher = Sha256::new();
        hasher.update(content.as_bytes());
        let content_hash = hex::encode(hasher.finalize());
        let total = records.len();

        Ok(ParseResult {
            total_records: total,
            valid_records: total,
            invalid_records: 0,
            records,
            errors: vec![],
            content_hash,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_valid_csv() {
        let csv = "\
declaration_number,hs_code,importer_name,importer_cr,origin_country,declared_value_sar,weight_kg,port_of_entry,declaration_date,required_certificates
FASAH-2026-00001,8471.30.00,شركة التقنية,1010123456,CN,150000.00,2500.0,SAJED,2026-02-15,SASO;CoC
FASAH-2026-00002,0402.10.00,مؤسسة الغذاء,1010654321,NZ,85000.00,5000.0,SAKHI,2026-02-16,SFDA;Halal";

        let result = DeclarationParser::parse_csv(csv).unwrap();
        assert_eq!(result.valid_records, 2);
        assert_eq!(result.invalid_records, 0);
        assert_eq!(result.records[0].declaration_number, "FASAH-2026-00001");
        assert_eq!(result.records[0].origin_country, "CN");
        assert_eq!(
            result.records[1].required_certificates,
            vec!["SFDA", "Halal"]
        );
    }

    #[test]
    fn test_parse_invalid_country_code() {
        let csv = "\
declaration_number,hs_code,importer_name,importer_cr,origin_country,declared_value_sar,weight_kg,port_of_entry,declaration_date,required_certificates
FASAH-2026-00001,8471.30.00,Test,123,xyz,150000.00,2500.0,SAJED,2026-02-15,SASO";

        let result = DeclarationParser::parse_csv(csv).unwrap();
        assert_eq!(result.valid_records, 0);
        assert!(result.errors.iter().any(|e| e.field == "origin_country"));
    }

    #[test]
    fn test_parse_negative_value() {
        let csv = "\
declaration_number,hs_code,importer_name,importer_cr,origin_country,declared_value_sar,weight_kg,port_of_entry,declaration_date,required_certificates
FASAH-2026-00001,8471.30.00,Test,123,CN,-500.00,2500.0,SAJED,2026-02-15,SASO";

        let result = DeclarationParser::parse_csv(csv).unwrap();
        assert_eq!(result.valid_records, 0);
        assert!(result
            .errors
            .iter()
            .any(|e| e.field == "declared_value_sar"));
    }
}
