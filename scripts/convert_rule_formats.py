import argparse
import ipaddress
import json
import subprocess
import sys
from pathlib import Path

import yaml


TEXT_SUFFIXES = {".list", ".txt", ".yaml", ".yml"}
SKIP_DIRS = {".git", ".github", ".venv", "mihomo", "node_modules", "scripts", "singbox", "venv"}

TEXT_RULES = {
    "DOMAIN": "domain",
    "DOMAIN-SUFFIX": "domain_suffix",
    "DOMAIN-KEYWORD": "domain_keyword",
    "DOMAIN-REGEX": "domain_regex",
    "IP-CIDR": "ip_cidr",
    "IP-CIDR6": "ip_cidr",
    "SRC-IP-CIDR": "source_ip_cidr",
    "GEOIP": "geoip",
    "DST-PORT": "port",
    "SRC-PORT": "source_port",
    "NETWORK": "network",
    "PROCESS-NAME": "process_name",
    "PROCESS-PATH": "process_path",
}

SINGBOX_RULES = {
    "domain": "DOMAIN",
    "domain_suffix": "DOMAIN-SUFFIX",
    "domain_keyword": "DOMAIN-KEYWORD",
    "domain_regex": "DOMAIN-REGEX",
    "ip_cidr": "IP-CIDR",
    "source_ip_cidr": "SRC-IP-CIDR",
    "geoip": "GEOIP",
    "port": "DST-PORT",
    "source_port": "SRC-PORT",
    "network": "NETWORK",
    "process_name": "PROCESS-NAME",
    "process_path": "PROCESS-PATH",
}


def normalize_value(field, value):
    value = str(value).strip().strip("'\"")
    if not value:
        return None
    if field == "domain_suffix":
        value = value.removeprefix("+.").removeprefix(".")
    if field == "ip_cidr":
        try:
            if "/" in value:
                return str(ipaddress.ip_network(value, strict=False))
            address = ipaddress.ip_address(value)
            prefix = 32 if address.version == 4 else 128
            return f"{address}/{prefix}"
        except ValueError:
            return None
    if any(char in value for char in "\r\n"):
        return None
    return value


def add_rule(rules, field, value):
    if field in SINGBOX_RULES:
        normalized = normalize_value(field, value)
        if normalized:
            rules.setdefault(field, set()).add(normalized)


def parse_text_line(raw_line, rules):
    line = raw_line.strip().strip("'\"")
    if not line or line.startswith(("#", "!", "//")):
        return

    if " #" in line:
        line = line.split(" #", 1)[0].rstrip()

    if line.startswith("||"):
        value = line[2:].split("$", 1)[0]
        if value.endswith("^"):
            value = value[:-1]
        if value and not any(char in value for char in "*/^|"):
            add_rule(rules, "domain_suffix", value)
        return

    if "," in line:
        cells = [cell.strip() for cell in line.split(",")]
        field = TEXT_RULES.get(cells[0].upper())
        if field and len(cells) > 1:
            add_rule(rules, field, cells[1])
        return

    field = "domain"
    value = line
    if value.startswith(("+.", "*.")):
        field, value = "domain_suffix", value[2:]
    elif value.startswith("."):
        field, value = "domain_suffix", value[1:]
    elif "/" in value:
        field = "ip_cidr"
    else:
        try:
            ipaddress.ip_address(value)
            field = "ip_cidr"
        except ValueError:
            pass

    if any(char in value for char in " \t\\") or "://" in value:
        return
    add_rule(rules, field, value)


def read_text_rules(path):
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            document = yaml.safe_load(content)
        except yaml.YAMLError as error:
            raise ValueError(f"invalid YAML: {error}") from error
        items = document.get("payload", []) if isinstance(document, dict) else []
        if not isinstance(items, list):
            raise ValueError("YAML input must contain a payload list")
        lines = [str(item) for item in items if isinstance(item, (str, int, float))]
    else:
        lines = content.splitlines()

    rules = {}
    for line in lines:
        parse_text_line(line, rules)
    return rules


def read_json_rules(path):
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    entries = document.get("rules", []) if isinstance(document, dict) else []
    if not isinstance(entries, list):
        raise ValueError("JSON rule-set must contain a rules list")

    rules = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for field in SINGBOX_RULES:
            values = entry.get(field, [])
            if isinstance(values, (str, int, float)):
                values = [values]
            if isinstance(values, list):
                for value in values:
                    add_rule(rules, field, value)
    return rules


def build_singbox_json(rules):
    return {
        "version": 4,
        "rules": [{field: sorted(values) for field, values in sorted(rules.items()) if values}],
    }


def mihomo_behavior(rules):
    fields = set(rules)
    if fields <= {"domain", "domain_suffix"}:
        return "domain"
    if fields == {"ip_cidr"}:
        return "ipcidr"
    return "classical"


def build_mihomo_list(rules):
    behavior = mihomo_behavior(rules)
    lines = []
    for field, values in sorted(rules.items()):
        for value in sorted(values):
            if field == "domain_suffix":
                line = f"+.{value}"
            elif field in {"domain", "ip_cidr"} and behavior != "classical":
                line = value
            else:
                line = f"{SINGBOX_RULES[field]},{value},DIRECT"
            lines.append(line)
    return behavior, lines


def compile_command(command, label):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        print(f"[ERROR] {label}: {error}")
        return False
    if result.returncode != 0:
        print(f"[ERROR] {label}: {result.stderr.strip()}")
        return False
    return True


def compile_singbox(json_path):
    srs_path = json_path.with_suffix(".srs")
    success = compile_command(
        ["sing-box", "rule-set", "compile", "--output", str(srs_path), str(json_path)],
        f"Sing-box compile {json_path}",
    )
    if success:
        print(f"[OK] {json_path} -> {srs_path}")
    return success


def compile_mihomo(source_path, root, output_dir, rules):
    relative = source_path.relative_to(root).with_suffix(".list")
    list_path = output_dir / relative
    mrs_path = list_path.with_suffix(".mrs")
    behavior, lines = build_mihomo_list(rules)
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    success = compile_command(
        ["mihomo", "convert-ruleset", behavior, "text", str(list_path), str(mrs_path)],
        f"Mihomo compile {source_path}",
    )
    if success:
        print(f"[OK] {source_path} -> {list_path}, {mrs_path} ({behavior}, {len(lines)} rules)")
    return success


def source_files(root):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES | {".json"}:
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        yield path


def process_file(path, root, output_dir):
    try:
        if path.suffix.lower() == ".json":
            rules = read_json_rules(path)
            if rules and not compile_singbox(path):
                return False
            if not rules:
                print(f"[SKIP] {path}: no supported Sing-box rule fields for Mihomo")
                return True
        else:
            rules = read_text_rules(path)
            if not rules:
                print(f"[SKIP] {path}: no supported rules")
                return True
            json_path = path.with_suffix(".json")
            json_path.write_text(
                json.dumps(build_singbox_json(rules), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if not compile_singbox(json_path):
                return False

        return compile_mihomo(path, root, output_dir, rules)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"[ERROR] {path}: {error}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--mihomo-output", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = (args.mihomo_output or root / "mihomo").resolve()
    files = list(source_files(root))
    if not files:
        print("No supported .txt, .list, .yaml, .yml, or .json inputs found.")
        return 0

    failed = sum(not process_file(path, root, output_dir) for path in files)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())