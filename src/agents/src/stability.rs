//! File stability tracker — prevents processing partially-written files.
//!
//! Tracks file metadata (size and mtime) across consecutive poll cycles:
//! a file is only considered "stable" when its metadata is unchanged
//! between two successive checks.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

#[derive(Default)]
pub struct FileStabilityTracker {
    state: HashMap<PathBuf, (u64, u64)>,
}

impl FileStabilityTracker {
    pub fn new() -> Self {
        Self {
            state: HashMap::new(),
        }
    }

    pub fn is_stable(&mut self, path: &Path) -> std::io::Result<bool> {
        let meta = std::fs::metadata(path)?;
        let size = meta.len();
        let mtime = meta
            .modified()?
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        if let Some((prev_size, prev_mtime)) = self.state.get(path) {
            if size == *prev_size && mtime == *prev_mtime {
                return Ok(true);
            }
            self.state.insert(path.to_path_buf(), (size, mtime));
            Ok(false)
        } else {
            self.state.insert(path.to_path_buf(), (size, mtime));
            Ok(false)
        }
    }

    pub fn remove(&mut self, path: &Path) {
        self.state.remove(path);
    }

    pub fn prune_missing(&mut self) {
        self.state.retain(|p, _| p.exists());
    }
}
