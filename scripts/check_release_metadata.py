from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_material_preprocessor.services.release_metadata import validate_release_metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-version")
    parser.add_argument("--tag")
    args = parser.parse_args()
    result = validate_release_metadata(args.project_root.resolve())
    errors = list(result.errors)
    if args.expected_version and result.version != args.expected_version:
        errors.append(
            f"expected version {args.expected_version}, project declares {result.version}"
        )
    if args.tag and args.tag != f"v{result.version}":
        errors.append(f"tag {args.tag} does not match v{result.version}")
    print(json.dumps({"version": result.version, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
