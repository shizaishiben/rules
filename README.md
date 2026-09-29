# rules

## Mihomo MRS

Add Mihomo rule sources with `.yaml`, `.yml`, `.txt`, or `.list` extensions anywhere in the repository. The build workflow scans these files on pushes to `main`, after the existing source-sync workflows succeed, and daily at 14:31 UTC. It writes normalized text and compiled `.mrs` files under `mihomo/`, mirroring each source file's relative path.

Supported inputs include Mihomo YAML files with a `payload` list, plain domain or IP-CIDR lists, Mihomo classical rules, and common AdGuard domain lines such as `||example.com^`. Unsupported lines are ignored; files without supported rules are skipped. YAML files must use a `payload` list.

Example YAML:

```yaml
payload:
  - "+.example.com"
  - "192.0.2.0/24"
```

The generated `.mrs` behavior is `domain` or `ipcidr` for single-type lists, and `classical` for mixed or explicitly classical rules. The existing Sing-box workflows continue to generate `.srs` independently.