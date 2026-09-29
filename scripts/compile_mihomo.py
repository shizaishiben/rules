import argparse
import ipaddress
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as error:
    raise SystemExit("PyYAML is required: install it with 'pip install pyyaml'") from error


CLASSICAL_TYPES = {
    "AND", "DOMAIN", "DOMAIN-KEYWORD", "DOMAIN-REGEX", "DOMAIN-SUFFIX",
    "DOMAIN-WILDCARD", "DSCP", "DST-PORT", "GEOIP", "IN-NAME", "IN-PORT",
    "IN-TYPE", "IN-USER", "IP-ASN", "IP-CIDR", "IP-CIDR6", "IP-SUFFIX",
    "MATCH", "NETWORK", "NOT", "OR", "PROCESS-NAME", "PROCESS-NAME-REGEX",
    "PROCESS-NAME-WILDCARD", "PROCESS-PATH", "PROCESS-PATH-REGEX",
    "PROCESS-PATH-WILDCARD", "REMATCH-NAME", "RULE-SET", "SRC-GEOIP",
    "SRC-IP-ASN", "SRC-IP-CIDR", "SRC-IP-SUFFIX", "SRC-PORT", "SUB-RULE", "UID",
}
INPUT_SUFFIXES = {".list", ".txt", ".yaml", ".yml"}
IGNORED_DIRS = {".git", ".venv", "venv", "mihomo", "node_modules"}


def load_lines(path):
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() not in {".yaml", ".yml"}:
        return text.splitlines()

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML: {error}") from error

    if isinstance(data, dict):
        data = data.get("payload")
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, (str, int, float))]


def normalize_line(raw_line):
    line = raw_line.strip().strip("'\"")
    if not line or line.startswith(("#", "!", "//")):
        return None

    if line.startswith("||"):
        pattern = line[2:].split("$", 1)[0]
        if pattern.endswith("^"):
            pattern = pattern[:-1]
        if pattern and not any(char in pattern for char in "*/^|"):
            return "suffix", pattern.lstrip(".")
        return None

    cells = [cell.strip() for cell in line.split(",")]
    rule_type = cells[0].upper()
    if len(cells) >= 2 and rule_type in CLASSICAL_TYPES:
        return "classical", ",".join(cells)

    candidate = line
    kind = "domain"
    if candidate.startswith(("+.", "*.")):
        candidate = candidate[2:]
        kind = "suffix"
    elif candidate.startswith("."):
        candidate = candidate[1:]
        kind = "suffix"

    try:
        if "/" in candidate:
            network = ipaddress.ip_network(candidate, strict=False)
            return "ip", str(network)
        address = ipaddress.ip_address(candidate)
        prefix = 32 if address.version == 4 else 128
        return "ip", f"{address}/{prefix}"
    except ValueError:
        pass

    if not candidate or any(char.isspace() for char in candidate):
        return None
    if any(char in candidate for char in "/,:\\") or "://" in candidate:
        return None
    if candidate.startswith(("@", "|")) or "*" in candidate or "^" in candidate:
        return None
    return kind, candidate


def normalize_rules(lines):
    rules = set()
    for line in lines:
        normalized = normalize_line(line)
        if normalized:
            rules.add(normalized)

    if not rules:
        return None, []

    kinds = {kind for kind, _ in rules}
    if kinds == {"domain"} or kinds == {"suffix"} or kinds <= {"domain", "suffix"}:
        behavior = "domain"
        output = [f"+.{value}" if kind == "suffix" else value for kind, value in rules]
    elif kinds == {"ip"}:
        behavior = "ipcidr"
        output = [value for _, value in rules]
    else:
        behavior = "classical"
        output = []
        for kind, value in rules:
            if kind == "classical":
                output.append(value)
            elif kind == "ip":
                output.append(f"IP-CIDR,{value},DIRECT,no-resolve")
            elif kind == "suffix":
                output.append(f"DOMAIN-SUFFIX,{value},DIRECT")
            else:
                output.append(f"DOMAIN,{value},DIRECT")

    return behavior, sorted(output)


def source_files(root, output_dir):
    output_dir = output_dir.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in INPUT_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        yield path


def compile_file(path, root, output_dir, mihomo):
    try:
        behavior, lines = normalize_rules(load_lines(path))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"[ERROR] {path.relative_to(root)}: {error}")
        return False

    if not lines:
        print(f"[SKIP] {path.relative_to(root)}: no supported Mihomo rules")
        return True

    relative = path.relative_to(root).with_suffix("")
    text_path = (output_dir / relative).with_suffix(".txt")
    mrs_path = text_path.with_suffix(".mrs")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = subprocess.run(
        [mihomo, "convert-ruleset", behavior, "text", str(text_path), str(mrs_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"[ERROR] {path.relative_to(root)}: {result.stderr.strip()}")
        return False

    print(f"[OK] {path.relative_to(root)} -> {mrs_path.relative_to(root)} ({behavior}, {len(lines)} rules)")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mihomo", default="mihomo")
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = (args.output_dir or root / "mihomo").resolve()
    files = list(source_files(root, output_dir))
    if not files:
        print("No .txt, .list, .yaml, or .yml inputs found.")
        return 0

    failed = sum(not compile_file(path, root, output_dir, args.mihomo) for path in files)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())