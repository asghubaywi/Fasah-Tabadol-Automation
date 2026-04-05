"""
fallback_parser.py — Pure Python CSV/JSON parser fallback for Fasah declarations.
محلل CSV/JSON احتياطي — يُستخدم عند فشل محرك Rust

Mimics the output format of ``fasah-engine parse`` so the rest of the
pipeline continues working when the Rust binary is unavailable or fails.

Usage (internal):
    from pipeline.fallback_parser import parse_file
    result = parse_file(Path("declarations.csv"))
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("fasah.fallback_parser")

# Required CSV columns — must match the Rust parser's expectations
REQUIRED_COLUMNS = [
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
]

# HS code: 6–10 digits, dots stripped before check
_HS_CODE_RE = re.compile(r"^\d{6,10}$")
# ISO 3166-1 alpha-2: exactly 2 uppercase letters
_ISO2_RE = re.compile(r"^[A-Z]{2}$")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_record(
    row: dict[str, str], line_num: int
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Validate a single CSV row.

    تحقق من صحة صف CSV واحد.

    Returns:
        (record_dict, []) on success, or (None, [error_strings]) on failure.
    """
    errors: list[str] = []

    # Validate HS code (strip dots for normalization)
    hs_raw = row.get("hs_code", "").strip()
    hs = hs_raw.replace(".", "")
    if not _HS_CODE_RE.match(hs):
        errors.append(
            f"Line {line_num}: invalid HS code '{hs_raw}' (must be 6–10 digits)"
        )

    # Validate origin country
    country = row.get("origin_country", "").strip()
    if not _ISO2_RE.match(country):
        errors.append(
            f"Line {line_num}: invalid country code '{country}' (must be ISO-2 uppercase)"
        )

    # Validate declared_value_sar
    try:
        declared_value = float(row.get("declared_value_sar", "0"))
        if declared_value < 0:
            errors.append(f"Line {line_num}: negative declared_value_sar")
    except ValueError:
        errors.append(f"Line {line_num}: non-numeric declared_value_sar")
        declared_value = 0.0

    # Validate weight_kg
    try:
        weight = float(row.get("weight_kg", "0"))
        if weight < 0:
            errors.append(f"Line {line_num}: negative weight_kg")
    except ValueError:
        errors.append(f"Line {line_num}: non-numeric weight_kg")
        weight = 0.0

    if errors:
        return None, errors

    # Parse certificates (semicolon or comma separated)
    cert_str = row.get("required_certificates", "").strip()
    certs = (
        [c.strip() for c in cert_str.replace(";", ",").split(",") if c.strip()]
        if cert_str
        else []
    )

    record: dict[str, Any] = {
        "declaration_number": row.get("declaration_number", "").strip(),
        "hs_code": hs_raw,
        "importer_name": row.get("importer_name", "").strip(),
        "importer_cr": row.get("importer_cr", "").strip(),
        "origin_country": country,
        "declared_value_sar": declared_value,
        "weight_kg": weight,
        "port_of_entry": row.get("port_of_entry", "").strip(),
        "declaration_date": row.get("declaration_date", "").strip(),
        "required_certificates": certs,
    }
    return record, []


# ── Public API ────────────────────────────────────────────────────────────────

def parse_csv(file_path: Path) -> dict[str, Any]:
    """
    Parse a Tabadol CSV export. Returns a ParseResult-compatible dict.

    تحليل ملف CSV لصادرات تبادل. يعيد قاموساً متوافقاً مع ParseResult.

    Output schema mirrors ``fasah-engine parse`` stdout:
    {
        "total_records": int,
        "valid_records": int,
        "invalid_records": int,
        "records": [...],
        "errors": [...],
        "content_hash": "hex"
    }
    """
    log.warning(
        "[DEGRADED] Python fallback CSV parser active for '%s' (Rust engine unavailable)",
        file_path.name,
    )

    try:
        content_hash = _sha256_file(file_path)
    except OSError as exc:
        log.error("Cannot hash '%s': %s", file_path, exc)
        return {
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "records": [],
            "errors": [f"File read error: {exc}"],
            "content_hash": "",
        }

    records: list[dict[str, Any]] = []
    all_errors: list[str] = []
    row_error_count = 0

    try:
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                return {
                    "total_records": 0,
                    "valid_records": 0,
                    "invalid_records": 0,
                    "records": [],
                    "errors": ["Cannot read CSV headers — file may be empty"],
                    "content_hash": content_hash,
                }

            missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames)
            if missing:
                log.error("CSV missing required columns: %s", sorted(missing))
                all_errors.append(f"Missing required columns: {sorted(missing)}")

            for line_num, row in enumerate(reader, start=2):
                record, errs = _validate_record(dict(row), line_num)
                if record:
                    records.append(record)
                else:
                    all_errors.extend(errs)
                    row_error_count += 1
                    log.warning("Skipping invalid row %d: %s", line_num, errs)

    except OSError as exc:
        log.error("Cannot read '%s': %s", file_path, exc)
        all_errors.append(f"File read error: {exc}")

    return {
        "total_records": len(records) + row_error_count,
        "valid_records": len(records),
        "invalid_records": row_error_count,
        "records": records,
        "errors": all_errors,
        "content_hash": content_hash,
    }


def parse_json(file_path: Path) -> dict[str, Any]:
    """
    Parse a Tabadol JSON export. Returns a ParseResult-compatible dict.

    تحليل ملف JSON لصادرات تبادل.
    """
    log.warning(
        "[DEGRADED] Python fallback JSON parser active for '%s' (Rust engine unavailable)",
        file_path.name,
    )

    content_hash = _sha256_file(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            records = data
        elif isinstance(data, dict) and "records" in data:
            records = data["records"]
        else:
            records = [data]

        return {
            "total_records": len(records),
            "valid_records": len(records),
            "invalid_records": 0,
            "records": records,
            "errors": [],
            "content_hash": content_hash,
        }

    except Exception as exc:
        log.error("Cannot parse JSON '%s': %s", file_path, exc)
        return {
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "records": [],
            "errors": [str(exc)],
            "content_hash": content_hash,
        }


def parse_file(file_path: Path) -> dict[str, Any]:
    """
    Auto-detect file type and parse. Mirrors ``fasah-engine parse <file>``.

    الكشف التلقائي عن نوع الملف والمعالجة. يحاكي أمر ``fasah-engine parse``.
    """
    if file_path.suffix.lower() == ".json":
        return parse_json(file_path)
    return parse_csv(file_path)
