# rules

Each rule set has five files with the same basename: `.json`, `.srs`, `.list`, `.yaml`, `.mrs`.
Uploaded JSON is the source and is preserved without rewriting or creating additional JSON copies. Non-JSON sources are converted to one same-name JSON. Source text files are kept.

The workflow refreshes upstream sources and rebuilds all root-level rule sets on every push to `main`, on manual runs, and daily at 14:31 UTC (22:31 China Standard Time). Identical output does not create a Git change. The Actions summary reports the rebuild count.

## Mihomo format

Domain providers follow the [MetaCubeX geosite layout](https://github.com/MetaCubeX/meta-rules-dat/tree/meta/geo/geosite): exact domains are bare, suffixes use `+.`, and YAML contains the same entries under `payload`.

LIST:

```text
exact.example.com
+.example.org
```

YAML:

```yaml
payload:
    - exact.example.com
    - +.example.org
```

Use `behavior: domain` for these providers. IP-only providers use bare IPv4/IPv6 CIDRs and `behavior: ipcidr`. JSON/SRS preserve all original matchers. Keywords, regular expressions, process rules, and other non-domain matchers are not included in domain LIST/YAML/MRS exports; omissions are reported in the build log. If a source contains both domains and IPs, its Mihomo provider contains domains. Sources without any supported domains or IPs fail explicitly.

No `-domain` or `-ipcidr` copies are created. Old generated copies with those suffixes are removed after the parent rule set compiles successfully.

## Source selection

Generated YAML is marked with a comment and excluded from input scanning. Hand-maintained YAML is preserved. For other same-name files, precedence is `.yaml`, `.yml`, `.txt`, `.json`, then `.list`. `workflow/links.txt` is upstream configuration, not a rule set. Edit source files rather than generated outputs.

## Repository layout

Root-level files are rule-set sources and generated artifacts only. Workflow implementation files are kept in `workflow/`:

- `workflow/main.py` refreshes the JSON sources configured in `workflow/links.txt`.
- `workflow/scripts/convert_rule_formats.py` compiles every root-level rule set.
- `workflow/tests/` contains the workflow tests, and `workflow/requirements.txt` lists its Python dependencies.

GitHub Actions configuration remains in `.github/workflows/`, as required by GitHub. SRS compilation uses the original input JSON, including its format version.
