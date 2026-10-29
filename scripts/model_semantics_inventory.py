#!/usr/bin/env python3
"""Read the formal P1b archive once and retain research metadata, not QM binaries.

The source archive is opened read-only. No archive code is executed. Selected
metadata and histories are copied under the supplied output directory; the full
member index makes omissions visible. Scientific logs and scores are not changed.
"""

from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path, PurePosixPath


def selected_metadata(name: str) -> bool:
    path = PurePosixPath(name)
    if path.name in {"MANIFEST.txt", "SUMMARY.md", "runs.csv", "README.md"}:
        return True
    if path.suffix in {".db", ".sqlite", ".sqlite3"}:
        return True
    if path.suffix not in {".json", ".jsonl", ".md", ".txt", ".log"}:
        return False
    return any(token in name.lower() for token in
               ("/contexts/", "/sessions/", "/trajectory", "/conversation", "/llm", "/events"))


def inventory(archive: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    entries, groups = [], set()
    total_bytes, copied_bytes = 0, 0
    metadata = output / "archive_metadata"
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            if not member.isfile():
                continue
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe archive member: {member.name}")
            row = {"path": member.name, "bytes": member.size, "copied": False}
            total_bytes += member.size
            parts = path.parts
            if len(parts) >= 6 and parts[3] == "sandboxes":
                groups.add((parts[1], parts[2], parts[4]))
            if selected_metadata(member.name):
                target = metadata.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.stat().st_size != member.size:
                    stream = source.extractfile(member)
                    if stream is None:
                        raise ValueError(f"Cannot read {member.name}")
                    with target.open("wb") as destination:
                        while chunk := stream.read(1024 * 1024):
                            destination.write(chunk)
                row["copied"] = True
                copied_bytes += member.size
            entries.append(row)
    summary = {"source_archive": str(archive.resolve()), "source_archive_bytes": archive.stat().st_size,
               "member_count": len(entries), "uncompressed_regular_file_bytes": total_bytes,
               "copied_metadata_bytes": copied_bytes,
               "sandbox_groups": [dict(zip(("arm", "round", "task"), group, strict=True))
                                  for group in sorted(groups)],
               "sandbox_group_count": len(groups),
               "source_unchanged": "Opened read-only; no extraction into the original dataset.",
               "selection": "Research metadata and histories only; skipped files remain in member_index.json."}
    for name, value in (("member_index.json", entries), ("inventory.json", summary)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.archive, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
