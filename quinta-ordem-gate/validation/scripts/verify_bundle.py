from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    errors: list[str] = []
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            errors.append(f"Invalid manifest entry: {entry!r}")
            continue
        path = root / relative
        if not path.is_file():
            errors.append(f"Missing file: {relative}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(f"Hash mismatch for {relative}: expected {expected}, got {actual}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a Quinta Ordem report bundle manifest.")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    errors = verify_manifest(args.manifest)
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("Bundle manifest verified.")


if __name__ == "__main__":
    main()
