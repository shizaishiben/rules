# rules

## Mihomo MRS

The build workflow scans `.txt`, `.list`, `.yaml`, `.yml`, and Sing-box rule-set `.json` files on pushes to `main`, after the existing source-sync workflows succeed, and daily at 14:31 UTC.

Text, list, and Mihomo YAML files with a `payload` list produce a Sing-box `.json` and `.srs` beside the input. JSON files keep their source and get an `.srs` beside it. Both directions also produce a Mihomo `.list` and `.mrs` under `mihomo/`, mirroring the source path.

Supported text rules include plain domains and IP-CIDRs, Mihomo classical rules, and common AdGuard domain lines such as `||example.com^`. Only rule fields supported by both formats are converted; unrelated YAML/JSON files and unsupported text lines are skipped.

Example YAML:

```yaml
payload:
  - "+.example.com"
  - "192.0.2.0/24"
```

The generated `.mrs` behavior is `domain` or `ipcidr` for single-type lists, and `classical` for mixed rules. The existing Sing-box sync workflow continues to update its upstream rule sources independently.