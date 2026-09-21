"""Validate the portable parts of an Aseprite PNG/JSON export pair."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path
from typing import Any, Iterable

from . import __version__


class _ObjectWithDuplicates(dict):
    """Mapping that remembers duplicate JSON member names."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        super().__init__()
        self.duplicates: list[str] = []
        for key, value in pairs:
            if key in self:
                self.duplicates.append(key)
            self[key] = value


def _duplicate_paths(value: Any, path: str = "") -> Iterable[str]:
    if isinstance(value, _ObjectWithDuplicates):
        for key in value.duplicates:
            yield f"{path}/{key}" if path else f"/{key}"
        for key, child in value.items():
            child_path = f"{path}/{key}" if path else f"/{key}"
            yield from _duplicate_paths(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _duplicate_paths(child, f"{path}/{index}")


def _issue(code: str, severity: str, message: str, path: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if path is not None:
        item["path"] = path
    return item


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_absolute_reference(value: str) -> bool:
    return Path(value).is_absolute() or bool(re.match(r"^[A-Za-z]:[\\\\/]", value)) or value.startswith("//")


def _png_size(path: Path) -> tuple[int, int] | None:
    signature = b"\x89PNG\r\n\x1a\n"
    with path.open("rb") as handle:
        if handle.read(8) != signature:
            return None
        header = handle.read(8)
        if len(header) != 8:
            return None
        length, chunk_type = struct.unpack(">I4s", header)
        if chunk_type != b"IHDR" or length != 13:
            return None
        data = handle.read(13)
        if len(data) != 13:
            return None
        width, height = struct.unpack(">II", data[:8])
        return width, height


def _load_json(path: Path) -> tuple[Any | None, list[dict[str, Any]]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_ObjectWithDuplicates)
    except UnicodeDecodeError as exc:
        return None, [_issue("json_encoding", "insufficient", f"JSON is not UTF-8: {exc}", str(path))]
    except json.JSONDecodeError as exc:
        return None, [_issue("json_invalid", "insufficient", f"JSON cannot be parsed: {exc.msg}", str(path))]
    issues = [
        _issue("duplicate_json_key", "error", "Duplicate JSON member name; the effective value is ambiguous.", path)
        for path in _duplicate_paths(value)
    ]
    return value, issues


def _status(issues: list[dict[str, Any]], usable: bool) -> tuple[str, int]:
    if any(item["severity"] == "error" for item in issues):
        return "fail", 1
    if any(item["severity"] == "insufficient" for item in issues) or not usable:
        return "insufficient", 2
    if issues:
        return "warning", 1
    return "pass", 0


def validate(json_path: Path, image_override: Path | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    json_path = json_path.expanduser()
    image_path: Path | None = image_override.expanduser() if image_override else None
    document: Any | None = None

    if not json_path.is_file():
        issues.append(_issue("json_missing", "insufficient", "JSON metadata file does not exist.", str(json_path)))
    else:
        document, parse_issues = _load_json(json_path)
        issues.extend(parse_issues)

    if isinstance(document, dict):
        meta = document.get("meta")
        if not isinstance(meta, dict):
            issues.append(_issue("meta_missing", "insufficient", "The metadata object is missing or not an object.", "/meta"))
        else:
            image_ref = meta.get("image")
            if image_path is None and isinstance(image_ref, str) and image_ref:
                image_path = json_path.parent / image_ref
            if not isinstance(image_ref, str) or not image_ref:
                if image_path is None:
                    issues.append(_issue("image_reference_missing", "insufficient", "No image path is present in meta.image and no --image was supplied.", "/meta/image"))
            elif _is_absolute_reference(image_ref):
                issues.append(_issue("absolute_image_path", "warning", "meta.image is absolute and is not portable.", "/meta/image"))
            elif any(part == ".." for part in Path(image_ref).parts):
                issues.append(_issue("escaping_image_path", "warning", "meta.image leaves the metadata directory.", "/meta/image"))

            if image_path is not None and isinstance(image_ref, str) and image_ref:
                if Path(image_ref).name != image_path.name:
                    issues.append(_issue("image_reference_mismatch", "error", "The metadata image name does not match the supplied image.", "/meta/image"))

            expected_size = meta.get("size")
            if expected_size is not None and (
                not isinstance(expected_size, dict)
                or not _is_int(expected_size.get("w"))
                or not _is_int(expected_size.get("h"))
            ):
                issues.append(_issue("metadata_size_invalid", "error", "meta.size must contain integer w and h values.", "/meta/size"))

        frames = document.get("frames")
        frame_items: list[tuple[str, Any]] = []
        if isinstance(frames, dict):
            frame_items = [(str(name), descriptor) for name, descriptor in frames.items()]
        elif isinstance(frames, list):
            for index, descriptor in enumerate(frames):
                if isinstance(descriptor, dict) and isinstance(descriptor.get("filename"), str):
                    frame_items.append((descriptor["filename"], descriptor))
                else:
                    issues.append(_issue("frame_name_missing", "error", "Array frame entries need a string filename.", f"/frames/{index}"))
        else:
            issues.append(_issue("frames_missing", "insufficient", "The frames object or array is missing.", "/frames"))

        seen_names: set[str] = set()
        for name, descriptor in frame_items:
            if name in seen_names:
                issues.append(_issue("duplicate_frame_name", "error", "More than one frame uses the same name.", f"/frames/{name}"))
            seen_names.add(name)
            if not isinstance(descriptor, dict):
                issues.append(_issue("frame_invalid", "error", "Frame descriptor must be an object.", f"/frames/{name}"))
                continue
            rect = descriptor.get("frame")
            if not isinstance(rect, dict) or not all(_is_int(rect.get(key)) for key in ("x", "y", "w", "h")):
                issues.append(_issue("frame_rect_invalid", "error", "Frame rectangle needs integer x, y, w, and h values.", f"/frames/{name}/frame"))
                continue
            if rect["w"] <= 0 or rect["h"] <= 0 or rect["x"] < 0 or rect["y"] < 0:
                issues.append(_issue("frame_rect_negative_or_empty", "error", "Frame rectangle must be non-empty and within positive coordinates.", f"/frames/{name}/frame"))

        if not frame_items and isinstance(frames, (dict, list)):
            issues.append(_issue("frames_empty", "insufficient", "No frame descriptors were available for pair validation.", "/frames"))
    elif document is not None:
        issues.append(_issue("json_root_invalid", "insufficient", "The JSON root must be an object.", str(json_path)))

    image_size: tuple[int, int] | None = None
    if image_path is not None:
        image_path = image_path.resolve()
        if not image_path.is_file():
            issues.append(_issue("image_missing", "error", "Referenced image file does not exist.", str(image_path)))
        else:
            try:
                image_size = _png_size(image_path)
            except OSError as exc:
                issues.append(_issue("image_unreadable", "insufficient", f"Image could not be read: {exc}", str(image_path)))
            if image_size is None:
                issues.append(_issue("image_not_png", "insufficient", "The pair witness currently requires a readable PNG image.", str(image_path)))

    if image_size is not None and isinstance(document, dict):
        frames = document.get("frames")
        descriptors = frames.values() if isinstance(frames, dict) else frames if isinstance(frames, list) else []
        for index, descriptor in enumerate(descriptors):
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get("frame"), dict):
                continue
            rect = descriptor["frame"]
            if all(_is_int(rect.get(key)) for key in ("x", "y", "w", "h")):
                if rect["x"] + rect["w"] > image_size[0] or rect["y"] + rect["h"] > image_size[1]:
                    label = descriptor.get("filename", index)
                    issues.append(_issue("frame_out_of_bounds", "error", f"Frame rectangle exceeds PNG bounds {image_size[0]}x{image_size[1]}.", f"/frames/{label}/frame"))

    issues.sort(key=lambda item: (item.get("severity", ""), item.get("code", ""), item.get("path", "")))
    status, exit_code = _status(issues, document is not None and image_size is not None)
    result: dict[str, Any] = {
        "tool": "aseprite-pair-witness",
        "version": __version__,
        "status": status,
        "exit_code": exit_code,
        "json": str(json_path),
        "image": str(image_path) if image_path is not None else None,
        "image_size": {"w": image_size[0], "h": image_size[1]} if image_size else None,
        "issues": issues,
    }
    return result


def audit_directory(directory: Path) -> dict[str, Any]:
    """Validate same-stem PNG/JSON pairs and report orphaned sidecars."""
    directory = directory.expanduser()
    if not directory.is_dir():
        issue = _issue("directory_missing", "insufficient", "Asset directory does not exist.", str(directory))
        return {
            "tool": "aseprite-pair-witness",
            "version": __version__,
            "status": "insufficient",
            "exit_code": 2,
            "directory": str(directory),
            "reports": [],
            "issues": [issue],
        }

    json_files = {path.stem: path for path in sorted(directory.glob("*.json"))}
    image_files = {path.stem: path for path in sorted(directory.glob("*.png"))}
    stems = sorted(set(json_files) | set(image_files))
    reports = [
        validate(
            json_files.get(stem, directory / f"{stem}.json"),
            image_files.get(stem, directory / f"{stem}.png"),
        )
        for stem in stems
    ]

    if not reports:
        issues = [_issue("directory_empty", "insufficient", "No PNG or JSON sidecars were found.", str(directory))]
        return {
            "tool": "aseprite-pair-witness",
            "version": __version__,
            "status": "insufficient",
            "exit_code": 2,
            "directory": str(directory),
            "reports": [],
            "issues": issues,
        }

    statuses = {report["status"] for report in reports}
    if "fail" in statuses:
        status, exit_code = "fail", 1
    elif "insufficient" in statuses:
        status, exit_code = "insufficient", 2
    elif "warning" in statuses:
        status, exit_code = "warning", 1
    else:
        status, exit_code = "pass", 0
    return {
        "tool": "aseprite-pair-witness",
        "version": __version__,
        "status": status,
        "exit_code": exit_code,
        "directory": str(directory),
        "reports": reports,
        "issues": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--json", type=Path, dest="json_path", help="Aseprite JSON metadata file")
    sources.add_argument("--directory", type=Path, help="Directory containing same-stem PNG/JSON sidecars")
    parser.add_argument("--image", type=Path, help="PNG image; otherwise derive it from meta.image")
    parser.add_argument("--pretty", action="store_true", help="Indent the JSON report")
    args = parser.parse_args(argv)
    if args.directory is not None:
        if args.image is not None:
            parser.error("--image can only be used with --json")
        result = audit_directory(args.directory)
    else:
        result = validate(args.json_path, args.image)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
