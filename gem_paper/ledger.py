"""Local append-only audit chain with exclusive lock and durable writes.

This is tamper-evident relative to a trusted checkpoint, not WORM storage.
Callers must retain checkpoints outside the writer's trust domain in release.
"""
import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from .common import ControlError, canonical, digest, utc

ZERO_HASH = "0" * 64


class AuditLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        if not self.path.parent.is_dir():
            raise ControlError("Ledger directory must exist")

    @contextmanager
    def _lock(self):
        # O_NOFOLLOW prevents redirection through a substituted leaf symlink.
        flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
        fd = os.open(self.lock_path, flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self):
        if not self.path.exists():
            if self.path.is_symlink():
                raise ControlError("Symlinked ledger")
            return []
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read()
        if raw and not raw.endswith(b"\n"):
            raise ControlError("Incomplete ledger tail; manual recovery required")
        records, previous, keys = [], ZERO_HASH, set()
        for sequence, line in enumerate(raw.splitlines(), 1):
            try:
                record = json.loads(line)
                if set(record) != {"sequence", "previous_hash", "record_hash", "event_type",
                                   "idempotency_key", "recorded_at", "payload"}:
                    raise ControlError("Invalid ledger record schema")
                body = {key: value for key, value in record.items() if key != "record_hash"}
                if canonical(record) != line:
                    raise ControlError("Noncanonical ledger encoding")
                if record["sequence"] != sequence or record["previous_hash"] != previous:
                    raise ControlError("Broken ledger sequence/hash chain")
                if record["record_hash"] != digest(body):
                    raise ControlError("Ledger payload/hash mismatch")
                if not isinstance(record["event_type"], str) or not record["event_type"]:
                    raise ControlError("Missing ledger event type")
                if not isinstance(record["idempotency_key"], str) or not record["idempotency_key"]:
                    raise ControlError("Missing ledger idempotency key")
                if record["idempotency_key"] in keys:
                    raise ControlError("Duplicate ledger idempotency key")
                utc(record["recorded_at"])
            except (ValueError, KeyError, TypeError) as exc:
                if isinstance(exc, ControlError):
                    raise
                raise ControlError("Unreadable ledger record") from exc
            keys.add(record["idempotency_key"])
            previous = record["record_hash"]
            records.append(record)
        return records

    @staticmethod
    def _checkpoint(records):
        return {"sequence": len(records),
                "record_hash": records[-1]["record_hash"] if records else ZERO_HASH}

    def read(self, *, expected_checkpoint=None):
        with self._lock():
            records = self._read()
            if expected_checkpoint is not None and self._checkpoint(records) != expected_checkpoint:
                raise ControlError("Trusted checkpoint mismatch; truncation/rewrite possible")
            return records

    def checkpoint(self):
        with self._lock():
            return self._checkpoint(self._read())

    def append(self, event_type, payload, *, idempotency_key, recorded_at):
        if not isinstance(event_type, str) or not event_type:
            raise ControlError("Missing event type")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ControlError("Missing idempotency key")
        utc(recorded_at)
        # Canonicalization rejects NaN/non-JSON payloads before storage access.
        semantic = canonical({"event_type": event_type, "payload": payload})
        with self._lock():
            records = self._read()  # any tamper/partial write blocks more writes
            for record in records:
                if record["idempotency_key"] == idempotency_key:
                    existing = canonical({"event_type": record["event_type"], "payload": record["payload"]})
                    if existing != semantic:
                        raise ControlError("Idempotency key reused for different content")
                    return record
            record = {"sequence": len(records) + 1,
                      "previous_hash": records[-1]["record_hash"] if records else ZERO_HASH,
                      "event_type": event_type, "payload": payload,
                      "idempotency_key": idempotency_key, "recorded_at": recorded_at}
            record["record_hash"] = digest(record)
            data = canonical(record) + b"\n"
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            try:
                offset = 0
                while offset < len(data):
                    written = os.write(fd, data[offset:])
                    if not written:
                        raise OSError("Short audit-ledger write")
                    offset += written
                os.fsync(fd)
            finally:
                os.close(fd)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return record
