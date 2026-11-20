import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "converter", Path(__file__).resolve().parents[1] / "scripts" / "convert_rule_formats.py"
)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class FullRebuildTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_json(self, name, rules, version=4):
        path = self.root / f"{name}.json"
        path.write_text(json.dumps({"version": version, "rules": rules}), encoding="utf-8")
        return path

    def fake_compile(self, command, label):
        # Model binary output as source bytes so stale outputs are detectable.
        if command[0] == "sing-box":
            source, output = Path(command[-1]), Path(command[-2])
        else:
            source, output = Path(command[-2]), Path(command[-1])
        output.write_bytes(source.read_bytes())
        return True

    def rebuild(self):
        with patch.object(converter, "compile_command", side_effect=self.fake_compile), \
             patch("sys.argv", ["convert", "--root", str(self.root)]), \
             patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": ""}):
            self.assertEqual(converter.main(), 0)

    def test_json_edit_preserved_and_all_rule_sets_recompiled(self):
        source = self.write_json("emby-域名", [{"domain": ["new.example"]}], version=5)
        original = source.read_bytes()
        self.write_json("unchanged", [{"domain": ["unchanged.example"]}])
        for name in ("emby-域名", "unchanged"):
            for suffix in (".list", ".mrs", ".srs"):
                (self.root / (name + suffix)).write_text("stale.example", encoding="utf-8")
        self.rebuild()
        self.assertEqual(source.read_bytes(), original)
        for name, expected in (("emby-域名", "new.example"), ("unchanged", "unchanged.example")):
            for suffix in (".list", ".mrs", ".srs"):
                self.assertIn(expected, (self.root / (name + suffix)).read_text(encoding="utf-8"))
        self.write_json("new-file", [{"domain": ["added.example"]}])
        self.rebuild()
        self.assertIn("added.example", (self.root / "new-file.mrs").read_text())

    def test_text_source_beats_generated_copies_and_ignores_links(self):
        (self.root / "source.txt").write_text("fresh.example\n")
        self.write_json("source", [{"domain": ["stale.example"]}])
        (self.root / "source.list").write_text("stale.example\n")
        (self.root / "links.txt").write_text("https://example.com/rules.yaml\n")
        self.assertEqual([p.name for p in converter.source_files(self.root)], ["source.txt"])
        self.rebuild()
        self.assertIn("fresh.example", (self.root / "source.srs").read_text())
        self.assertIn("fresh.example", (self.root / "source.json").read_text())
        self.assertFalse((self.root / "links.json").exists())

    def test_mixed_rules_produce_only_five_files_and_clean_legacy_subsets(self):
        source = self.write_json("mixed", [{"domain": ["fresh.example"], "domain_suffix": ["suffix.example"], "domain_keyword": ["keyword"], "ip_cidr": ["192.0.2.0/24"]}])
        original = source.read_bytes()
        self.write_json("mixed-domain", [{"domain": ["stale.example"]}])
        (self.root / "mixed-domain.mrs").write_text("stale")
        for _ in range(2):
            self.assertEqual([p.name for p in converter.source_files(self.root)], ["mixed.json"])
            self.rebuild()
            self.assertEqual({p.name for p in self.root.iterdir()}, {"mixed" + ext for ext in (".json", ".srs", ".mrs", ".list", ".yaml")})
            self.assertEqual(source.read_bytes(), original)
            self.assertIn("keyword", (self.root / "mixed.srs").read_text())
            self.assertEqual((self.root / "mixed.list").read_text(), "fresh.example\n+.suffix.example\n")

    def test_ip_provider_uses_bare_cidrs(self):
        self.write_json("ips", [{"ip_cidr": ["192.0.2.0/24", "2001:db8::/32"]}])
        self.rebuild()
        lines = (self.root / "ips.list").read_text().splitlines()
        self.assertEqual(lines, ["192.0.2.0/24", "2001:db8::/32"])
        self.assertEqual(converter.yaml.safe_load((self.root / "ips.yaml").read_text()), {"payload": lines})

    def test_standalone_list_and_yaml_sources(self):
        (self.root / "standalone.list").write_text("list.example\n")
        (self.root / "yaml-source.yaml").write_text("payload:\n  - '+.yaml.example'\n")
        self.rebuild()
        self.assertIn("list.example", (self.root / "standalone.srs").read_text())
        self.assertIn("+.yaml.example", (self.root / "yaml-source.mrs").read_text())
        self.assertTrue((self.root / "standalone.json").exists())
        self.assertTrue((self.root / "yaml-source.json").exists())

    def test_domain_yaml_matches_list_and_never_overrides_json(self):
        source = self.write_json("domains", [{"domain": ["exact.example"], "domain_suffix": ["suffix.example"]}], version=5)
        original = source.read_bytes()
        self.rebuild()
        lines = (self.root / "domains.list").read_text().splitlines()
        self.assertEqual(lines, ["exact.example", "+.suffix.example"])
        self.assertEqual(converter.yaml.safe_load((self.root / "domains.yaml").read_text()), {"payload": lines})
        self.assertEqual(source.read_bytes(), original)
        self.write_json("domains", [{"domain": ["updated.example"]}], version=5)
        self.rebuild()
        self.assertEqual((self.root / "domains.list").read_text(), "updated.example\n")
        self.assertEqual([p.name for p in self.root.glob("*.json")], ["domains.json"])

    def test_compile_failure_fails_full_rebuild(self):
        self.write_json("broken", [{"domain": ["example.com"]}])
        with patch.object(converter, "compile_command", return_value=False), \
             patch("sys.argv", ["convert", "--root", str(self.root)]), \
             patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": ""}):
            self.assertEqual(converter.main(), 1)


if __name__ == "__main__":
    unittest.main()
