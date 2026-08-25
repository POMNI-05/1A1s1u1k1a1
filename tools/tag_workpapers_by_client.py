#!/usr/bin/env python3
"""Preview and optionally persist client tags for generated workpapers.

Examples:
    python tools/tag_workpapers_by_client.py
    python tools/tag_workpapers_by_client.py --write-tags --write-index client_index.json

The default is preview-only: it does not alter any Excel workbook or metadata
file.  `--write-tags` creates/updates a metadata sidecar only when it has no
saved client name and a standard workpaper filename yields an unambiguous tag.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.workpaper_library import (  # noqa: E402
    build_client_index,
    client_tag_for_workpaper,
)

DEFAULT_ROOT = PROJECT_ROOT / "frontend" / "downloads"


def metadata_path_for(workpaper_path: Path) -> Path:
    return workpaper_path.with_suffix(".metadata.json")


def load_metadata(workpaper_path: Path) -> dict[str, Any]:
    path = metadata_path_for(workpaper_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def find_workpapers(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.xlsx")
        if not path.name.startswith("~$")
    )


def write_missing_client_tag(workpaper_path: Path) -> bool:
    """Persist a filename-inferred tag in the sidecar, never in Excel."""

    metadata = load_metadata(workpaper_path)
    client_name, source = client_tag_for_workpaper(workpaper_path, metadata)
    if source != "filename_inferred" or not client_name:
        return False

    tagged_metadata = dict(metadata)
    tagged_metadata.update(
        {
            "client_name": client_name,
            "client_tag_source": source,
            "client_tagged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    metadata_path_for(workpaper_path).write_text(
        json.dumps(tagged_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cluster generated workpapers by saved or safely inferred client name."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Directory to scan (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--write-tags",
        action="store_true",
        help="Write only missing, filename-inferred client tags to metadata sidecars.",
    )
    parser.add_argument(
        "--write-index",
        type=Path,
        help="Write a JSON client index to this path; omitted means preview only.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"Root directory does not exist: {root}")

    workpapers = find_workpapers(root)
    tagged_count = 0
    if args.write_tags:
        for workpaper_path in workpapers:
            tagged_count += int(write_missing_client_tag(workpaper_path))

    index = build_client_index(workpapers, metadata_loader=load_metadata)
    print(f"Scanned {len(workpapers)} workpapers in {root}")
    for group in index:
        print(f"- {group['client_name']}: {len(group['workpapers'])} workpaper(s)")
        for workpaper in group["workpapers"]:
            print(f"  [{workpaper['tag_source']}] {workpaper['path']}")

    if args.write_tags:
        print(f"Wrote {tagged_count} missing metadata client tag(s).")
    if args.write_index:
        index_path = args.write_index.resolve()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps({"clients": index}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote client index: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
