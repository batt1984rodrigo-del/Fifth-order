from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_inventory(input_path: Path, *, case_id: str) -> dict[str, Any]:
    files = [input_path] if input_path.is_file() else sorted(p for p in input_path.rglob("*") if p.is_file())
    evidence = []
    for index, path in enumerate(files, start=1):
        evidence.append(
            {
                "artifact_id": f"EVD-{index:03d}",
                "original_location_ref": str(path.resolve()),
                "public_description": path.name,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "modified_original": False,
                "derived_copy_ref": None,
                "extraction_status": "skipped",
                "notes": [],
            }
        )
    return {
        "case_id": case_id,
        "case_type": "closed_legal_or_administrative_case",
        "custody_notice": "Original evidence is not stored in the public repository. This file records controlled metadata and hashes only.",
        "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a SHA-256 evidence inventory.")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    inventory = build_inventory(args.input_path, case_id=args.case_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
