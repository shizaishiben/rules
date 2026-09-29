# rules

## Mihomo MRS

All rule source files and generated files live in the repository root. The `Update and Build Sing-box and Mihomo Rules` workflow runs on pushes to `main`, manually, and daily at 14:31 UTC (22:31 China Standard Time). It downloads the AdGuard source and updates the sources configured in `links.txt` through `main.py`, then scans root-level `.txt`, `.list`, `.yaml`, `.yml`, and Sing-box rule-set `.json` files to convert and compile both formats. Source updates and generated files are committed and pushed together.

Text, list, and Mihomo YAML files with a `payload` list produce a Sing-box `.json` and `.srs` beside the input. JSON files keep their source and get an `.srs` beside it. Both directions also produce a Mihomo `.list` and supported `.mrs` files beside the input.

Supported text rules include plain domains and IP-CIDRs, Mihomo classical rules, and common AdGuard domain lines such as `||example.com^`. Only rule fields supported by both formats are converted; unrelated YAML/JSON files and unsupported text lines are skipped.

Every push to `main` (without path filters), manual run, and daily run rebuilds all root-level rule sets, including newly added files. For files sharing a name, source priority is `.yaml`, `.yml`, `.txt`, `.json`, then standalone `.list`. Edit the source, not its generated copies. In particular, `emby-域名.json` is the source of its `.list`, `.mrs`, and `.srs`; its JSON format version is preserved. `links.txt` is configuration, and `-domain`/`-ipcidr` files with an existing parent rule set are generated subsets, rebuilt from the parent. Identical output does not produce a Git change; the Actions summary reports the full rebuild count even when nothing needs committing.

Example YAML:

```yaml
payload:
  - "+.example.com"
  - "192.0.2.0/24"
```

Mihomo `.mrs` files are compiled for `domain` and `ipcidr` behaviors. Mixed lists keep the full `.list` and get separate `-domain` and/or `-ipcidr` list/MRS outputs for the compilable subsets. Mihomo 1.19.31's classical MRS converter panics, so classical-only rules remain available as `.list` without blocking other builds. `main.py` generates JSON sources; `scripts/convert_rule_formats.py` handles compilation in the same workflow.
