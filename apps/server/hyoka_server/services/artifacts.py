from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hyoka_schemas.hashing import canonical_json, content_hash
from hyoka_schemas.ids import new_id
from hyoka_server.models import ArtifactRecordModel
from hyoka_server.settings import get_settings
from sqlalchemy.orm import Session


class LocalArtifactStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().artifact_root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_json(self, kind: str, payload: Any) -> tuple[str, str, str, int]:
        digest = content_hash(payload)
        artifact_id = f"art_{digest.split(':', 1)[1][:24]}"
        path = self.root / kind / f"{digest.split(':', 1)[1]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = canonical_json(payload)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(body, encoding="utf-8")
        os.replace(tmp_path, path)
        return artifact_id, digest, str(path), len(body.encode("utf-8"))

    def read_json(self, uri: str) -> str:
        return Path(uri).read_text(encoding="utf-8")


class S3ArtifactStore:
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - guarded by production configuration
            raise RuntimeError("S3 artifact backend requires boto3 to be installed") from exc
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

    def _key(self, kind: str, digest: str) -> str:
        digest_value = digest.split(":", 1)[1]
        return f"{self.prefix}/{kind}/{digest_value}.json" if self.prefix else f"{kind}/{digest_value}.json"

    def write_json(self, kind: str, payload: Any) -> tuple[str, str, str, int]:
        digest = content_hash(payload)
        artifact_id = f"art_{digest.split(':', 1)[1][:24]}"
        body = canonical_json(payload).encode("utf-8")
        key = self._key(kind, digest)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={"hyoka-content-hash": digest},
        )
        return artifact_id, digest, f"s3://{self.bucket}/{key}", len(body)

    def read_json(self, uri: str) -> str:
        prefix = "s3://"
        if not uri.startswith(prefix):
            raise ValueError(f"Unsupported S3 artifact URI: {uri}")
        bucket_and_key = uri[len(prefix) :]
        bucket, key = bucket_and_key.split("/", 1)
        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")


def artifact_store() -> LocalArtifactStore | S3ArtifactStore:
    settings = get_settings()
    if settings.artifact_backend == "local":
        return LocalArtifactStore()
    if settings.artifact_backend == "s3":
        if not settings.artifact_s3_bucket:
            raise RuntimeError("HYOKA_ARTIFACT_S3_BUCKET is required when HYOKA_ARTIFACT_BACKEND=s3")
        return S3ArtifactStore(
            bucket=settings.artifact_s3_bucket,
            prefix=settings.artifact_s3_prefix,
            region=settings.artifact_s3_region,
            endpoint_url=settings.artifact_s3_endpoint_url,
        )
    raise RuntimeError(f"Unsupported artifact backend: {settings.artifact_backend}")


def create_artifact(
    session: Session,
    *,
    kind: str,
    payload: Any,
    project_id: str = "default",
    metadata: dict[str, Any] | None = None,
) -> ArtifactRecordModel:
    store = artifact_store()
    artifact_id, digest, uri, size = store.write_json(kind, payload)
    existing = session.query(ArtifactRecordModel).filter_by(artifact_id=artifact_id).one_or_none()
    if existing:
        return existing
    record = ArtifactRecordModel(
        artifact_id=artifact_id or new_id("art"),
        project_id=project_id,
        kind=kind,
        content_hash=digest,
        uri=uri,
        size_bytes=size,
        artifact_metadata=metadata or {},
    )
    session.add(record)
    session.flush()
    return record
