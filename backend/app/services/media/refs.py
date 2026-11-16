from dataclasses import dataclass
from typing import Any

from ...domain.models import Material


@dataclass(frozen=True)
class MediaRef:
    material_id: str
    blob_sha: str | None
    mime: str | None
    duration_ms: int

    @classmethod
    def from_material(cls, material: Material) -> "MediaRef":
        return cls(
            material_id=material.id,
            blob_sha=material.blob_sha,
            mime=material.mime,
            duration_ms=int((material.duration_sec or 0) * 1000),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "blob_sha": self.blob_sha,
            "mime": self.mime,
            "duration_ms": self.duration_ms,
        }
