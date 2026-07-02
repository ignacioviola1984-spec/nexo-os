"""Release identity and production rollback safety.

A release manifest records what is deployed: service version, git sha, environment, and
a **schema fingerprint** derived from the canonical schema. Rollback is only safe when
the target release shares the current schema fingerprint - rolling a service back across
a schema change without a down-migration corrupts data, so ``plan_rollback`` blocks it
and says so. This is the deterministic check the deploy pipeline (docs/DEPLOYMENT.md)
runs before it flips traffic back.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from nexo_os.config import Settings, get_settings
from nexo_os.data.schema_def import ALL_TABLES


def schema_fingerprint() -> str:
    """Stable short hash of the canonical schema (table + column names + types). Any
    additive or breaking schema change moves this, flagging cross-schema rollbacks."""
    parts: list[str] = []
    for t in sorted(ALL_TABLES, key=lambda x: x.name):
        cols = ",".join(f"{c.name}:{c.bq_type}" for c in t.columns)
        parts.append(f"{t.name}({cols})")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    git_sha: str | None
    environment: str
    schema_fingerprint: str
    tenant_id: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> ReleaseManifest:
        data = json.loads(text)
        return cls(
            version=data["version"],
            git_sha=data.get("git_sha"),
            environment=data["environment"],
            schema_fingerprint=data["schema_fingerprint"],
            tenant_id=data.get("tenant_id", "default"),
        )


def current_manifest(settings: Settings | None = None) -> ReleaseManifest:
    settings = settings or get_settings()
    return ReleaseManifest(
        version=settings.service_version,
        git_sha=settings.git_sha,
        environment=settings.environment.value,
        schema_fingerprint=schema_fingerprint(),
        tenant_id=settings.tenant_id,
    )


def write_manifest(path: Path, settings: Settings | None = None) -> ReleaseManifest:
    manifest = current_manifest(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json(), encoding="utf-8")
    return manifest


def load_manifest(path: Path) -> ReleaseManifest:
    return ReleaseManifest.from_json(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RollbackPlan:
    ok: bool
    target_version: str
    current_version: str
    reasons: list[str]


def plan_rollback(target: ReleaseManifest, current: ReleaseManifest | None = None) -> RollbackPlan:
    """Decide whether rolling back to ``target`` is safe from ``current``."""
    current = current or current_manifest()
    reasons: list[str] = []
    if target.schema_fingerprint != current.schema_fingerprint:
        reasons.append(
            f"schema fingerprint differs (target {target.schema_fingerprint} vs "
            f"current {current.schema_fingerprint}); a down-migration is required first."
        )
    if target.tenant_id != current.tenant_id:
        reasons.append(
            f"tenant mismatch (target {target.tenant_id} vs current {current.tenant_id})."
        )
    if target.environment != current.environment:
        reasons.append(
            f"environment mismatch (target {target.environment} vs current {current.environment})."
        )
    return RollbackPlan(
        ok=not reasons,
        target_version=target.version,
        current_version=current.version,
        reasons=reasons,
    )
