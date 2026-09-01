from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from job_storage import JobStore


def _write_bytes(path: Path, size: int, *, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


class JobStorageCleanupTests(unittest.TestCase):
    def test_cleanup_preserves_active_and_expires_terminal_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = 1_000_000.0
            store = JobStore(
                root,
                job_ttl_seconds=100,
                storage_cap_bytes=10_000,
                upload_ttl_seconds=100,
            )
            store.create_job("active", status="running")
            store.create_job("done", status="completed")
            store.create_job("failed", status="failed")

            for job_id in ("done", "failed"):
                path = root / "jobs" / job_id / "job.json"
                record = json.loads(path.read_text())
                record["updated_at"] = "1970-01-01T00:00:00+00:00"
                path.write_text(json.dumps(record))

            report = store.cleanup(now=now)

            self.assertEqual(report.deleted_jobs, 2)
            self.assertTrue((root / "jobs" / "active").exists())
            self.assertFalse((root / "jobs" / "done").exists())
            self.assertFalse((root / "jobs" / "failed").exists())

    def test_storage_cap_removes_oldest_terminal_jobs_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            creator = JobStore(
                root,
                job_ttl_seconds=10_000,
                storage_cap_bytes=10_000,
            )
            creator.create_job("active", status="running")
            creator.create_job("old", status="completed")
            creator.create_job("new", status="completed")

            old_path = root / "jobs" / "old" / "payload.bin"
            new_path = root / "jobs" / "new" / "payload.bin"
            _write_bytes(old_path, 100, mtime=1)
            _write_bytes(new_path, 100, mtime=2)

            cleaner = JobStore(
                root,
                job_ttl_seconds=10_000,
                storage_cap_bytes=450,
            )
            report = cleaner.cleanup(now=time.time())

            self.assertGreaterEqual(report.deleted_jobs, 1)
            self.assertTrue((root / "jobs" / "active").exists())
            self.assertFalse((root / "jobs" / "old").exists())

    def test_old_upload_chunks_are_removed_but_recent_chunks_remain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = 1_000.0
            store = JobStore(
                root,
                job_ttl_seconds=10_000,
                storage_cap_bytes=10_000,
                upload_ttl_seconds=100,
            )
            old_chunk = root / "uploads" / "chunks" / "old.part"
            recent_chunk = root / "uploads" / "chunks" / "recent.part"
            _write_bytes(old_chunk, 5, mtime=now - 101)
            _write_bytes(recent_chunk, 5, mtime=now - 1)

            report = store.cleanup(now=now)

            self.assertEqual(report.deleted_upload_chunks, 1)
            self.assertFalse(old_chunk.exists())
            self.assertTrue(recent_chunk.exists())


if __name__ == "__main__":
    unittest.main()