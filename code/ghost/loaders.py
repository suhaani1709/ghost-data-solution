"""Load the participant-facing CSV files under dataset/.

Every column is read as a string with empty cells kept as "" (never NaN), so
phones, hashes and timestamps are never coerced. Column names are checked
against the real headers; a mismatch raises instead of silently continuing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

import pandas as pd

PathLike = Optional[Union[str, Path]]

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

REQUEST_COLUMNS = ["case_id", "email", "requested_at", "reported_status",
                   "reported_at", "audit_at", "request_text"]
OUTPUT_COLUMNS = ["case_id", "deletion_status", "steps_json"]
IDENTITY_COLUMNS = ["user_id", "name", "email", "phone", "email_hash", "updated_at"]
AUDIT_LOG_COLUMNS = ["audit_id", "user_id", "event_time", "field_name",
                     "old_value", "new_value"]
ACTIVITY_COLUMNS = ["activity_id", "event_time", "event_type", "source_system",
                    "target_system", "resource_id", "reported_result", "details"]
RULE_COLUMNS = ["rule_id", "data_category", "condition", "required_action"]
EVIDENCE_FILE_COLUMNS = ["file_id", "file_path", "origin", "captured_at"]


def case_sort_key(case_id: str) -> tuple:
    """Numeric case order (case_9 < case_10 < case_100), the order of deletion_requests.csv."""
    prefix, _, number = case_id.rpartition("_")
    return (prefix, int(number)) if number.isdigit() else (case_id, -1)


def sort_case_ids(case_ids: Iterable[str]) -> list[str]:
    return sorted(case_ids, key=case_sort_key)


def _read(name: str, columns: list[str], dataset_dir: PathLike = None) -> pd.DataFrame:
    path = Path(dataset_dir or DATASET_DIR) / name
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    if list(df.columns) != columns:
        raise ValueError(f"{path}: expected columns {columns}, got {list(df.columns)}")
    return df


def load_deletion_requests(dataset_dir: PathLike = None) -> pd.DataFrame:
    """The 518 evaluation requests."""
    return _read("deletion_requests.csv", REQUEST_COLUMNS, dataset_dir)


def load_sample_requests(dataset_dir: PathLike = None) -> pd.DataFrame:
    """The 32 public sample requests."""
    return _read("sample_deletion_requests.csv", REQUEST_COLUMNS, dataset_dir)


def load_sample_output(dataset_dir: PathLike = None) -> pd.DataFrame:
    """Correct outputs for the 32 sample requests."""
    return _read("sample_output.csv", OUTPUT_COLUMNS, dataset_dir)


def load_output_template(dataset_dir: PathLike = None) -> pd.DataFrame:
    """The blank prediction template (header only)."""
    return _read("output.csv", OUTPUT_COLUMNS, dataset_dir)


def load_user_identities(dataset_dir: PathLike = None) -> pd.DataFrame:
    """Current identity snapshot, one row per user."""
    return _read("user_identities.csv", IDENTITY_COLUMNS, dataset_dir)


def load_user_audit_log(dataset_dir: PathLike = None) -> pd.DataFrame:
    """Historical identity-field changes (email, email_hash, phone)."""
    return _read("user_audit_log.csv", AUDIT_LOG_COLUMNS, dataset_dir)


def load_system_activity(dataset_dir: PathLike = None) -> pd.DataFrame:
    """Global activity stream. Results in it are claims, not proof."""
    return _read("system_activity.csv", ACTIVITY_COLUMNS, dataset_dir)


def load_deletion_rules(dataset_dir: PathLike = None) -> pd.DataFrame:
    """Policy: data_category + condition -> required_action."""
    return _read("deletion_rules.csv", RULE_COLUMNS, dataset_dir)


def load_evidence_files(dataset_dir: PathLike = None) -> pd.DataFrame:
    """Manifest of evidence files (paths are relative to dataset/)."""
    return _read("evidence_files.csv", EVIDENCE_FILE_COLUMNS, dataset_dir)


def missing_evidence(dataset_dir: PathLike = None) -> list[str]:
    """Manifest paths with no file on disk. The run stops when any is missing, so no output is
    ever built on a partial evidence picture."""
    root = Path(dataset_dir or DATASET_DIR)
    return [f for f in load_evidence_files(dataset_dir).file_path if not (root / f).is_file()]


def load_all(dataset_dir: PathLike = None) -> dict[str, pd.DataFrame]:
    """Every CSV in dataset/, keyed by a short name."""
    return {
        "requests": load_deletion_requests(dataset_dir),
        "sample_requests": load_sample_requests(dataset_dir),
        "sample_output": load_sample_output(dataset_dir),
        "output_template": load_output_template(dataset_dir),
        "identities": load_user_identities(dataset_dir),
        "audit_log": load_user_audit_log(dataset_dir),
        "activity": load_system_activity(dataset_dir),
        "rules": load_deletion_rules(dataset_dir),
        "evidence_files": load_evidence_files(dataset_dir),
    }
