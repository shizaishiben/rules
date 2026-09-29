# rules

## Mihomo MRS

The build workflow scans `.txt`, `.list`, `.yaml`, `.yml`, and Sing-box rule-set `.json` files on pushes to `main`, after the existing source-sync workflows succeed, and daily at 14:31 UTC.

Text, list, and Mihomo YAML files with a `payload` list produce a Sing-box `.json` and `.srs` beside the input. JSON files keep their source and get an `.srs` beside it. Both directions also produce a Mihomo `.list` under `mihomo/`, mirroring the source path.

Supported text rules include plain domains and IP-CIDRs, Mihomo classical rules, and common AdGuard domain lines such as `||example.com^`. Only rule fields supported by both formats are converted; unrelated YAML/JSON files and unsupported text lines are skipped.

Example YAML:

```yaml
payload:
  - "+.example.com"
  - "192.0.2.0/24"
```

Mihomo `.mrs` files are compiled for `domain` and `ipcidr` behaviors. Mixed lists keep the full `.list` and get separate `-domain` and/or `-ipcidr` list/MRS outputs for the compilable subsets. Mihomo 1.19.31's classical MRS converter panics, so classical-only rules remain available as `.list` without blocking other builds. The existing Sing-box sync workflow continues to update its upstream rule sources independently.