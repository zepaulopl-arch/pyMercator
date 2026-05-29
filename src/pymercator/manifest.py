from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

MANIFEST_JSON = "00_manifest.json"
MANIFEST_TEXT = "00_manifest.txt"
MANIFEST_HEADER = "PYMERCATOR SCENARIO PACK MANIFEST\n"
MANIFEST_DIVIDER = "-" * 118


def load_json(path: str | Path, default: Any = None) -> Any:
    source = Path(path)
    if not source.exists():
        return default

    return json.loads(source.read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_manifest(pack_dir: str | Path) -> dict[str, Any]:
    return load_json(Path(pack_dir) / MANIFEST_JSON, {})


def save_manifest(pack_dir: str | Path, manifest: dict[str, Any]) -> None:
    write_json(Path(pack_dir) / MANIFEST_JSON, manifest)


def update_manifest_files(
    manifest: dict[str, Any], file_names: Iterable[str]
) -> list[str]:
    files = list(manifest.get("files", []))
    for file_name in file_names:
        if file_name not in files:
            files.append(file_name)

    manifest["files"] = files
    return files


def append_manifest_txt_section(
    pack_dir: str | Path,
    section_title: str,
    lines: list[str],
) -> None:
    manifest_txt_path = Path(pack_dir) / MANIFEST_TEXT

    if manifest_txt_path.exists():
        original = manifest_txt_path.read_text(encoding="utf-8")
    else:
        original = MANIFEST_HEADER

    marker = f"\n\n{section_title}\n"
    if marker in original:
        original = original.split(marker)[0]

    section = marker + MANIFEST_DIVIDER + "\n" + "\n".join(lines) + "\n"
    manifest_txt_path.write_text(original + section, encoding="utf-8")
