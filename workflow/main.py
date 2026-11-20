"""Download configured rule sources and normalize them to Sing-box JSON."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WORKFLOW_DIR = Path(__file__).resolve().parent
if str(WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIR))

from rule_set import build_singbox_json, parse_text_rules, supported_rule_set_version


REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "rules-source-updater/1.0"


@dataclass(frozen=True)
class SourceResult:
    url: str
    output_path: Path
    content: str
    rule_count: int


def output_name(url):
    stem = Path(unquote(urlparse(url).path)).stem
    if not stem:
        raise ValueError(f"URL does not include a rule-set filename: {url}")
    return f"{stem}.json"


def load_links(path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def fetch_source(url, output_dir, rule_set_version):
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    finally:
        session.close()

    rules = parse_text_rules(response.text)
    if not rules:
        raise ValueError("source does not contain supported rules")
    content = json.dumps(
        build_singbox_json(rules, rule_set_version),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    return SourceResult(
        url=url,
        output_path=output_dir / output_name(url),
        content=content,
        rule_count=sum(len(values) for values in rules.values()),
    )


def write_if_changed(path, content):
    encoded = content.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return False
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        temporary_path.write_bytes(encoded)
        temporary_path.replace(path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--links-file", type=Path, default=WORKFLOW_DIR / "links.txt")
    parser.add_argument("--output-dir", type=Path, default=WORKFLOW_DIR.parent)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")

    links = load_links(args.links_file)
    names = [output_name(link) for link in links]
    if len(names) != len(set(names)):
        raise ValueError("configured URLs must produce unique output filenames")
    if not links:
        print("Source refresh: no configured sources.")
        return 0

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rule_set_version = supported_rule_set_version()
    workers = min(args.jobs, len(links))
    results = []
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            (link, executor.submit(fetch_source, link, output_dir, rule_set_version))
            for link in links
        ]
        for link, future in futures:
            try:
                results.append(future.result())
            except (OSError, ValueError, requests.RequestException) as error:
                failures += 1
                print(f"[ERROR] {link}: {error}")

    updated = 0
    for result in results:
        changed = write_if_changed(result.output_path, result.content)
        updated += changed
        status = "updated" if changed else "unchanged"
        print(f"[OK] {result.url} -> {result.output_path} ({result.rule_count} rules, {status})")

    print(
        f"Source refresh: {len(links)} configured, {len(results)} succeeded, "
        f"{failures} failed, {updated} updated (rule-set version {rule_set_version})."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
