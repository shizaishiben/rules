import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "updater", Path(__file__).resolve().parents[1] / "main.py"
)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class SourceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.links_file = self.root / "links.txt"
        self.output_dir = self.root / "rules"

    def run_main(self):
        with patch(
            "sys.argv",
            [
                "update",
                "--links-file",
                str(self.links_file),
                "--output-dir",
                str(self.output_dir),
            ],
        ):
            return updater.main()

    def test_configured_sources_write_to_the_selected_rule_directory(self):
        source = "https://example.com/path/example-rules.yaml?revision=42"
        self.links_file.write_text(f"# comment\n{source}\n", encoding="utf-8")

        with patch.object(updater, "parse_list_file", return_value=str(self.output_dir / "example-rules.json")) as refresh:
            self.assertEqual(self.run_main(), 0)

        refresh.assert_called_once_with(source, output_directory=self.output_dir.resolve())
        self.assertTrue(self.output_dir.is_dir())

    def test_duplicate_generated_names_fail_before_fetching(self):
        self.links_file.write_text(
            "https://one.example/rules.yaml\nhttps://two.example/rules.txt\n",
            encoding="utf-8",
        )

        with patch.object(updater, "parse_list_file") as refresh:
            with self.assertRaises(ValueError):
                self.run_main()

        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
