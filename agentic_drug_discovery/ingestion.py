"""Deterministic capture and compilation for source-pinned evidence manifests."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pinned_evidence import (
    PINNED_EVIDENCE_SCHEMA_VERSION,
    normalize_pinned_evidence_manifest,
)


SOURCE_RECEIPT_SCHEMA_VERSION = "adds.source-receipt.v1"
INGESTION_JOB_SCHEMA_VERSION = "adds.pinned-ingestion-job.v1"
INGESTION_REVIEW_SCHEMA_VERSION = "adds.pinned-ingestion-review.v1"
SOURCE_BUNDLE_RECEIPT = "receipt.json"
SOURCE_BUNDLE_PAYLOAD = "payload.bin"
DEFAULT_MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FORBIDDEN_VERSION_TERMS = ("latest", "current", "unknown", "unpinned")
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "key",
        "secret",
        "signature",
        "token",
    }
)
_SENSITIVE_QUERY_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_authorization",
    "_credential",
    "_secret",
    "_signature",
    "_token",
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "source",
        "retrieved_at",
        "byte_size",
        "media_type",
        "transport",
    }
)
_SOURCE_FIELDS = frozenset(
    {"source_id", "source_version", "locator", "content_hash"}
)
_TRANSPORT_FIELDS = frozenset(
    {"method", "http_status", "etag", "last_modified"}
)
_JOB_FIELDS = frozenset({"schema_version", "job_id", "records"})
_JOB_RECORD_FIELDS = frozenset(
    {
        "source_receipt_id",
        "record_id",
        "predicate",
        "subject",
        "object_value",
        "observed_at",
        "available_at",
        "confidence",
        "biological_context",
        "metadata",
    }
)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _sequence(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an array")
    return list(value)


def _safe_id(value: Any, field_name: str) -> str:
    text = _text(value, field_name)
    if _SAFE_ID.fullmatch(text) is None:
        raise ValueError(
            f"{field_name} must use only letters, numbers, dot, underscore, or hyphen"
        )
    return text


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _sha256(value: Any, field_name: str) -> str:
    text = _text(value, field_name)
    if len(text) != 64 or text != text.lower():
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    try:
        int(text, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest") from exc
    return text


def _utc_datetime(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_source_version(value: Any) -> str:
    text = _text(value, "source_version")
    normalized = text.casefold()
    if any(term in normalized for term in _FORBIDDEN_VERSION_TERMS):
        raise ValueError("source_version must identify an immutable source revision")
    return text


def _validate_locator(value: Any, *, allow_fixture: bool) -> str:
    locator = _text(value, "locator")
    if any(fragment in locator for fragment in ("/Users/", "/home/", "\\Users\\")):
        raise ValueError("locator must not contain a machine-local path")
    parsed = urllib.parse.urlsplit(locator)
    allowed = {"https", "doi", "urn"}
    if allow_fixture:
        allowed.add("fixture")
    if parsed.scheme.casefold() not in allowed:
        raise ValueError("locator must use https, doi, urn, or an allowed fixture scheme")
    if parsed.scheme.casefold() == "https":
        if not parsed.netloc or parsed.username is not None or parsed.password is not None:
            raise ValueError("https locator must identify a public host without credentials")
        for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            normalized_key = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
            if normalized_key in _SENSITIVE_QUERY_KEYS or normalized_key.endswith(
                _SENSITIVE_QUERY_SUFFIXES
            ):
                raise ValueError("locator query must not contain credential-like parameters")
    return locator


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable, newline-terminated UTF-8 JSON bytes."""

    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class SourceReceipt:
    """Payload-free receipt for one exact source snapshot."""

    receipt_id: str
    source_id: str
    source_version: str
    locator: str
    content_hash: str
    byte_size: int
    retrieved_at: datetime
    media_type: str
    capture_method: str
    http_status: int | None = None
    etag: str | None = None
    last_modified: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", _safe_id(self.receipt_id, "receipt_id"))
        object.__setattr__(self, "source_id", _text(self.source_id, "source_id"))
        object.__setattr__(
            self,
            "source_version",
            _validate_source_version(self.source_version),
        )
        method = _text(self.capture_method, "capture_method").casefold()
        if method not in {"https", "local_file"}:
            raise ValueError("capture_method must be https or local_file")
        object.__setattr__(self, "capture_method", method)
        object.__setattr__(
            self,
            "locator",
            _validate_locator(self.locator, allow_fixture=method == "local_file"),
        )
        object.__setattr__(
            self,
            "content_hash",
            _sha256(self.content_hash, "content_hash"),
        )
        if (
            not isinstance(self.byte_size, int)
            or isinstance(self.byte_size, bool)
            or self.byte_size <= 0
        ):
            raise ValueError("byte_size must be a positive integer")
        if not isinstance(self.retrieved_at, datetime):
            raise TypeError("retrieved_at must be a datetime")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")
        object.__setattr__(
            self,
            "retrieved_at",
            self.retrieved_at.astimezone(timezone.utc),
        )
        object.__setattr__(self, "media_type", _text(self.media_type, "media_type"))
        if method == "https":
            if (
                not isinstance(self.http_status, int)
                or isinstance(self.http_status, bool)
                or self.http_status != 200
            ):
                raise ValueError("https capture requires http_status 200")
        elif self.http_status is not None:
            raise ValueError("local_file capture cannot declare an HTTP status")
        for field_name in ("etag", "last_modified"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))

    @property
    def source(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "locator": self.locator,
            "content_hash": self.content_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        transport: dict[str, Any] = {"method": self.capture_method}
        if self.http_status is not None:
            transport["http_status"] = self.http_status
        if self.etag is not None:
            transport["etag"] = self.etag
        if self.last_modified is not None:
            transport["last_modified"] = self.last_modified
        return {
            "schema_version": SOURCE_RECEIPT_SCHEMA_VERSION,
            "receipt_id": self.receipt_id,
            "source": self.source,
            "retrieved_at": _timestamp(self.retrieved_at),
            "byte_size": self.byte_size,
            "media_type": self.media_type,
            "transport": transport,
        }


@dataclass(frozen=True, slots=True)
class SourceBundle:
    """Verified receipt and exact source bytes kept outside the public repository."""

    receipt: SourceReceipt
    payload: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")
        verify_source_payload(self.receipt, self.payload)


def source_receipt_from_dict(value: Any) -> SourceReceipt:
    data = _mapping(value, "receipt")
    if set(data) != _RECEIPT_FIELDS:
        raise ValueError(f"receipt must contain exactly {sorted(_RECEIPT_FIELDS)}")
    if data["schema_version"] != SOURCE_RECEIPT_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {SOURCE_RECEIPT_SCHEMA_VERSION}"
        )
    source = _mapping(data["source"], "receipt.source")
    if set(source) != _SOURCE_FIELDS:
        raise ValueError(
            f"receipt.source must contain exactly {sorted(_SOURCE_FIELDS)}"
        )
    transport = _mapping(data["transport"], "receipt.transport")
    unknown_transport = set(transport) - _TRANSPORT_FIELDS
    if unknown_transport or "method" not in transport:
        raise ValueError(
            "receipt.transport must contain method and only declared transport fields"
        )
    return SourceReceipt(
        receipt_id=data["receipt_id"],
        source_id=source["source_id"],
        source_version=source["source_version"],
        locator=source["locator"],
        content_hash=source["content_hash"],
        byte_size=data["byte_size"],
        retrieved_at=_utc_datetime(data["retrieved_at"], "retrieved_at"),
        media_type=data["media_type"],
        capture_method=transport["method"],
        http_status=transport.get("http_status"),
        etag=transport.get("etag"),
        last_modified=transport.get("last_modified"),
    )


def capture_source_bytes(
    payload: bytes,
    *,
    receipt_id: str,
    source_id: str,
    source_version: str,
    locator: str,
    retrieved_at: datetime,
    media_type: str,
    capture_method: str,
    http_status: int | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> SourceBundle:
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("source payload must be non-empty bytes")
    receipt = SourceReceipt(
        receipt_id=receipt_id,
        source_id=source_id,
        source_version=source_version,
        locator=locator,
        content_hash=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        retrieved_at=retrieved_at,
        media_type=media_type,
        capture_method=capture_method,
        http_status=http_status,
        etag=etag,
        last_modified=last_modified,
    )
    return SourceBundle(receipt=receipt, payload=payload)


def verify_source_payload(receipt: SourceReceipt, payload: bytes) -> None:
    if len(payload) != receipt.byte_size:
        raise ValueError("source payload byte size does not match its receipt")
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(digest, receipt.content_hash):
        raise ValueError("source payload SHA-256 does not match its receipt")


def _git_root_containing(path: Path) -> Path | None:
    resolved = path.resolve(strict=False)
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def write_source_bundle(path: str | Path, bundle: SourceBundle) -> Path:
    """Atomically write raw bytes and receipt outside every Git worktree."""

    output = Path(path).resolve(strict=False)
    if _git_root_containing(output) is not None:
        raise ValueError("raw source bundles must be written outside a Git worktree")
    if output.exists():
        raise ValueError("source bundle output already exists and is immutable")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        temp.chmod(0o700)
        receipt_path = temp / SOURCE_BUNDLE_RECEIPT
        payload_path = temp / SOURCE_BUNDLE_PAYLOAD
        receipt_path.write_bytes(canonical_json_bytes(bundle.receipt.to_dict()))
        payload_path.write_bytes(bundle.payload)
        receipt_path.chmod(0o600)
        payload_path.chmod(0o600)
        os.replace(temp, output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return output


def read_source_bundle(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> SourceBundle:
    limit = _positive_int(max_bytes, "max_bytes")
    source = Path(path)
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source bundle must be a non-symlink directory")
    names = {item.name for item in source.iterdir()}
    expected = {SOURCE_BUNDLE_RECEIPT, SOURCE_BUNDLE_PAYLOAD}
    if names != expected:
        raise ValueError(f"source bundle must contain exactly {sorted(expected)}")
    receipt_path = source / SOURCE_BUNDLE_RECEIPT
    payload_path = source / SOURCE_BUNDLE_PAYLOAD
    if (
        receipt_path.is_symlink()
        or payload_path.is_symlink()
        or not receipt_path.is_file()
        or not payload_path.is_file()
    ):
        raise ValueError("source bundle entries must be non-symlink files")
    try:
        with receipt_path.open("rb") as handle:
            receipt_payload = handle.read(MAX_RECEIPT_BYTES + 1)
        if len(receipt_payload) > MAX_RECEIPT_BYTES:
            raise ValueError("source bundle receipt exceeds the configured limit")
        receipt = source_receipt_from_dict(
            json.loads(receipt_payload.decode("utf-8"))
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("source bundle receipt is unreadable") from exc
    if receipt.byte_size > limit or payload_path.stat().st_size > limit:
        raise ValueError("source payload exceeds the configured size limit")
    with payload_path.open("rb") as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("source payload exceeds the configured size limit")
    return SourceBundle(receipt=receipt, payload=payload)


def capture_local_file(
    path: str | Path,
    *,
    receipt_id: str,
    source_id: str,
    source_version: str,
    locator: str,
    retrieved_at: datetime,
    media_type: str | None = None,
    max_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> SourceBundle:
    limit = _positive_int(max_bytes, "max_bytes")
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("input source must be a non-symlink file")
    size = source.stat().st_size
    if size <= 0 or size > limit:
        raise ValueError("input source size is empty or exceeds the configured limit")
    with source.open("rb") as handle:
        payload = handle.read(limit + 1)
    if not payload or len(payload) > limit:
        raise ValueError("input source size is empty or exceeds the configured limit")
    resolved_media_type = media_type or mimetypes.guess_type(source.name)[0]
    return capture_source_bytes(
        payload,
        receipt_id=receipt_id,
        source_id=source_id,
        source_version=source_version,
        locator=locator,
        retrieved_at=retrieved_at,
        media_type=resolved_media_type or "application/octet-stream",
        capture_method="local_file",
    )


def fetch_https_source(
    url: str,
    *,
    receipt_id: str,
    source_id: str,
    source_version: str,
    retrieved_at: datetime | None = None,
    timeout_seconds: float = 30.0,
    max_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> SourceBundle:
    """Fetch one public HTTPS source and pin its exact response bytes."""

    locator = _validate_locator(url, allow_fixture=False)
    if urllib.parse.urlsplit(locator).scheme.casefold() != "https":
        raise ValueError("live source capture requires an https URL")
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be positive")
    limit = _positive_int(max_bytes, "max_bytes")
    request = urllib.request.Request(
        locator,
        headers={
            "User-Agent": "agentic-drug-discovery-system/0.3 source-capture",
            "Accept": "application/json, text/csv;q=0.9, */*;q=0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
        status = response.getcode()
        if status != 200:
            raise ValueError("public source capture requires HTTP status 200")
        final_locator = _validate_locator(response.geturl(), allow_fixture=False)
        if urllib.parse.urlsplit(final_locator).scheme.casefold() != "https":
            raise ValueError("public source redirect left HTTPS")
        payload = response.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("public source payload exceeds the configured size limit")
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        media_type = content_type.split(";", 1)[0].strip()
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
    return capture_source_bytes(
        payload,
        receipt_id=receipt_id,
        source_id=source_id,
        source_version=source_version,
        locator=final_locator,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        media_type=media_type or "application/octet-stream",
        capture_method="https",
        http_status=200,
        etag=etag,
        last_modified=last_modified,
    )


def normalize_pinned_ingestion_job(value: Any) -> dict[str, Any]:
    """Validate and normalize a reviewer-authored ingestion job."""

    data = _mapping(value, "job")
    if set(data) != _JOB_FIELDS:
        raise ValueError(f"job must contain exactly {sorted(_JOB_FIELDS)}")
    if data["schema_version"] != INGESTION_JOB_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {INGESTION_JOB_SCHEMA_VERSION}")
    job_id = _safe_id(data["job_id"], "job_id")
    raw_records = _sequence(data["records"], "job.records")
    if not raw_records:
        raise ValueError("job.records must contain at least one record")
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_records):
        record = _mapping(raw, f"job.records[{index}]")
        if set(record) != _JOB_RECORD_FIELDS:
            raise ValueError(
                f"job.records[{index}] must contain exactly "
                f"{sorted(_JOB_RECORD_FIELDS)}"
            )
        records.append(
            {
                **record,
                "source_receipt_id": _safe_id(
                    record["source_receipt_id"],
                    f"job.records[{index}].source_receipt_id",
                ),
            }
        )
    return {
        "schema_version": INGESTION_JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "records": records,
    }


def compile_pinned_evidence_manifest(
    job: Any,
    bundles: Mapping[str, SourceBundle],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify source bundles and compile a payload-free manifest plus review report."""

    normalized_job = normalize_pinned_ingestion_job(job)
    if not isinstance(bundles, Mapping):
        raise ValueError("bundles must map receipt ids to SourceBundle values")
    normalized_bundles: dict[str, SourceBundle] = {}
    for key, bundle in bundles.items():
        receipt_id = _safe_id(key, "bundles receipt id")
        if not isinstance(bundle, SourceBundle):
            raise TypeError("bundles values must be SourceBundle records")
        if receipt_id != bundle.receipt.receipt_id:
            raise ValueError("bundle key must equal its receipt_id")
        verify_source_payload(bundle.receipt, bundle.payload)
        normalized_bundles[receipt_id] = bundle

    referenced_receipts = {
        record["source_receipt_id"] for record in normalized_job["records"]
    }
    unknown = sorted(referenced_receipts - set(normalized_bundles))
    unused = sorted(set(normalized_bundles) - referenced_receipts)
    if unknown:
        raise ValueError(f"job references unknown receipt ids: {', '.join(unknown)}")
    if unused:
        raise ValueError(f"bundles contain unused receipt ids: {', '.join(unused)}")

    source_definitions: dict[str, dict[str, str]] = {}
    content_hash_record_ids: dict[str, list[str]] = {}
    manifest_records: list[dict[str, Any]] = []
    receipt_record_ids: dict[str, list[str]] = {}
    source_record_ids: dict[str, list[str]] = {}
    for index, draft in enumerate(normalized_job["records"]):
        receipt = normalized_bundles[draft["source_receipt_id"]].receipt
        available_at = _text(
            draft["available_at"], f"job.records[{index}].available_at"
        )
        try:
            available_date = datetime.fromisoformat(available_at).date()
        except ValueError as exc:
            raise ValueError(
                f"job.records[{index}].available_at must be an ISO 8601 date"
            ) from exc
        if available_date > receipt.retrieved_at.date():
            raise ValueError(
                f"job.records[{index}].available_at cannot follow source retrieval"
            )
        previous_source = source_definitions.get(receipt.source_id)
        if previous_source is not None and previous_source != receipt.source:
            raise ValueError("one source_id cannot identify conflicting source receipts")
        source_definitions[receipt.source_id] = receipt.source
        record = {
            key: value
            for key, value in draft.items()
            if key != "source_receipt_id"
        }
        record["source"] = receipt.source
        manifest_records.append(record)
        receipt_record_ids.setdefault(receipt.receipt_id, []).append(record["record_id"])
        source_record_ids.setdefault(receipt.source_id, []).append(record["record_id"])
        content_hash_record_ids.setdefault(receipt.content_hash, []).append(
            record["record_id"]
        )

    manifest = normalize_pinned_evidence_manifest(
        {
            "schema_version": PINNED_EVIDENCE_SCHEMA_VERSION,
            "records": manifest_records,
        }
    )
    manifest_bytes = canonical_json_bytes(manifest)
    reused_sources = {
        source_id: sorted(record_ids)
        for source_id, record_ids in source_record_ids.items()
        if len(record_ids) > 1
    }
    reused_content_hashes = {
        content_hash: sorted(record_ids)
        for content_hash, record_ids in content_hash_record_ids.items()
        if len(record_ids) > 1
    }
    warnings = [
        "Scientific interpretation and source suitability require explicit human review."
    ]
    if reused_sources:
        warnings.append(
            "One or more records reuse a source_id; composite independence gates may defer."
        )
    if reused_content_hashes:
        warnings.append(
            "One or more records reuse exact source bytes; composite independence gates defer "
            "even when source_id values differ."
        )
    latest_retrieval = max(
        bundle.receipt.retrieved_at for bundle in normalized_bundles.values()
    )
    review = {
        "schema_version": INGESTION_REVIEW_SCHEMA_VERSION,
        "review_id": f"{normalized_job['job_id']}.review",
        "job_id": normalized_job["job_id"],
        "status": "requires_human_review",
        "compiled_at": _timestamp(latest_retrieval),
        "manifest_schema_version": PINNED_EVIDENCE_SCHEMA_VERSION,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "record_count": len(manifest["records"]),
        "receipt_count": len(normalized_bundles),
        "independent_source_count": len(content_hash_record_ids),
        "record_ids": sorted(record["record_id"] for record in manifest["records"]),
        "source_receipts": [
            normalized_bundles[receipt_id].receipt.to_dict()
            for receipt_id in sorted(normalized_bundles)
        ],
        "receipt_record_ids": {
            receipt_id: sorted(record_ids)
            for receipt_id, record_ids in sorted(receipt_record_ids.items())
        },
        "reused_source_ids": reused_sources,
        "reused_content_hashes": reused_content_hashes,
        "checks": {
            "payload_hashes_verified": True,
            "record_contract_valid": True,
            "chronology_valid": True,
            "forbidden_payload_keys_absent": True,
            "public_summary_size_limits_passed": True,
            "local_path_scan_passed": True,
        },
        "warnings": warnings,
    }
    return manifest, review


def write_json_artifact(
    path: str | Path,
    value: Any,
    *,
    force: bool = False,
) -> Path:
    """Atomically write stable JSON without silently replacing reviewed artifacts."""

    output = Path(path)
    if (output.exists() or output.is_symlink()) and not force:
        raise ValueError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=output.parent,
        prefix=f".{output.name}.",
        delete=False,
    ) as handle:
        temp = Path(handle.name)
        handle.write(canonical_json_bytes(value))
    try:
        if force:
            os.replace(temp, output)
        else:
            try:
                os.link(temp, output)
            except FileExistsError as exc:
                raise ValueError(f"output already exists: {output}") from exc
            temp.unlink()
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return output
