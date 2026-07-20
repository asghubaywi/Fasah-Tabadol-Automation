"""
test_equivalence.py — Rust ⇄ Python compliance equivalence (Constitution P14).
اختبار تكافؤ محرك الامتثال بين Rust وPython

The Rust engine (`fasah-engine check`) is authoritative; the Python fallback
(`pipeline.fallback_compliance`) must produce the SAME decision for the same
input. We compare the decision-relevant fields — action, risk_score,
missing_certificates, and the aggregate counts — not the human-readable reason
prose (which is allowed to differ).

Skips automatically if the Rust binary is not built (e.g. a Python-only CI job);
build it with `cargo build` to exercise this suite.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_TESTS_DIR = Path(__file__).parent
_PROJECT_ROOT = _TESTS_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))


def _find_engine() -> Path | None:
    for candidate in (
        _PROJECT_ROOT / "target" / "release" / "fasah-engine",
        _PROJECT_ROOT / "target" / "debug" / "fasah-engine",
    ):
        if candidate.exists():
            return candidate
    return None


_ENGINE = _find_engine()
_skip = pytest.mark.skipif(_ENGINE is None, reason="fasah-engine binary not built (run: cargo build)")

_REAL_RULES = _PROJECT_ROOT / "config" / "fasah_rules.yaml"


def _record(
    decl: str,
    hs: str,
    origin: str = "CN",
    value: float = 1000.0,
    weight: float = 1000.0,
    certs: list[str] | None = None,
) -> dict:
    return {
        "declaration_number": decl,
        "hs_code": hs,
        "importer_name": "Test",
        "importer_cr": "1010000001",
        "origin_country": origin,
        "declared_value_sar": value,
        "weight_kg": weight,
        "port_of_entry": "SAJED",
        "declaration_date": "2026-02-15",
        "required_certificates": certs or [],
        "source_line": 1,
    }


# Fixtures span every decision branch and combination.
_FIXTURES = [
    _record("EQ-APPROVE", "8471.30.00", "CN", 150_000, 500, ["SASO"]),          # approve
    _record("EQ-HOLD-CERT", "0402.10.00", "NZ", 85_000, 5_000, []),             # hold (missing SFDA+Halal)
    _record("EQ-ESCALATE", "8471.60.00", "KR", 750_000, 1_200, ["SASO"]),       # escalate high value
    _record("EQ-REJECT-HS", "9301.00.00", "US", 10_000, 500, []),               # reject banned HS
    _record("EQ-MANDATE", "7204.10.00", "DE", 100_000, 60_000, []),             # mandate inspection (overweight)
    _record("EQ-HOLD+HIGHVAL", "0402.10.00", "NZ", 900_000, 100, []),           # missing cert wins over high value → hold
    _record("EQ-ESCALATE+OVERWT", "8471.30.00", "JP", 800_000, 60_000, ["SASO"]),  # high value + overweight → escalate
    _record("EQ-CHEM-HAZMAT", "2801.00.00", "IN", 5_000, 100, ["SASO"]),        # chemicals need SASO+HazMat → hold (missing HazMat)
    _record("EQ-CLEAN-CHEM", "2801.00.00", "IN", 5_000, 100, ["SASO", "HazMat"]),  # chemicals fully certified → approve
]


def _run_rust(records: list[dict], rules_path: Path, tmp_path: Path) -> dict:
    parse_result = {
        "total_records": len(records),
        "valid_records": len(records),
        "invalid_records": 0,
        "records": records,
        "errors": [],
        "content_hash": "",
    }
    infile = tmp_path / "records.json"
    infile.write_text(json.dumps(parse_result), encoding="utf-8")
    proc = subprocess.run(
        [str(_ENGINE), "check", str(infile), "--rules", str(rules_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"rust check failed: {proc.stderr}"
    return json.loads(proc.stdout)


def _run_python(records: list[dict], rules_path: Path) -> dict:
    from pipeline.fallback_compliance import check_compliance

    return check_compliance({"records": records}, str(rules_path))


def _assert_equivalent(records: list[dict], rules_path: Path, tmp_path: Path) -> None:
    rust = _run_rust(records, rules_path, tmp_path)
    py = _run_python(records, rules_path)

    # Aggregate counts must match exactly.
    for key in ("total_checked", "approved", "held", "escalated", "rejected"):
        assert rust[key] == py[key], (
            f"count '{key}' differs: rust={rust[key]} python={py[key]}"
        )

    # Per-declaration decision fields must match exactly.
    rmap = {v["declaration_number"]: v for v in rust["verdicts"]}
    pmap = {v["declaration_number"]: v for v in py["verdicts"]}
    assert rmap.keys() == pmap.keys()
    for decl, rv in rmap.items():
        pv = pmap[decl]
        assert rv["action"] == pv["action"], f"{decl}: action rust={rv['action']} py={pv['action']}"
        assert rv["risk_score"] == pv["risk_score"], (
            f"{decl}: risk rust={rv['risk_score']} py={pv['risk_score']}"
        )
        assert sorted(rv.get("missing_certificates", [])) == sorted(
            pv.get("missing_certificates", [])
        ), f"{decl}: missing_certificates differ"


@_skip
def test_equivalence_real_rules(tmp_path: Path) -> None:
    """Rust and Python agree on every branch using the shipped rules file."""
    _assert_equivalent(_FIXTURES, _REAL_RULES, tmp_path)


@_skip
def test_equivalence_sanctioned_and_prefix_union(tmp_path: Path) -> None:
    """
    Custom rules exercise the two historical divergence points:
    a populated sanctioned list, and overlapping 2-digit + 4-digit cert rules
    (Rust takes the union; the fallback must too).
    """
    custom = {
        "banned_hs_prefixes": ["9301"],
        "sanctioned_countries": ["KP", "SY"],
        "high_value_threshold_sar": 500_000.0,
        "max_weight_kg": 50_000.0,
        "certificate_requirements": {
            "84": ["SASO"],
            "8471": ["ExtraCert"],  # 4-digit rule overlaps the 2-digit chapter
        },
    }
    rules_path = tmp_path / "custom_rules.yaml"
    rules_path.write_text(yaml.safe_dump(custom), encoding="utf-8")

    records = [
        _record("EQ-SANCTIONED", "8471.30.00", "KP", 1_000, 100, ["SASO", "ExtraCert"]),  # reject_sanctioned
        _record("EQ-UNION-HOLD", "8471.30.00", "CN", 1_000, 100, ["SASO"]),               # missing ExtraCert → hold (union)
        _record("EQ-UNION-OK", "8471.30.00", "CN", 1_000, 100, ["SASO", "ExtraCert"]),    # both provided → approve
    ]
    _assert_equivalent(records, rules_path, tmp_path)
