---
name: gooddata-platform2cloud-cli
description: Use when operating, running, or constructing commands for the gooddata-legacy2cloud CLI — migrating GoodData Legacy analytics content (LDM, metrics, insights, dashboards, reports, scheduled exports, permissions) to GoodData Cloud. Covers all 10 CLI commands, their parameters, .env setup, migration order, and common patterns.
---

# gooddata-legacy2cloud CLI

## Overview

CLI tool for migrating analytical content from GoodData Legacy (private cloud) to GoodData Cloud (modern platform).

- Entry point: `gooddata-legacy2cloud <command>`
- Install from PyPI:
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install gooddata-legacy2cloud
  ```
- Install from source (inside cloned repo):
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install .
  ```
- Always activate the venv before running commands: `source .venv/bin/activate`

## Pre-Flight Checks

Before running any migration command, verify:

1. **CLI accessible:**
   ```bash
   gooddata-legacy2cloud --help
   ```
   If this fails, **stop and inform the user** — the CLI is not installed or not on PATH. Do not proceed. Suggest: `pip install gooddata-legacy2cloud` or activate the correct virtual environment.

2. **`.env` file exists:**
   ```bash
   test -f .env && echo "exists" || echo "missing"
   ```
   If missing, **stop and inform the user** — the CLI needs credentials to run.

## Environment Setup

> **Security:** The `.env` file contains sensitive credentials. **Never read its contents directly** — only verify it exists (`ls .env` or `test -f .env`). The CLI reads it at runtime.

Create a `.env` file before running any command:

```
# Required
LEGACY_DOMAIN = "https://your-legacy-domain.com/"
LEGACY_LOGIN = "your_username"
LEGACY_PASSWORD = "your_password"
LEGACY_WS = "your_legacy_workspace_id"        # PID from Legacy URL

CLOUD_DOMAIN = "https://your-cloud-domain.gooddata.com/"
CLOUD_TOKEN = "your_bearer_token"              # User Settings > API Tokens
CLOUD_WS = "your_cloud_workspace_id"

DATA_SOURCE_ID = "your_data_source_id"         # Must exist before migration
SCHEMA = "your_schema"
TABLE_PREFIX = "your_table_prefix"

# Optional — workspace data filters
WS_DATA_FILTER_ID = "filter_id"
WS_DATA_FILTER_COLUMN = "filter_column"
WS_DATA_FILTER_DESCRIPTION = "filter_description"

# Required for scheduled-exports command only
CLOUD_NOTIFICATION_CHANNEL_ID = "notification_channel_id"
```

Use `--env path/to/.env` to specify a non-default env file.

## Migration Order (Dependency Chain)

Run commands in this order — later commands read mapping files produced by earlier ones:

```
1. ldm              → produces ldm_mappings.csv
2. color-palette    → (no mapping deps or output)
3. metrics          → reads ldm_mappings.csv → produces metric_mappings.csv
4. insights         → reads ldm + metric mappings → produces insight_mappings.csv
5. dashboards       → reads ldm + metric + insight mappings → produces dashboard_mappings.csv
6. reports          → reads ldm + metric mappings → produces report_mappings.csv
7. pp-dashboards    → reads ldm + metric + insight + report mappings → produces pixel_perfect_dashboard_mappings.csv
8. scheduled-exports → reads metric + insight + dashboard mappings → produces scheduled_export_mappings.csv
9. dashboard-permissions → reads dashboard + pp-dashboard mappings (no mapping output)
10. web-compare     → reads migration log files → produces HTML comparison output
```

## Common Parameters

Available on most commands (except `color-palette` and `web-compare`):

| Parameter | Description |
|-----------|-------------|
| `--env PATH` | Path to .env file (default: `.env`) |
| `--legacy-ws ID` | Override `LEGACY_WS` from .env |
| `--cloud-ws ID` | Override `CLOUD_WS` from .env |
| `--skip-deploy` | Dry run — parse and transform but skip PUT to Cloud |
| `--dump-legacy` | Save Legacy objects to JSON file |
| `--dump-cloud` | Save Cloud objects to JSON file |
| `--overwrite-existing` | Update objects that already exist (default: skip them) |
| `--cleanup-target-env` | Delete ALL existing objects of this type before migration |
| `--output-files-prefix PREFIX` | Prefix all output filenames (mapping files, logs, etc.) |
| `--client-prefix PREFIX` | Client workspace mode — see Patterns section |
| `--check-parent-workspace` | Verify target Cloud workspace has a parent |
| `--suppress-migration-warnings` | Don't add `[WARN]` to object titles (warnings still printed to console) |

## Filtering Parameters

Available on: `metrics`, `insights`, `dashboards`, `reports`, `pp-dashboards`, `dashboard-permissions`

| Parameter | Description |
|-----------|-------------|
| `--with-tags TAG1,TAG2` | Only migrate objects with these tags |
| `--without-tags TAG1,TAG2` | Exclude objects with these tags |
| `--with-creator-profiles P1,P2` | Only migrate objects created by these profiles |
| `--without-creator-profiles P1,P2` | Exclude objects from these profiles |
| `--with-locked-flag` | Only migrate locked objects |
| `--without-locked-flag` | Only migrate unlocked objects |
| `--only-object-ids ID1,ID2` | Migrate specific objects by Legacy numeric ID |
| `--only-object-ids-with-dependencies ID1,ID2` | Migrate objects + all their dependencies |
| `--only-identifiers IDENT1,IDENT2` | Migrate by alphanumeric identifier |
| `--only-identifiers-with-dependencies IDENT1,IDENT2` | Migrate by identifier + dependencies |
| `--without-mapped-objects default_only\|all` | Skip already-mapped objects (incremental migrations) |

## Element Lookup Parameters

Available on: `metrics`, `insights`, `dashboards`, `reports`, `pp-dashboards`

These address attribute element values used in filters — in Legacy, values must exist in the workspace to be readable. Use these to recover missing values.

| Parameter | Available on | Description |
|-----------|-------------|-------------|
| `--element-values-prefetch` | metrics, insights, dashboards, reports | Batch-fetch element values before processing; reduces Legacy API calls |
| `--validation-element-lookup` | all above | Use Legacy validation endpoint to fetch missing element values |
| `--validation-element-lookup-with-metrics` | insights, dashboards only | Advanced: create temp metrics → run validation → delete metrics. Most comprehensive; includes both above. Requires write permission to Legacy workspace. |

## Command Reference

### `ldm` — Logical Data Model

```bash
gooddata-legacy2cloud ldm
```

- **Reads:** nothing
- **Writes:** `ldm_mappings.csv`
- **Specific params:**
  - `--ignore-folders` — don't migrate LDM folders as Cloud tags
  - `--ignore-explicit-mapping` — use ADS naming convention instead of Modeler explicit mapping

---

### `color-palette`

```bash
gooddata-legacy2cloud color-palette
```

- **Reads:** nothing | **Writes:** nothing
- Sets org-level color palette from Legacy. **Overwrites ALL existing color palettes.**
- Params: `--env`, `--legacy-ws`, `--cloud-ws` only

---

### `metrics`

```bash
gooddata-legacy2cloud metrics
```

- **Reads:** `ldm_mappings.csv`
- **Writes:** `metric_mappings.csv`, `metrics_maql.log`, `cloud_failed_metrics.json`, `cloud_skipped_metrics.json`
- **Specific params:**
  - `--keep-original-ids` — use Legacy identifier as Cloud ID (default: derived from title + Legacy ID)
  - `--ignore-folders` — don't migrate metric folders as Cloud tags
  - `--ldm-mapping-file FILE` — custom LDM mapping file (default: `ldm_mappings.csv`)
  - `--metric-mapping-file FILE` — custom metric mapping output file (default: `metric_mappings.csv`)
- **Notes:**
  - Missing element values → replaced with `--MISSING VALUE--` + `[WARN]` added to title
  - MAQL conversion failures → `[ERROR]` in title, definition set to `SELECT SQRT(-1)` (returns NULL), original MAQL in comment

---

### `insights`

```bash
gooddata-legacy2cloud insights
```

- **Reads:** `ldm_mappings.csv`, `metric_mappings.csv`
- **Writes:** `insight_mappings.csv`, `insight_logs.log`, `cloud_failed_insights.json`, `cloud_skipped_insights.json`
- **Specific params:**
  - `--keep-original-ids` — use Legacy identifier as Cloud ID
  - `--ldm-mapping-file FILE`, `--metric-mapping-file FILE`, `--insight-mapping-file FILE`
- **Notes:**
  - Cannot migrate Geo charts
  - Missing filter element values → values removed, insight marked `[WARN]`
  - Best element lookup: `--validation-element-lookup-with-metrics`

---

### `dashboards`

```bash
gooddata-legacy2cloud dashboards
```

- **Reads:** `ldm_mappings.csv`, `metric_mappings.csv`, `insight_mappings.csv`
- **Writes:** `dashboard_mappings.csv`, `dashboards_logs.log`, `cloud_failed_dashboards.json`, `cloud_skipped_dashboards.json`
- **Specific params:**
  - `--keep-original-ids` — use Legacy identifier as Cloud ID
  - `--dashboard-type TYPE` — type of dashboard to migrate (default: `analyticalDashboard`)
  - `--ldm-mapping-file FILE`, `--metric-mapping-file FILE`, `--insight-mapping-file FILE`, `--dashboard-mapping-file FILE`
- **Notes:**
  - Dashboards created empty first, then updated (ensures drillToDashboard targets exist)
  - Missing drill targets → drill removed, dashboard marked `[WARN]`

---

### `reports` — Pixel Perfect Reports → Cloud Visualizations

```bash
gooddata-legacy2cloud reports
```

- **Reads:** `ldm_mappings.csv`, `metric_mappings.csv`
- **Writes:** `report_mappings.csv`, `report_logs.log`, `cloud_failed_reports.json`, `cloud_skipped_reports.json`
- **Specific params:**
  - `--keep-original-ids` — use Legacy identifier as Cloud ID
  - `--report-prefix PREFIX` — prefix added to migrated visualization names (default: `[PP] `; use `""` to disable)
  - `--ldm-mapping-file FILE`, `--metric-mapping-file FILE`, `--report-mapping-file FILE`
- **Notes:**
  - Best-effort conversion; visual appearance may differ from Legacy
  - PP-only features (some filter types) may not be available in Cloud

---

### `pp-dashboards` — Pixel Perfect Dashboards

```bash
gooddata-legacy2cloud pp-dashboards
```

- **Reads:** `ldm_mappings.csv`, `metric_mappings.csv`, `insight_mappings.csv`, `report_mappings.csv`
- **Writes:** `pixel_perfect_dashboard_mappings.csv`
- **Specific params:**
  - `--keep-original-ids` — use Legacy identifier as Cloud ID (cannot combine with `--pp-legacy-split-tabs`)
  - `--pp-legacy-split-tabs` — each Legacy tab → separate Cloud dashboard (legacy behavior; default is one dashboard with native tabs)
  - `--ldm-mapping-file FILE`, `--metric-mapping-file FILE`, `--insight-mapping-file FILE`, `--report-mapping-file FILE` (no `--insight-mapping-file` is not used here, actually `--report-mapping-file` is used)

---

### `scheduled-exports`

```bash
gooddata-legacy2cloud scheduled-exports
```

- **Reads:** `metric_mappings.csv`, `insight_mappings.csv`, `dashboard_mappings.csv`
- **Writes:** `scheduled_export_mappings.csv`
- **Requires:** `CLOUD_NOTIFICATION_CHANNEL_ID` set in .env
- **Specific params:**
  - `--exports-to-migrate FILE` — path to file listing specific export IDs to migrate (one per line)
  - `--ldm-mapping-file FILE`, `--metric-mapping-file FILE`, `--insight-mapping-file FILE`, `--dashboard-mapping-file FILE`, `--scheduled-export-mapping-file FILE`

---

### `dashboard-permissions`

```bash
gooddata-legacy2cloud dashboard-permissions
```

- **Reads:** `dashboard_mappings.csv`, `pixel_perfect_dashboard_mappings.csv`
- **Writes:** nothing (modifies existing Cloud dashboards in-place)
- **Specific params:**
  - `--permission VIEW|SHARE|EDIT` — permission level to assign (default: `EDIT`)
  - `--use-email` — match users by email field instead of login field
  - `--keep-existing-permissions` — preserve permissions not present in Legacy source
  - `--skip-creators` — don't migrate creator permissions
  - `--skip-individual-grantees` — don't migrate individual user permissions
  - `--skip-group-grantees` — don't migrate user group permissions
  - `--skip-kpi-dashboards` — skip KPI dashboards
  - `--skip-pp-dashboards` — skip Pixel Perfect dashboards
  - `--dump-layout` — save layout JSON before and after modifications
  - `--print-user-mappings` — print detailed user mapping information
  - `--dashboard-mapping-file FILE`, `--pp-dashboard-mapping-file FILE`

---

### `web-compare`

```bash
gooddata-legacy2cloud web-compare --log-dir ./logs --output-dir ./web_compare
```

- **Reads:** migration log files in `--log-dir`
- **Writes:** HTML comparison files to `--output-dir`
- **Params:**
  - `--log-dir DIR` — directory containing migration log files (required)
  - `--output-dir DIR` — output directory for HTML (default: `web_compare`)
  - `--skip-inherited` — exclude unprefixed objects from prefixed outputs with `inherited` status
  - `--env PATH` — optional (for defaults)

---

## Common Patterns

### Full single workspace migration

```bash
gooddata-legacy2cloud ldm
gooddata-legacy2cloud color-palette
gooddata-legacy2cloud metrics
gooddata-legacy2cloud insights
gooddata-legacy2cloud dashboards
gooddata-legacy2cloud reports
gooddata-legacy2cloud pp-dashboards
```

### Dry run (no Cloud writes)

```bash
gooddata-legacy2cloud metrics --skip-deploy --dump-legacy
```

### Incremental migration (only new objects)

```bash
gooddata-legacy2cloud metrics --without-mapped-objects default_only
gooddata-legacy2cloud insights --without-mapped-objects default_only
gooddata-legacy2cloud dashboards --without-mapped-objects default_only
```

### Client workspace migration (parent/child)

```bash
# 1. Migrate parent workspace first (no prefix)
gooddata-legacy2cloud metrics
gooddata-legacy2cloud insights
gooddata-legacy2cloud dashboards

# 2. Migrate each child/client workspace
gooddata-legacy2cloud metrics \
  --legacy-ws client1_pid \
  --cloud-ws client1_cloud_id \
  --client-prefix client1_
gooddata-legacy2cloud insights \
  --legacy-ws client1_pid \
  --cloud-ws client1_cloud_id \
  --client-prefix client1_
gooddata-legacy2cloud dashboards \
  --legacy-ws client1_pid \
  --cloud-ws client1_cloud_id \
  --client-prefix client1_
```

`--client-prefix` automatically: reads both default (parent) and prefixed (client) mapping files; only migrates objects NOT present in parent mappings; prefixes all output files with the given prefix; validates that the target workspace has a parent.

### Overwrite existing objects

```bash
gooddata-legacy2cloud insights --overwrite-existing
```

### Migrate specific objects only

```bash
gooddata-legacy2cloud metrics --only-object-ids 123,456,789
gooddata-legacy2cloud dashboards --only-identifiers my_dashboard_id
gooddata-legacy2cloud insights --only-identifiers-with-dependencies my_insight_id
```

### Use custom env file

```bash
gooddata-legacy2cloud ldm --env /path/to/production.env
```

### Best element lookup (prevents missing filter values)

```bash
# For metrics and reports
gooddata-legacy2cloud metrics --validation-element-lookup
# For insights and dashboards (most comprehensive)
gooddata-legacy2cloud insights --validation-element-lookup-with-metrics
gooddata-legacy2cloud dashboards --validation-element-lookup-with-metrics
```

## Output Files Reference

| File pattern | Produced by | Contents |
|-------------|-------------|---------|
| `ldm_mappings.csv` | `ldm` | Legacy attribute/fact → Cloud ID mappings |
| `metric_mappings.csv` | `metrics` | Legacy metric ID → Cloud metric ID |
| `insight_mappings.csv` | `insights` | Legacy insight ID → Cloud insight ID |
| `dashboard_mappings.csv` | `dashboards` | Legacy dashboard ID → Cloud dashboard ID |
| `report_mappings.csv` | `reports` | Legacy report ID → Cloud visualization ID |
| `pixel_perfect_dashboard_mappings.csv` | `pp-dashboards` | Legacy PP dashboard ID → Cloud dashboard ID |
| `scheduled_export_mappings.csv` | `scheduled-exports` | Legacy export → Cloud export ID |
| `*_logs.log` | all | Transformation details, warnings, errors |
| `cloud_failed_*.json` | all | Objects that failed to create in Cloud |
| `cloud_skipped_*.json` | all | Objects skipped (already exist in Cloud) |
| `legacy_*.json` | all (`--dump-legacy`) | Full Legacy object dumps |
| `cloud_*.json` | all (`--dump-cloud`) | Full Cloud object dumps |

With `--output-files-prefix foo_` or `--client-prefix foo_`, all output files get the prefix (e.g., `foo_metric_mappings.csv`).
