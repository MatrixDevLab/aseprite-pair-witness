import json
import tempfile
import unittest
from pathlib import Path

from aseprite_pair_witness.cli import audit_directory, main, validate


PNG_2X2 = (
    b"\x89PNG\r\n\x1a\n"
    + (13).to_bytes(4, "big")
    + b"IHDR"
    + (2).to_bytes(4, "big")
    + (2).to_bytes(4, "big")
    + b"\x08\x06\x00\x00\x00"
    + b"\x00" * 4
)


def write_pair(directory: Path, document: object, image_name: str = "sheet.png") -> tuple[Path, Path]:
    image = directory / image_name
    image.write_bytes(PNG_2X2)
    metadata = directory / "sheet.json"
    metadata.write_text(json.dumps(document), encoding="utf-8")
    return metadata, image


class PairWitnessTests(unittest.TestCase):
    def test_valid_hash_pair_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            metadata, _ = write_pair(
                Path(raw),
                {"frames": {"idle": {"frame": {"x": 0, "y": 0, "w": 2, "h": 2}}}, "meta": {"image": "sheet.png"}},
            )
            result = validate(metadata)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["exit_code"], 0)

    def test_array_pair_checks_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            metadata, image = write_pair(
                Path(raw),
                {"frames": [{"filename": "bad", "frame": {"x": 1, "y": 1, "w": 2, "h": 2}}], "meta": {"image": "sheet.png"}},
            )
            result = validate(metadata, image)
            self.assertEqual(result["status"], "fail")
            self.assertIn("frame_out_of_bounds", {item["code"] for item in result["issues"]})

    def test_missing_image_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            metadata = Path(raw) / "sheet.json"
            metadata.write_text(json.dumps({"frames": {}, "meta": {"image": "missing.png"}}), encoding="utf-8")
            result = validate(metadata)
            self.assertEqual(result["status"], "fail")
            self.assertIn("image_missing", {item["code"] for item in result["issues"]})

    def test_absolute_reference_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            metadata, image = write_pair(
                Path(raw),
                {"frames": {"idle": {"frame": {"x": 0, "y": 0, "w": 1, "h": 1}}}, "meta": {"image": str(Path(raw) / "sheet.png")}},
            )
            result = validate(metadata, image)
            self.assertEqual(result["status"], "warning")
            self.assertIn("absolute_image_path", {item["code"] for item in result["issues"]})

    def test_duplicate_json_frame_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            image = directory / "sheet.png"
            image.write_bytes(PNG_2X2)
            metadata = directory / "sheet.json"
            metadata.write_text(
                '{"frames":{"idle":{"frame":{"x":0,"y":0,"w":1,"h":1}},"idle":{"frame":{"x":0,"y":0,"w":1,"h":1}}},"meta":{"image":"sheet.png"}}',
                encoding="utf-8",
            )
            result = validate(metadata)
            self.assertEqual(result["status"], "fail")
            self.assertIn("duplicate_json_key", {item["code"] for item in result["issues"]})

    def test_cli_returns_report_for_missing_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            code = main(["--json", str(Path(raw) / "missing.json")])
            self.assertEqual(code, 2)

    def test_directory_audit_detects_orphan_png(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "orphan.png").write_bytes(PNG_2X2)
            result = audit_directory(directory)
            self.assertEqual(result["status"], "insufficient")
            self.assertEqual(result["exit_code"], 2)
            self.assertEqual(result["reports"][0]["issues"][0]["code"], "json_missing")

    def test_directory_audit_validates_same_stem_pair(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_pair(
                directory,
                {"frames": {"idle": {"frame": {"x": 0, "y": 0, "w": 2, "h": 2}}}, "meta": {"image": "sheet.png"}},
            )
            result = audit_directory(directory)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["exit_code"], 0)

    def test_directory_audit_detects_orphan_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "orphan.json").write_text(
                json.dumps({"frames": {"idle": {"frame": {"x": 0, "y": 0, "w": 1, "h": 1}}}, "meta": {"image": "orphan.png"}}),
                encoding="utf-8",
            )
            result = audit_directory(directory)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["reports"][0]["issues"][0]["code"], "image_missing")

    def test_cli_directory_mode_returns_directory_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "orphan.png").write_bytes(PNG_2X2)
            self.assertEqual(main(["--directory", str(directory)]), 2)


if __name__ == "__main__":
    unittest.main()
