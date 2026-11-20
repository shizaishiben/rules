"""Shared parsing and Sing-box rule-set helpers."""

import ipaddress
import json
import re
import subprocess

import yaml


RULE_SET_VERSION_BY_CORE = (
    ((1, 14, 0), 5),
    ((1, 13, 0), 4),
    ((1, 11, 0), 3),
    ((1, 10, 0), 2),
    ((1, 8, 0), 1),
)

TEXT_RULES = {
    "DOMAIN": "domain",
    "DOMAIN-SUFFIX": "domain_suffix",
    "HOST": "domain",
    "HOST-SUFFIX": "domain_suffix",
    "DOMAIN-KEYWORD": "domain_keyword",
    "HOST-KEYWORD": "domain_keyword",
    "DOMAIN-REGEX": "domain_regex",
    "URL-REGEX": "domain_regex",
    "IP-CIDR": "ip_cidr",
    "IP-CIDR6": "ip_cidr",
    "IP6-CIDR": "ip_cidr",
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


def supported_rule_set_version(binary="sing-box"):
    try:
        result = subprocess.run(
            [binary, "version"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        raise RuntimeError(f"could not run {binary}: {error}") from error
    if result.returncode != 0:
        raise RuntimeError(f"could not read {binary} version: {result.stderr.strip()}")

    match = re.search(r"sing-box version (\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match:
        raise RuntimeError(f"could not parse sing-box version: {result.stdout.strip()}")
    core_version = tuple(int(part) for part in match.groups())
    for minimum_version, rule_set_version in RULE_SET_VERSION_BY_CORE:
        if core_version >= minimum_version:
            return rule_set_version
    raise RuntimeError("sing-box 1.8.0 or newer is required to compile source rule sets")


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
            return f"{address}/{32 if address.version == 4 else 128}"
        except ValueError:
            return None
    if any(character in value for character in "\r\n"):
        return None
    return value


def add_rule(rules, field, value):
    if field not in SINGBOX_RULES:
        return
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
        value = line[2:].split("$", 1)[0].removesuffix("^")
        if value and not any(character in value for character in "*/^|"):
            add_rule(rules, "domain_suffix", value)
        return

    if "," in line:
        pattern, value, *_ = (cell.strip() for cell in line.split(","))
        field = TEXT_RULES.get(pattern.upper())
        if field:
            add_rule(rules, field, value)
        return

    field = "domain"
    value = line
    if value.startswith(("+.", "*.")):
        field, value = "domain_suffix", value[2:]
    elif value.startswith("."):
        field, value = "domain_suffix", value[1:]
    else:
        try:
            ipaddress.ip_network(value, strict=False)
            field = "ip_cidr"
        except ValueError:
            pass
    if any(character in value for character in " \t\\") or "://" in value:
        return
    add_rule(rules, field, value)


def source_lines(content):
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        document = None
    if isinstance(document, dict) and isinstance(document.get("payload"), list):
        return [
            str(item)
            for item in document["payload"]
            if isinstance(item, (str, int, float))
        ]
    return content.splitlines()


def parse_text_rules(content):
    rules = {}
    for line in source_lines(content):
        parse_text_line(line, rules)
    return rules


def read_text_rules(path):
    return parse_text_rules(path.read_text(encoding="utf-8-sig"))


def read_json_document(path):
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or not isinstance(document.get("rules"), list):
        raise ValueError("JSON rule-set must contain a rules list")
    return document


def rules_from_document(document):
    rules = {}
    for entry in document["rules"]:
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


def build_singbox_json(rules, rule_set_version):
    return {
        "version": rule_set_version,
        "rules": [
            {field: sorted(values) for field, values in sorted(rules.items()) if values}
        ],
    }
