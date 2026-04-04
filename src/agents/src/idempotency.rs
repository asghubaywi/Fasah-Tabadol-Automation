//! Crash-safe, file-locked idempotency ledger.
//!
//! Records SHA-256 content hashes of every file that completed the full
//! parse → compliance → dispatch pipeline. Before processing a file, the
//! caller checks this ledger to detect duplicates.

use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::io::Write;
use std::path::{Path, PathBuf};

/// Ledger for tracking processed file hashes.
#[derive(Debug)]
pub struct ProcessedHashesLedger {
    ledger_path: PathBuf,
    known_hashes: HashSet<String>,
}

impl ProcessedHashesLedger {
    /// Open (or create) the ledger file and load all existing hashes into memory.
    pub fn open(ledger_path: &Path) -> Result<Self, std::io::Error> {
        if let Some(parent) = ledger_path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let mut known_hashes = HashSet::new();

        if ledger_path.exists() {
            // Security: reject symlinks
            let metadata = std::fs::symlink_metadata(ledger_path)?;
            if metadata.file_type().is_symlink() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    format!(
                        "SECURITY: processed_hashes ledger is a symlink: {}",
                        ledger_path.display()
                    ),
                ));
            }
            if !metadata.is_file() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    format!(
                        "processed_hashes ledger is not a regular file: {}",
                        ledger_path.display()
                    ),
                ));
            }

            let content = std::fs::read_to_string(ledger_path)?;
            for line in content.lines() {
                let line = line.trim();
                if line.is_empty() {
                    continue;
                }
                if let Some(hash) = line.split_whitespace().next() {
                    if hash.len() == 64 && hash.chars().all(|c| c.is_ascii_hexdigit()) {
                        known_hashes.insert(hash.to_string());
                    }
                }
            }
        }

        Ok(Self {
            ledger_path: ledger_path.to_path_buf(),
            known_hashes,
        })
    }

    pub fn is_duplicate(&self, content_hash: &str) -> bool {
        self.known_hashes.contains(content_hash)
    }

    pub fn hash_file(path: &Path) -> Result<String, std::io::Error> {
        let content = std::fs::read(path)?;
        let mut hasher = Sha256::new();
        hasher.update(&content);
        Ok(hex::encode(hasher.finalize()))
    }

    pub fn record_hash(
        &mut self,
        content_hash: &str,
        filename: &str,
    ) -> Result<(), std::io::Error> {
        let timestamp = chrono::Utc::now().to_rfc3339();
        let line = format!("{} {} {}\n", content_hash, filename, timestamp);

        let file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.ledger_path)?;

        // Cross-platform file locking via fs2
        use fs2::FileExt;
        file.lock_exclusive()?;

        let mut writer = std::io::BufWriter::new(&file);
        writer.write_all(line.as_bytes())?;
        writer.flush()?;
        file.sync_all()?;

        file.unlock()?;

        self.known_hashes.insert(content_hash.to_string());
        Ok(())
    }
}
