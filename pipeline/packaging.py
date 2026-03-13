from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipeline.processor import InputType, OutputType


@dataclass(frozen=True)
class Manifest:
    job_id: str
    input_filename: str
    input_type: str
    requested_outputs: list[str]
    generated_outputs: list[str]
    model: str
    language: str
    metrics: dict[str, Any]


def build_manifest(
    *,
    job_id: str,
    input_path: Path,
    input_type: InputType,
    requested_outputs: list[OutputType],
    artifacts: dict[OutputType, Path],
    model: str,
    language: str,
    metrics: dict[str, Any] | None = None,
) -> Manifest:
    return Manifest(
        job_id=job_id,
        input_filename=input_path.name,
        input_type=input_type.value,
        requested_outputs=[o.value for o in requested_outputs],
        generated_outputs=[o.value for o in artifacts.keys()],
        model=model,
        language=language,
        metrics=metrics or {},
    )


def create_results_zip(
    *,
    output_dir: Path,
    job_id: str,
    artifacts: dict[OutputType, Path],
    manifest: Manifest,
) -> Path:
    """
    Create results_<job_id>.zip in output_dir containing:
    - generated artifact files
    - manifest.json
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = output_dir / f"results_{job_id}.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # add artifacts
        for out_type, file_path in artifacts.items():
            file_path = Path(file_path)
            arcname = file_path.name  # keep flat structure
            zf.write(file_path, arcname=arcname)

        # add manifest.json
        manifest_bytes = json.dumps(asdict(manifest), ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr("manifest.json", manifest_bytes)

    return zip_path