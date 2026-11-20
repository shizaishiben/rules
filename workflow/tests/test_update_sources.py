import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "updater", Path(__file__).resolve().parents[1] / "main.py"
)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
import rule_set


class SourceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.links_file = self.root / "links.txt"
        self.output_dir = self.root / "rules"

    def run_main(self):
        with patch.object(updater, "supported_rule_set_version", return_value=5), patch(
                "sys.argv",
                [
                    "update",
                    "--links-file",
                    str(self.links_file),
                    "--output-dir",
                    str(self.output_dir),
                    "--jobs",
                    "1",
                ],
        ):
            return updater.main()

    def test_configured_sources_write_to_the_selected_rule_directory(self):
        source = "https://example.com/path/example-rules.yaml?revision=42"
        self.links_file.write_text(f"# comment\n{source}\n", encoding="utf-8")

        result = updater.SourceResult(
            url=source,
            output_path=self.output_dir / "example-rules.json",
            content=json.dumps({"version": 5, "rules": []}) + "\n",
            rule_count=0,
        )
        with patch.object(updater, "fetch_source", return_value=result) as refresh:
            self.assertEqual(self.run_main(), 0)

        refresh.assert_called_once_with(
            source,
            self.output_dir.resolve(),
            5,
        )
        self.assertTrue(self.output_dir.is_dir())
        self.assertEqual(
            json.loads((self.output_dir / "example-rules.json").read_text())["version"],
            5,
        )

    def test_duplicate_generated_names_fail_before_fetching(self):
        self.links_file.write_text(
            "https://one.example/rules.yaml\nhttps://two.example/rules.txt\n",
            encoding="utf-8",
        )

        with patch.object(updater, "fetch_source") as refresh:
            with self.assertRaises(ValueError):
                self.run_main()

        refresh.assert_not_called()

    def test_refresh_uses_the_core_supported_rule_set_version(self):
        with patch.object(
            rule_set.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout="sing-box version 1.14.1\n",
                stderr="",
            ),
        ):
            self.assertEqual(updater.supported_rule_set_version(), 5)


if __name__ == "__main__":
    unittest.main()
