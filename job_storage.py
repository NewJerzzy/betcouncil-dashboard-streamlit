"""Small, bounded storage layer for project-owned background jobs.

The project currently has source refresh scripts but no central persistent job
store.  This module provides one for future jobs without treating Replit's
platform caches, GitHub Gists, or user assets as disposable application data.

Storage layout (all project-owned):

    .runtime/
      jobs/<job-id>/job.json
      uploads/chunks/<temporary upload pieces>
      logs/<application logs>

Cleanup rules:

* Jobs whose status is active are never removed by retention or cap cleanup.
* Completed, failed, and cancelled jobs are removed after the terminal-job TTL.
* If the job directory exceeds its byte cap, oldest terminal jobs are removed
  first.  Active jobs are preserved even when the cap cannot be met.
* Temporary upload chunks are removed after their shorter upload TTL.
* Only the three directories above are inspected.  In particular, this module
  never walks .cache, .pythonlibs, node_modules, artifacts, or other
  platform/dependency-managed directories.

The defaults can be adjusted with environment variables:

    BETCOUNCIL_RUNTIME_DIR
    BETCOUNCIL_JOB_TTL_SECONDS       (default: 7 days)
    BETCOUNCIL_JOB_STORAGE_CAP_BYTES (default: 256 MiB)
    BETCOUNCIL_UPLOAD_TTL_SECONDS    (default: 6 hours)
    BETCOUNCIL_LOG_TTL_SECONDS       (default: 14 days)
    BETCOUNCIL_LOG_STORAGE_CAP_BYTES (default: 64 MiB)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_logger = logging.getLogger("betcouncil.job_storage")

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / ".runtime"

ACTIVE_JOB_STATUSES = frozenset(
    {"queued", "pending", "running", "active", "processing", "retrying"}
)
TERMINAL_JOB_STATUSES = frozenset(
    {"completed", "succeeded", "failed", "cancelled", "canceled", "error"}
)

DEFAULT_JOB_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_JOB_STORAGE_CAP_BYTES = 256 * 1024 * 1024
DEFAULT_UPLOAD_TTL_SECONDS = 6 * 60 * 60
DEFAULT_LOG_TTL_SECONDS = 14 * 24 * 60 * 60
DEFAULT_LOG_STORAGE_CAP_BYTES = 64 * 1024 * 1024


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    """Read a non-negative integer environment setting safely."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        _logger.warning("Ignoring invalid %s=%r; using %d", name, raw, default)
        return default


def _utc_iso(timestamp: float | None = None) -> str:
    value = time.time() if timestamp is None else timestamp
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _timestamp(value: Any, fallback: float) -> float:
    """Convert stored ISO/numeric timestamps; malformed values use fallback."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            normalized = value.strip().replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            pass
    return fallback


def _safe_job_id(job_id: str) -> str:
    value = str(job_id).strip()
    if not value or value in {".", ".."} or Path(value).name != value:
        raise ValueError("job_id must be a non-empty single path component")
    return value


def _within_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _directory_size(directory: Path) -> int:
    total = 0
    if not directory.exists():
        return 0
    for path in directory.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class CleanupReport:
    deleted_jobs: int = 0
    deleted_upload_chunks: int = 0
    deleted_log_files: int = 0
    bytes_reclaimed: int = 0
    job_storage_bytes: int = 0
    job_storage_cap_bytes: int = DEFAULT_JOB_STORAGE_CAP_BYTES
    cap_exceeded_by_active_jobs: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobStore:
    """Filesystem-backed job store with safe, bounded cleanup."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        *,
        job_ttl_seconds: int | None = None,
        storage_cap_bytes: int | None = None,
        upload_ttl_seconds: int | None = None,
        log_ttl_seconds: int | None = None,
        log_storage_cap_bytes: int | None = None,
    ) -> None:
        configured_root = root or os.environ.get("BETCOUNCIL_RUNTIME_DIR")
        self.root = Path(configured_root or DEFAULT_RUNTIME_DIR)
        self.jobs_dir = self.root / "jobs"
        self.upload_chunks_dir = self.root / "uploads" / "chunks"
        self.logs_dir = self.root / "logs"

        self.job_ttl_seconds = (
            DEFAULT_JOB_TTL_SECONDS
            if job_ttl_seconds is None
            else max(0, int(job_ttl_seconds))
        )
        self.storage_cap_bytes = (
            DEFAULT_JOB_STORAGE_CAP_BYTES
            if storage_cap_bytes is None
            else max(0, int(storage_cap_bytes))
        )
        self.upload_ttl_seconds = (
            DEFAULT_UPLOAD_TTL_SECONDS
            if upload_ttl_seconds is None
            else max(0, int(upload_ttl_seconds))
        )
        self.log_ttl_seconds = (
            DEFAULT_LOG_TTL_SECONDS
            if log_ttl_seconds is None
            else max(0, int(log_ttl_seconds))
        )
        self.log_storage_cap_bytes = (
            DEFAULT_LOG_STORAGE_CAP_BYTES
            if log_storage_cap_bytes is None
            else max(0, int(log_storage_cap_bytes))
        )

    def _ensure_directories(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.upload_chunks_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / _safe_job_id(job_id)

    def _job_metadata_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job.json"

    def create_job(
        self,
        job_id: str,
        *,
        status: str = "queued",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or replace a job metadata record and run bounded cleanup."""
        job_id = _safe_job_id(job_id)
        now = _utc_iso()
        record: dict[str, Any] = {
            "id": job_id,
            "status": status,
            "created_at": now,
            "updated_at": now,
            "metadata": dict(metadata or {}),
        }
        _atomic_json_write(self._job_metadata_path(job_id), record)
        self.cleanup()
        return record

    def load_job(self, job_id: str) -> dict[str, Any] | None:
        path = self._job_metadata_path(job_id)
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else None
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Update a job record and immediately enforce retention/cap rules."""
        record = self.load_job(job_id)
        if record is None:
            return None
        if status is not None:
            record["status"] = status
        if fields:
            record.update(fields)
        record["updated_at"] = _utc_iso()
        if status in TERMINAL_JOB_STATUSES:
            record.setdefault("finished_at", record["updated_at"])
        _atomic_json_write(self._job_metadata_path(job_id), record)
        self.cleanup()
        return record

    def cleanup(self, *, now: float | None = None) -> CleanupReport:
        """Apply retention, upload cleanup, and terminal-job storage cap."""
        self._ensure_directories()
        current_time = time.time() if now is None else float(now)
        deleted_jobs = 0
        deleted_upload_chunks = 0
        deleted_log_files = 0
        bytes_reclaimed = 0

        deleted_upload_chunks, upload_bytes = self._cleanup_old_files(
            self.upload_chunks_dir,
            current_time - self.upload_ttl_seconds,
        )
        deleted_log_files, log_bytes = self._cleanup_old_files(
            self.logs_dir,
            current_time - self.log_ttl_seconds,
        )
        bytes_reclaimed += upload_bytes + log_bytes
        bytes_reclaimed += self._trim_directory_by_cap(
            self.logs_dir,
            self.log_storage_cap_bytes,
        )

        terminal_candidates: list[tuple[float, Path, int]] = []
        for job_dir in sorted(self.jobs_dir.iterdir()):
            if not job_dir.is_dir() or job_dir.is_symlink():
                continue
            metadata_path = job_dir / "job.json"
            try:
                with metadata_path.open("r", encoding="utf-8") as handle:
                    record = json.load(handle)
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                # Unknown or damaged job records are protected.  Automatic
                # cleanup must not guess that a job is safe to delete.
                continue
            if not isinstance(record, dict):
                continue

            size = _directory_size(job_dir)
            status = str(record.get("status", "")).strip().lower()
            updated_at = _timestamp(
                record.get("finished_at", record.get("updated_at")),
                job_dir.stat().st_mtime,
            )
            if status in TERMINAL_JOB_STATUSES:
                if current_time - updated_at >= self.job_ttl_seconds:
                    if self._remove_directory(job_dir):
                        deleted_jobs += 1
                        bytes_reclaimed += size
                    continue
                terminal_candidates.append((updated_at, job_dir, size))

        # The cap only removes known terminal jobs.  Active and malformed jobs
        # remain intact, and the report makes an unavoidable over-cap state
        # visible to callers.
        job_storage_bytes = _directory_size(self.jobs_dir)
        terminal_candidates.sort(key=lambda item: item[0])
        for _, job_dir, size in terminal_candidates:
            if job_storage_bytes <= self.storage_cap_bytes:
                break
            if self._remove_directory(job_dir):
                deleted_jobs += 1
                bytes_reclaimed += size
                job_storage_bytes = max(0, job_storage_bytes - size)

        remaining_terminal_bytes = sum(
            item[2] for item in terminal_candidates if item[1].exists()
        )
        protected_bytes = max(0, job_storage_bytes - remaining_terminal_bytes)
        # The cap deliberately does not delete active or malformed records; the
        # flag makes that unavoidable over-cap state visible to callers.
        cap_exceeded_by_active_jobs = (
            job_storage_bytes > self.storage_cap_bytes
            and protected_bytes > self.storage_cap_bytes
        )

        return CleanupReport(
            deleted_jobs=deleted_jobs,
            deleted_upload_chunks=deleted_upload_chunks,
            deleted_log_files=deleted_log_files,
            bytes_reclaimed=bytes_reclaimed,
            job_storage_bytes=job_storage_bytes,
            job_storage_cap_bytes=self.storage_cap_bytes,
            cap_exceeded_by_active_jobs=cap_exceeded_by_active_jobs,
        )

    def _cleanup_old_files(
        self, directory: Path, cutoff: float
    ) -> tuple[int, int]:
        deleted = 0
        reclaimed = 0
        for path in directory.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                stat = path.stat()
                if stat.st_mtime >= cutoff:
                    continue
                if not _within_directory(path, directory):
                    continue
                size = stat.st_size
                path.unlink()
                deleted += 1
                reclaimed += size
            except OSError:
                _logger.warning("Could not remove expired file %s", path)
        return deleted, reclaimed

    def _trim_directory_by_cap(
        self,
        directory: Path,
        cap_bytes: int,
    ) -> int:
        reclaimed = 0
        current_size = _directory_size(directory)
        if current_size <= cap_bytes:
            return 0
        files: list[tuple[float, Path, int]] = []
        for path in directory.rglob("*"):
            if path.is_file() and not path.is_symlink():
                try:
                    stat = path.stat()
                    files.append((stat.st_mtime, path, stat.st_size))
                except OSError:
                    continue
        files.sort(key=lambda item: item[0])
        for _, path, size in files:
            if current_size <= cap_bytes:
                break
            try:
                path.unlink()
                current_size -= size
                reclaimed += size
            except OSError:
                _logger.warning("Could not trim log file %s", path)
        return reclaimed

    @staticmethod
    def _remove_directory(path: Path) -> bool:
        try:
            shutil.rmtree(path)
            return True
        except OSError:
            _logger.warning("Could not remove expired job directory %s", path)
            return False


def cleanup_project_storage() -> dict[str, Any]:
    """Run the safe project-owned cleanup used by app startup."""
    report = JobStore(
        job_ttl_seconds=_env_int(
            "BETCOUNCIL_JOB_TTL_SECONDS", DEFAULT_JOB_TTL_SECONDS
        ),
        storage_cap_bytes=_env_int(
            "BETCOUNCIL_JOB_STORAGE_CAP_BYTES", DEFAULT_JOB_STORAGE_CAP_BYTES
        ),
        upload_ttl_seconds=_env_int(
            "BETCOUNCIL_UPLOAD_TTL_SECONDS", DEFAULT_UPLOAD_TTL_SECONDS
        ),
        log_ttl_seconds=_env_int(
            "BETCOUNCIL_LOG_TTL_SECONDS", DEFAULT_LOG_TTL_SECONDS
        ),
        log_storage_cap_bytes=_env_int(
            "BETCOUNCIL_LOG_STORAGE_CAP_BYTES",
            DEFAULT_LOG_STORAGE_CAP_BYTES,
        ),
    )
    return report.cleanup().to_dict()


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "TERMINAL_JOB_STATUSES",
    "CleanupReport",
    "JobStore",
    "cleanup_project_storage",
]