# gooddata-legacy2cloud-tools

Repository for GoodData Legacy to Cloud migration tools

Recommended Python version: **>3.14.2**

## Introduction

This migration toolkit facilitates the transition of analytics content from GoodData Legacy to GoodData Cloud.

Throughout the readme and the codebase, the products are referred to as such:

- **Legacy** refers to GoodData Legacy, the legacy private cloud-based analytics solution
- **Cloud** refers to GoodData Cloud, the modern cloud-based analytics platform

**What problem does this toolkit solve?**
This toolkit automates the migration of your analytical content, preserving the relationships between different objects while handling the architectural differences between the two platforms. It can migrate:

- Logical Data Models (LDM) with data source mappings
- Metrics (calculations/measures)
- Insights (visualizations)
- KPI Dashboards
- Pixel Perfect Reports
- Pixel Perfect Dashboards

The migration can be performed as a complete workspace transfer or selectively for specific objects. The toolkit supports various migration patterns including parent/child workspace migrations and incremental updates.

You can use the [GoodData MCP Server](https://www.gooddata.ai/docs/cloud/ai/mcp-server/) to have an AI agent assist with the metadata transfer.

## Table of Contents

- [Introduction](#introduction)
- [Quick Start Guide](#quick-start-guide)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Setup](#environment-setup)
  - [Basic Migration Workflow](#basic-migration-workflow)
- [Common Use Cases](#common-use-cases)
  - [Single Workspace Migration](#single-workspace-migration)
  - [Parent/Child Workspace Migration](#parentchild-workspace-migration)
  - [Incremental Migration](#incremental-migration)
- [Migration Scripts Reference](#migration-scripts-reference)
  - [Common Parameters](#common-parameters)
  - [LDM Migration](#ldm-migration)
  - [Color Palette Migration](#color-palette-migration)
  - [Metrics Migration](#metrics-migration)
  - [Insights Migration](#insights-migration)
  - [Dashboards Migration](#dashboards-migration)
  - [Reports Migration](#reports-migration)
  - [Scheduled Exports Migration](#scheduled-exports-migration)
  - [Dashboard Permissions Migration](#dashboard-permissions-migration)

- [Advanced Topics](#advanced-topics)
  - [Filtering Objects for Migration](#filtering-objects-for-migration)
  - [Understanding Mapping Files](#understanding-mapping-files)
  - [Custom Client Object Migration](#custom-client-object-migration)
  - [Advanced Mapping File Parameters](#advanced-mapping-file-parameters)
- [Web Comparison Tool](#web-comparison-tool)
- [Standalone Tools](#standalone-tools)

## Quick Start Guide

### Prerequisites

- Python 3.14.2 or newer
- Access to both GoodData Legacy and GoodData Cloud environments
- Admin permissions for both environments

### Installation

You can install the CLI using a package manager of your choice or clone the repository and install directly from source.

### Install from PyPI

Simply install the package using pip or other package manager. It is recommended to install the package into a virtual environment

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the package
pip install gooddata-legacy2cloud
```

Or install the package as a tool using uv:

```bash
uv tool install gooddata-legacy2cloud
```

#### Install from Source

1. **Clone this repository**

    ```bash
    git clone git@github.com:gooddata/gooddata-legacy2cloud.git
    ```

1. **Install the package**

    Navigate to the cloned repository in your system and install the package in your environment.

    ```bash
    cd gooddata-legacy2cloud
    pip install .
    ```

### Environment Setup

Create a `.env` file with your access credentials:

```
LEGACY_DOMAIN = "https://your-legacy-domain.com/"
LEGACY_LOGIN = "your_username"
LEGACY_PASSWORD = "your_password"
LEGACY_WS = "your_legacy_workspace_id"

CLOUD_DOMAIN = "https://your-cloud-domain.gooddata.com/"
CLOUD_TOKEN = "your_bearer_token"
CLOUD_WS = "your_cloud_workspace_id"

DATA_SOURCE_ID = "your_data_source_id"
SCHEMA = "your_schema"
TABLE_PREFIX = "your_table_prefix"

# Optional parameters
WS_DATA_FILTER_ID = "filter_id"
WS_DATA_FILTER_COLUMN = "filter_column"
WS_DATA_FILTER_DESCRIPTION = "filter_description"

# Notification channel ID is required for scheduled exports migration
CLOUD_NOTIFICATION_CHANNEL_ID=notification_channel_to_use_with_migrated_exports
```

**Where to find these values:**
- **LEGACY_WS**: Navigate to your GoodData Legacy workspace and copy the project ID (PID) from the URL
- **CLOUD_TOKEN**: Generate a token in GoodData Cloud under User Settings > API Tokens
- **DATA_SOURCE_ID**: Get this from your Cloud workspace data source settings (create the data source before the migration)

### Basic Migration Workflow

> You can use the GoodData MCP Server to guide you through the process. If you want to perform the steps manually, follow the steps outlined below.

Run these scripts in sequence, verifying results after each step:

1. **Migrate the Logical Data Model**

   ```
   gooddata-legacy2cloud ldm
   ```

   - Check in Cloud that your data model has been migrated correctly, check the data mapping if it was migrated
   - Review any warnings or errors in the modeller

1. **Migrate the color palette**

   ```bash
   gooddata-legacy2cloud color-palette
   ```

1. **Migrate Metrics**

   ```
   gooddata-legacy2cloud metrics
   ```

   Verify the metrics in Cloud, especially any with [ERROR] or [WARN] in the title

1. **Migrate Insights (Visualizations)**

   ```
   gooddata-legacy2cloud insights
   ```

   Verify the insights in Cloud, especially any with [ERROR] or [WARN] in the title

1. **Migrate Dashboards**

   ```
   gooddata-legacy2cloud dashboards
   ```

   Verify the dashboards in Cloud

1. **Migrate Pixel Perfect Reports**

   ```
   gooddata-legacy2cloud reports
   ```

   Verify the Visualziations migrated from report in Cloud (by default they will have "[PP]" prefix)

1. **Migrate Pixel Perfect Dashboards**

   ```bash
   gooddata-legacy2cloud pp-dashboards
   ```

   Verify the migrated Dashboards in Cloud

## Common Use Cases

### Single Workspace Migration

Migrating all content from one GoodData Legacy workspace to one GoodData Cloud workspace:

1. **Set up your environment file** with source and target workspace IDs
2. **Run the migration scripts in sequence**:
   ```
   gooddata-legacy2cloud ldm
   gooddata-legacy2cloud metrics
   gooddata-legacy2cloud insights
   gooddata-legacy2cloud dashboards
   ```
3. **Verify the migrated content** in your Cloud workspace

### Parent/Child Workspace Migration

For organizations with multiple workspaces that share content and want to also migrate the custom objects from client workspaces:

1. **Prepare your Cloud environment**:
   - Create an empty parent workspace in Cloud
   - Create a child workspace for each client workspace in Cloud

2. **Migrate the parent workspace** first:

   ```
   gooddata-legacy2cloud ldm
   gooddata-legacy2cloud metrics
   gooddata-legacy2cloud insights
   gooddata-legacy2cloud dashboards
   gooddata-legacy2cloud reports
   ```

   - **Note:** This migration toolkit does **not** create workspaces or provision users, user groups, or user permissions (except dashboard permissions). You must create all client workspaces to the Cloud organization separately before running the migration. If you want to migrate also dashboard permissions or scheduled emails, you also need to provision the users/user groups before that.

   **Important:** : If you plan to use Workspace Data Filters to restrict which data each client workspace in Cloud can access, verify that you have the Workspace Data Filters defined and properly mapped for all datasets in LDM of your parent workspace. [Documentation](https://www.gooddata.com/docs/cloud/workspaces/workspace-data-filters/)

3. **Migrate each client workspace** with client-specific prefix:

   Note: The `--client-prefix` parameter automatically:
   - Reads mappings from default mapping file (belonging to the parent) as well as client-specific mapping file (with defined client-specific prefix)
   - Only migrates objects not present in the parent (=not present in the default mapping files)
   - Prefixes any mapping or log it creates with the defined client-specific prefix (to prevent overwriting and easy identification)
   - Validates that the target workspace is a child workspace (=has parent defined)
   - Requires use of --legacy-ws and --parent-ws to prevent accidentally migrating into parent workspace in client mode

   ```
   # For client 1
   gooddata-legacy2cloud metrics --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
   gooddata-legacy2cloud insights --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
   gooddata-legacy2cloud dashboards --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
   gooddata-legacy2cloud reports --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
   # For client 2
   gooddata-legacy2cloud metrics --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_
   gooddata-legacy2cloud insights --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_
   gooddata-legacy2cloud dashboards --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_
   gooddata-legacy2cloud reports --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_

   # Repeat for each client
   ```

   Which would first completely migrate each client workspace (metrics, insights and dashboards) and then continue to the next one.
   Alternatively You can also first migrate all metrics in all workspaces, then all insights in all workspaces and then all dashboards in all workspaces:

```bash
# Migrate all clients metrics
gooddata-legacy2cloud metrics --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
gooddata-legacy2cloud metrics --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_
# Repeat for each client

# Migrate all clients insights
gooddata-legacy2cloud insights --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_
gooddata-legacy2cloud insights --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
# Repeat for each client

# Migrate all clients dashboards
gooddata-legacy2cloud dashboards --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
gooddata-legacy2cloud dashboards --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_
# Repeat for each client

# Migrate all clients reports
gooddata-legacy2cloud reports --legacy-ws client1_legacy_id --cloud-ws client1_cloud_id --client-prefix client1_
gooddata-legacy2cloud reports --legacy-ws client2_legacy_id --cloud-ws client2_cloud_id --client-prefix client2_
# Repeat for each client
```

### Incremental Migration

Migrating only new objects added since your last migration:

```
gooddata-legacy2cloud metrics --without-mapped-objects
gooddata-legacy2cloud insights --without-mapped-objects
gooddata-legacy2cloud dashboards --without-mapped-objects
gooddata-legacy2cloud reports --without-mapped-objects
```

Note that the migration scripts currently do not support overwriting already existing objects in Cloud. Instead of overwriting, any object with ID already existing in the Cloud workspace is skipped.

## Migration Scripts Reference

### Common Parameters

These parameters are available in all migration scripts:

**--help** - Display help information about the script

**--env [path_to_env_file]** - Specify a custom .env file (default: .env)

**--legacy-ws** - Source Legacy workspace ID. Overrides LEGACY_WS from the .env file (required for --client-prefix)

**--cloud-ws** - Target Cloud workspace ID. Overrides CLOUD_WS from the .env file (required for --client-prefix)

**--skip-deploy** - Skip deployment to Cloud (useful for testing)

**--dump-legacy** - Dump Legacy objects to a JSON file

**--dump-cloud** - Dump Cloud objects to a JSON file

**--cleanup-target-env** - Remove ALL existing objects of that type (i.e. metrics for `metrics`) in the target environment before migration

**--overwrite-existing** - Updates existing objects instead of skipping them. Affects also dashboard components like filter contexts and comparison widgets that are created during migration of the dashboard.

**--output-files-prefix [prefix]** - Add a specified prefix to all output filenames the script generates (mapping files, logs, ...)

**--check-parent-workspace** - Before starting migration check that the target Cloud workspace has a parent workspace

**--client-prefix [prefix]** - Special parameter for easy migration of objects in client workspaces - see [Custom Client Object Migration](#custom-client-object-migration)

**--suppress-migration-warnings** - Suppress migration warnings from being added to object titles and descriptions. Warnings will still be printed to console for visibility. This parameter only affects warnings; errors are still added to objects.

#### Element Lookup Parameters

These parameters optimize the lookup of attribute element values (filter values) from Legacy during migration. In Legacy normally if an attribute value is used in an object definition (i.e. a filter) it has to be present in the workspce to be able to read and migrate it. Otherwise a manual fix is needed to the migrated object. These parameters allow to overcome this limation by looking up the value in the Legacy workspace Validation that checks reports and metrics for missing values.
These are meant to fill-in a few missing values, do not run the migration tool with these on an empty workspace.

**--element-values-prefetch** - Scans objects for migration for attribute element URIs and batch-fetches their values before processing. This optimization reduces Legacy API calls during migration. Works independently of validation. Does not fix any missing values by itself.

**--validation-element-lookup** - Uses Legacy's workspace validation endpoint to fetch missing attribute element values. The validation process returns missing element values for used in metrics and reports and they are later used for the migration of missing values.

**--validation-element-lookup-with-metrics** - Advanced strategy combining values prefetch prefetch with temporary Legacy metric creation for comprehensive element lookup. it creates temporary metrics in the Legacy workspace for any unmapped elements, runs validation to populate cache from these metrics, and finally deletes the temporary metrics. This requires permission to create and delete metrics in the Legacy workspace. Includes prefetch and validation, no need to use the other `*-element-*` parameters with it.
This parameter is only available for `insights` and `dashboards`

### LDM Migration

```
gooddata-legacy2cloud ldm
```

Script generates:

- LDM object mappings to `ldm_mappings.csv`

**LDM-specific options:**

**--ignore-folders** - Legacy folders for LDM objects are not migrated to Cloud tags. Use if you used only tags for organizing the catalog in Legacy.

**--ignore-explicit-mapping** - Explicit LDM mapping (Legacy Mapping from Modeler used for ADDv2) is not used even if it exists. Instead the ADS naming convention is used for LDM mapping.

### Metrics Migration

```
gooddata-legacy2cloud metrics
```

Script generates:

- Metric mappings to `metric_mappings.csv`
- MAQL transformation log to `metrics_maql.log`
- Failed Cloud metrics to `cloud_failed_metrics.json`
- Skipped objects IDs to `cloud_skipped_metrics.json`

Script reads:

- LDM mappings from `ldm_mappings.csv`

Notes:

- If any element values are missing within the Legacy metric, they are replaced with `--MISSING VALUE--`. Such metrics can be found in `metrics_maql.log` file and these metrics are also marked with [WARN] in their title (unless `--suppress-migration-warnings` is used). Warnings are always printed to console.
- If converted MAQL fails to be saved to Cloud, such metrics are converted to "ERROR metrics". These have [ERROR] in their title, their definition is changed to `SELECT SQRT(-1)` (=returns NULL) and their original converted MAQL is left in the comment. These metrics should be manually inspected.
- Objects that already exist in Cloud (based on their ID) are skipped and their IDs are recorded in the skipped objects file (unless `--overwrite-existing` is used).
- To prevent missing element values, use `--validation-element-lookup` (see [Element Lookup Parameters](#element-lookup-parameters))

**Metrics-specific options:**

**--keep-original-ids** - Keep original metric identifiers from Legacy. Otherwise the Cloud ID is derived from metric title and Legacy identifier.

**--ignore-folders** - Legacy folders of Metrics are not migrated to Cloud tags. Use if you used only tags for organizing the catalog in Legacy.

### Color Palette Migration

```bash
gooddata-legacy2cloud color-palette
```

Migrate color palette from Legacy workspace and set it as the default palette at Organization level. This will also remove all other existing color palettes from the organization. Migrating color palettes per workspace is currently not supported.

To see the supported CLI arguments, run

```bash
gooddata-legacy2cloud color-palette --help
```

### Insights Migration

```bash
gooddata-legacy2cloud insights
```

Script generates:

- Insights mappings to `insight_mappings.csv`
- Insights transformation log to `insight_logs.log`
- Failed Cloud insights to `cloud_failed_insights.json`
- Skipped objects IDs to `cloud_skipped_insights.json`

Script reads:

- LDM mappings from `ldm_mappings.csv`
- Metric mappings from `metric_mappings.csv`

Notes:

- If any element values used in Legacy insight filter definition are missing, they are removed and such insight is marked as [WARN] (unless `--suppress-migration-warnings` is used). It should be manually inspected. Information about what is missing is added to the insight description. Warnings are always printed to console.
- If there are any errors in Cloud insight creation, such insights can be found in `insights_logs.log` file.
- The script cannot migrate Geo charts at this time.
- Objects that already exist in Cloud (based on their ID) are skipped and their IDs are recorded in the skipped objects file (unless `--overwrite-existing` is used).
- For best results with element lookup, use `--validation-element-lookup-with-metrics` (see [Element Lookup Parameters](#element-lookup-parameters))

**Insights-specific options:**

**--keep-original-ids** - Keep original Legacy identifiers as Cloud IDs instead of generating new ones. Otherwise the Cloud ID is derived from the insight title and Legacy identifier.

### Dashboards Migration

```bash
gooddata-legacy2cloud dashboards
```

Script generates:

- Dashboards mappings to `dashboard_mappings.csv`
- Dashboards transformation log to `dashboards_logs.log`
- Failed Cloud dashboards to `cloud_failed_dashboards.json`
- Skipped objects IDs to `cloud_skipped_dashboards.json`

Script reads:

- LDM mappings from `ldm_mappings.csv`
- Metric mappings from `metric_mappings.csv`
- Insights mappings from `insight_mappings.csv`

Notes:
This script only migrates the Responsive Dashboards (a.k.a. KPI Dashboards). The tooling currently does not migrate Pixel Perfect Dashboards.

- If any element values used in the Legacy definition of a Dashboards is missing within the Legacy dashboards, they are removed and such dashboard is marked as [WARN] (unless `--suppress-migration-warnings` is used) with details in the description for manual inspection. Warnings are always printed to console.
- If there are any errors in Cloud dashboard creation, such dashboards can be found in `dashboards_logs.log` file.
- All migrated dashboards are first created as empty ones and in the next phase updated to the final structure to make sure all drillToDashboards have existing target. If some target is missing (i.e. because that dashboard is not migrated) such drill is removed and the dashboard is marked as [WARN] (unless `--suppress-migration-warnings` is used) and details about removed drills are put into its description. Warnings are always printed to console.
- Objects that already exist in Cloud (based on their ID) are skipped and their IDs are recorded in the skipped objects file (unless `--overwrite-existing` is used).
- For best results with element lookup, use `--validation-element-lookup-with-metrics` (see [Element Lookup Parameters](#element-lookup-parameters))

**Dashboards-specific options:**

**--keep-original-ids** - Keep original Legacy identifiers as Cloud IDs instead of generating new ones. Otherwise the Cloud ID is derived from the dashboard title and Legacy identifier.

### Pixel Perfect Dashboards Migration

```bash
gooddata-legacy2cloud pp-dashboards
```

Notes:

- By default, each Legacy Pixel Perfect dashboard is migrated **one-to-one** into a single Cloud KPI dashboard that uses **native tabs** (one Legacy tab -> one Cloud tab).
- Use `--pp-legacy-split-tabs` to enable the legacy behavior where each Legacy tab is migrated as a separate Cloud dashboard (intended for transition only).
- Use `--keep-original-ids` to keep the Legacy PP dashboard identifier as the Cloud dashboard ID. Cannot be combined with `--pp-legacy-split-tabs`. Note that dashboards created with this flag will not be removed when `--cleanup-target-env` is used AND will get removed if you migrate regular dashboards with `--cleanup-target-env` after this.

### Reports Migration

```bash
gooddata-legacy2cloud reports
```

Script generates:

- Report mappings to `report_mappings.csv`
- Reports transformation log to `report_logs.log`
- Failed Cloud reports to `cloud_failed_reports.json`
- Skipped objects IDs to `cloud_skipped_reports.json`

Script reads:

- LDM mappings from `ldm_mappings.csv`
- Metric mappings from `metric_mappings.csv`

Notes:

- This script performs a best-effort migration of Pixel Perfect Reports from Legacy to Cloud.
- Pixel Perfect reports do not exist in Cloud, the script converts them to Cloud visualizations as closely as possible. The visual appearance may differ.
- Some features specific to Pixel Perfect reports (i.e. types of filters) might not be available in Cloud.
- Reports containing features not available in Cloud are marked by adding [WARN] to the migrated visualization name (unless `--suppress-migration-warnings` is used). Details are added to the description. Warnings are always printed to console.
- To prevent missing element values, use `--validation-element-lookup` (see [Element Lookup Parameters](#element-lookup-parameters))

**Reports-specific options:**

**--report-prefix** - Prefix added to the visualziations migrated from PixelPerfect reports to distinguish them from those migrated from Insights. Default is '[PP] '. Use empty string to disable the prefix.

**--keep-original-ids** - Keep original metric identifiers from Legacy. Otherwise, the Cloud ID is derived from metric title and Legacy identifier. Note that insights created with this flag will not be removed when `--cleanup-target-env` is used AND will get removed if you migrate regular insights with `--cleanup-target-env` after this.

### Scheduled Exports Migration

```bash
gooddata-legacy2cloud scheduled-exports
```

Script generates:

- Export mappings to `scheduled_export_mappings.csv`
- Metadata transformations log to `scheduled_exports_logs.log`

Script reads:

- Insight mappings from `insight_mappings.csv`
- Dashboard mappings from `dashboard_mappings.csv`

Prerequisities:

- The LDM, insights and dashboards need to be migrated prior to sheduled exports.
- Legacy users need to be provisioned in Cloud. The script will match `to` recipients based on email. Existence of `bcc` recipients is not checked.

- `CLOUD_NOTIFICATION_CHANNEL_ID` environment variable needs to be set.

Notes:

- By default, the script does not migrate such scheduled emails which do not have a recipient or any attachment.
- If Legacy recipient from `to` field does not exist in Cloud, they are skipped. The script will still attempt to create the export.
- Legacy recipients from `to` field are mapped to Cloud `recipients`, Legacy `bcc` email addresses will be set as `external_recipients` in Cloud.
- Only scheduled emails from Legacy KPI dashboards are migrated. The script does not migrate automations generated on Pixel Perfect reports.
- If a migrated Legacy export uses only dashboard filters, but those filters have values selected, these filter values will be baked into the Cloud automation. This could be adjusted for visual exports (PDF), but Cloud tabular exports (CSV, XLSX) can only be created with persistent filter selections.

**Reports-specific options:**

**--exports-to-migrate** - List of specific scheduled exports to migrate. The value should be a path to a csv containing a single column (without header) with Legacy IDs of scheduled exports which should be migrated.

### Dashboard Permissions Migration

After migrating dashboards from Legacy to Cloud, and provisioning users and user groups to your Cloud Organization (which is not done by this migration toolkit), you can migrate dashboard ownership and permissions to properly attribute ownership and access rights to non-public dashboards to the original users and user groups.

```bash
gooddata-legacy2cloud dashboard-permissions
```

**What this script does:**

1. Fetches selected Legacy dashboards based on filter parameters
2. Identifies the creator (account that created the dashboard) from Legacy
3. Collects sharing information (grantees) from Legacy dashboard permissions
4. Maps Legacy users to Cloud users based on either Legacy `email` field or Legacy `login` field
5. Maps Legacy user groups to Cloud user groups based on group names
6. Updates the Cloud workspace layout to reflect the correct creator and dashboard permissions for matched users and user groups

**Script generates:**

- Consolidated permissions changes log to `cloud_dashboard_permissions_changes.log` (includes creator updates and permission changes)
- Optional layout dumps: `cloud_layout_before.json` and `cloud_layout_after.json` (with `--dump-layout`)

**Script reads:**

- Dashboard mappings from `dashboard_mappings.csv`

**Prerequisites:**

- Dashboards need to be migrated to Cloud before running this script
- Legacy users should be provisioned in Cloud with matching identifiers:
  - By default: Legacy `login` field should match Cloud user `email` field
  - With `--use-email`: Legacy `email` field (not `login`) should match Cloud user `email` field
- Legacy user groups should exist in Cloud with matching names
  - Note that while in Legacy the user groups are workspace-specific, in Cloud they are organization-wide
- User account executing the migration needs `org.MANAGE` permissions to update workspace layout via API

**Dashboard Permissions-specific options:**

**--dump-layout** - Store the layout JSON locally before and after modifications for debugging purposes

**--use-email** - Use Legacy email field instead of login field when matching Legacy users to Cloud users. By default, the script uses the login field from Legacy users to match against Cloud user emails. With this parameter it uses email field from Legacy users to match against Cloud user emails.

**--skip-creators** - Skip migrating creator permissions (only migrate grantees)

**--skip-individual-grantees** - Skip migrating individual user grantee permissions (only migrate creators and group grantees)

**--skip-group-grantees** - Skip migrating user group grantee permissions (only migrate creators and individual grantees)

**--permission [VIEW|SHARE|EDIT]** - Dashboard permission level to assign to grantee users and user groups (default: EDIT). The dashboard creator always receives EDIT permission regardless of this setting. Note that in Legacy there was only a single dashboard permission and ability to edit was determined by user role in the workspace.

**--print-user-mappings** - Print detailed user mapping information for each Legacy user during the migration process

**--keep-existing-permissions** - Keep existing Cloud permissions that are not present in the Legacy source. Without this flag the script removes unmanaged permissions during the synchronization step.

**--skip-kpi-dashboards** - Skip adjusting permissions of KPI dashboards.

**--skip-pp-dashboards** - Skip adjusting permissions of Pixel Perfect dashboards.

**--pp-dashboard-mapping-file** - Path to the Pixel Perfect dashboards mapping file.

**Example usage:**

```bash

# Migrate all permissions (creators, users, and groups)
gooddata-legacy2cloud dashboard-permissions

# Only migrate creators, skip all grantees
gooddata-legacy2cloud dashboard-permissions --skip-individual-grantees --skip-group-grantees

# Migrate with VIEW permission for grantees instead of EDIT
gooddata-legacy2cloud dashboard-permissions --permission VIEW

# Update with client prefix
gooddata-legacy2cloud dashboard-permissions --client-prefix client1_ --legacy-ws client1_legacy_ws --cloud-ws client1_cloud_ws
```

**Important notes:**
**Warning:** By default this script synchronizes permissions, meaning it removes any Cloud permissions that do not exist in Legacy (unless they belong to sections skipped with `--skip-*`). This includes the permission of the account used for the migraiton! Workspace admins can still see all the dashboards. Use `--keep-existing-permissions` to keep extra Cloud permissions untouched.

- This script modifies the workspace layout directly via the Layout API
- Always test with `--skip-deploy` first to preview changes
- The script only logs actual changes made, not items that were already correct
- User mapping is case-sensitive:
  - By default: Legacy `login` field is matched against Cloud user `email`
  - With `--use-email`: Legacy `email` field is matched against Cloud user `email`
- User group mapping is based on exact name matching between Legacy and Cloud
- The script does not provision users or user groups to the Cloud organization
- The script does not grant users workspace permissions (only dashboard-specific permissions)
- The log file groups changes by dashboard title with one JSON line per change for easy parsing

## Advanced Topics

### Filtering Objects for Migration

The migration scripts provide flexible filtering options to control which objects get migrated. All these parameters only apply to `metrics`, `insights` and `dashboards`. (Logical Data Model is always migrated as a complete).
The filtering works as a two-step process. First set of parameters (--only-\* parameters) defines which objects are being read from Legacy. Then these can be further filtered down by various properties defined by a second set of parameters (--with\_/--without\*).

#### Initial Object Selection (--only-\* parameters)

Controls which objects are gathered from Legacy for the migration:

- **--only-object-ids** - Only migrate specific objects by their numeric IDs (comma-separated)
- **--only-identifiers** - Only migrate specific objects by their alphanumeric identifiers (comma-separated)
- **--only-object-ids-with-dependencies** - Same as --only-object-ids, but also includes all their dependent objects
- **--only-identifiers-with-dependencies** - Same as --only-identifiers, but also includes all their dependent objects

Note that each script will still only migrate one type of objects (e.g. `metrics` migrates metrics) but you can pass objects of any types to the --only-identifiers-with-dependencies and --only-object-ids-with-dependencies parameters. It will find dependent objects of the proper type to migrate. This is useful if you want to migrate a few dashboards and do not want to explicitly list all their dependent metrics and insights.

Only one of these parameters can be used at a time.

#### Post-Download Filtering (--with*/--without* parameters)

Further filter the downloaded objects based on specific features before migrating them:

- **--with-tags** - Only migrate downloaded objects with at least one of the specified tags (comma-separated)
- **--without-tags** - Only migrate downloaded objects that don't have any of the specified tags (comma-separated)
- **--with-locked-flag** - Only migrate downloaded objects that have locked=1 flag in their metadata
- **--without-locked-flag** - Only migrate downloaded objects that have locked=0 or no locked flag in their metadata
- **--with-creator-profiles** - Only migrate downloaded objects created by one of the specified Legacy user profile IDs (comma-separated, without /gdc/account/profile/ prefix)
- **--without-creator-profiles** - Only migrate downloaded objects NOT created by any of the specified Legacy user profile IDs (comma-separated, without /gdc/account/profile/ prefix)
- **--without-mapped-objects** - Filter out downloaded objects with Legacy identifiers already present in the corresponding mapping file(s). By default, checks all (default and additional) mapping files. Use --without-mapped-objects default_only to only check the default mapping file.

Multiple --with*/--without* parameters can be used together and are treated with AND operator

**Note on Creator Profiles:** The Legacy user profile ID can be found in the object's metadata under the `author` field. It's formatted as `/gdc/account/profile/{profile_id}`. When using the `--with-creator-profiles` or `--without-creator-profiles` parameters, provide only the `{profile_id}` part (e.g., `0102b54c3859150e0d75e52f1a3d034f`).

### Understanding Mapping Files

Mapping files are critical for the migration process:

- Each migration script generates a mapping file of the objects it migrated (e.g., ldm_mappings.csv, metric_mappings.csv)
- These files contain "Legacy ID (identifier)" to "Cloud ID" mappings
- Later scripts use these mappings to establish relationships between migrated objects
- Presence of an identifier in the mapping file (from previous migration runs) can also be used to filter which objects to migrate
- There can be more than one mapping file on the script input - in that case all are used combined
- In case of --client-prefix the default mapping file is meant to have objects from the parent workspace and client-prefixed mapping file is meant to contain client-specific objects.

### Custom Client Object Migration

Cloud supports true inheritance of objects between workspaces, while in Legacy all the objects are local copies. To properly migrate between these two paradigms, you need to decide what is common and should go to the parent and what are client-specific objects and will go to individual client workspaces.

The migration tooling does support this use case directly with a parameter --client-prefix:

**--client-prefix [prefix]** - This parameter does several things at once:

- Sets the prefix for all output files (same as --output-files-prefix)
- Enables checking the parent workspace (same as --check-parent-workspace)
- **Must** be used together with --legacy-ws and --cloud-ws parameters
- Looks for both standard and prefixed mapping files (i.e. metric_mappings.csv and client1_metric_mappings.csv) if found, will use both
- Automatically enables filtering by default mapping files (same as --without-mapped-objects default_only)

This combined behavior is ideal for migration of individual client workspaces after the parent/master workspace was migrated.
All the objects migrated to the parent workspace are in the default mapping files, while for each client workspace a new prefixed mapping file with objects specific to that workspace is created.

The target Cloud workspace already must be in a workspace hierarchy and have a parent defined.

**Note:** When using `--client-prefix`, you **must** also specify `--legacy-ws` and `--cloud-ws` parameters. This is a safety measure to ensure you're migrating between the correct client workspaces, not accidentally using the master workspaces from your .env file.

```bash
gooddata-legacy2cloud insights --client-prefix client1_ --legacy-ws client1_ws --cloud-ws client1_cloud_ws
```

### Advanced Mapping File Parameters

These parameters control which mapping files are used as input for each script and where the output mappings are written.

#### Main Mapping File Parameters

These parameters override the default mapping files used by the scripts:

| Parameter                    | Default Value          | Read by Scripts               | Generated by Script | Description                                                                                                                                          |
| ---------------------------- | ---------------------- | ----------------------------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **--ldm-mapping-file**       | ldm_mappings.csv       | metrics, insights, dashboards | ldm                 | Specifies the LDM mapping file(s) to read from. First file is used for output, all for input. Comma-separated list.                                  |
| **--metric-mapping-file**    | metric_mappings.csv    | insights, dashboards          | metrics             | Specifies the metric mapping file(s) to read from and for metrics to write to. First file is used for output, all for input. Comma-separated list.   |
| **--insight-mapping-file**   | insight_mappings.csv   | dashboards                    | insights            | Specifies the insight mapping file(s) to read from and for insights to write to. First file is used for output, all for input. Comma-separated list. |
| **--dashboard-mapping-file** | dashboard_mappings.csv | None                          | dashboards          | Specifies the dashboard mapping file(s) for dashboards to write to. First file is used for output, all for input. Comma-separated list.              |

When specifying multiple files with comma separation, only the first file is used for writing new mappings, while all files are used for reading existing mappings.

#### Using Multiple Mapping Files

You can specify multiple mapping files in two ways:

1. **Using comma-separated lists:**

```bash
gooddata-legacy2cloud insights --metric-mapping-file main_metrics.csv,project1_metrics.csv,project2_metrics.csv
```

This loads all three mapping files for lookups

2. **Using --client-prefix:**

```bash
gooddata-legacy2cloud insights --client-prefix client1_
```

This loads both the default file (e.g., metric_mappings.csv) and the prefixed version (e.g., client1_metric_mappings.csv) if it exists.

The --client-prefix parameter is a handy shortcut that automatically sets --output-files-prefix to the same value and loads both default and prefixed mapping files.

## Web Comparison Tool

The toolkit includes a web-based comparison tool that visualizes migration results in user-friendly HTML pages, making it easy to review and validate migrated content.

```bash
gooddata-legacy2cloud web-compare
```

### Key Features

- Automatically processes all migration log files in a directory
- Detects object types (metrics, insights, dashboards) and client prefixes from log filenames
- Generates a separate HTML page for each log file with detailed migration results
- Provides side-by-side comparison view of objects in Legacy and Cloud
- Organizes prefixed client outputs in separate directories. Shows also objects inherited from the hierarchy
- Includes filtering, sorting, and search capabilities in the web interface
- Works completely offline without requiring a web server

### Basic Usage

```bash
# Process logs in current directory, output to `compare_web` folder
gooddata-legacy2cloud web-compare --env .env

# Specify custom directories
gooddata-legacy2cloud web-compare --log-dir=logs/project1 --output-dir=reviews/project1

# Do not show inherited objects for client workspaces
gooddata-legacy2cloud web-compare --skip-inherited
```

### Workspace Structure

The tool creates a structured output directory:

- Main HTML files for unprefixed (parent) workspace in the root output directory
- Subdirectories for each client prefix containing their specific HTML files
- A shared `resources` directory with CSS, JavaScript, and images (shared between parent and all clients)

This structure allows you to easily share the results with clients by copying their specific folder along with the resources directory. In such case the links to parent workspace will be automatically deactivated.

### Using the Web Interface

The web interface provides several powerful features:

1. **Navigation**
   - Use the left sidebar to switch between object types and client workspaces
   - Click on "BACK TO PARENT" to return from client workspace to parent workspace view

2. **Filtering and Searching**
   - Click the summary cards at the top to filter by migration status
   - Use the search box to find specific objects by title or ID
   - Sort the table by clicking on any column header

3. **Object Comparison**
   - Click the "Compare" button to open a live side-by-side view of the object in Legacy and Cloud
   - Use the divider controls to adjust the split view ratio (the arrow icons maximize one of the views, the = sign splits the view equally).
   - Navigate between individual objects with Previous/Next buttons
   - Open either object in its full native UI with the "Open in Legacy/Cloud" buttons
   - Compare and Legacy and Cloud workspace links require valid GoodData sessions in your browser to work
   - Note: For Pixel Perfect Reports, the comparison is currently not avialable for inherited objects

4. **Status Indicators**
   - Color-coded status icons show the migration outcome for each object
   - Hover over status icons for detailed information
   - Click the info (ℹ️) icon to view detailed error messages, warnings or object descriptions.

### Command Line Options

Usage: gooddata-legacy2cloud web-compare [options]

Options:
| Option | Description |
|-|-|
| --env ENV_FILE | Environment file to use for fallback workspace IDs |
| --log-dir LOG_DIR | Path to directory with migration log files (default: current directory) |
| --output-dir DIR | Directory to write HTML output to (default: compare_web) |
| --skip-inherited | Do not include objects inherited from parent workspace into client pages |

### Notes

- The output HTML pages work completely offline and can be viewed locally in a modern browser
- In case of browser with restrictions on local file access (like Safari), you can overcome it by running a simple local web server i.e. in Python:

```
python3 -m http.server 8000
```

Then open: http://localhost:8000/dashboards_web_compare.html

## Standalone Tools

There are standalone tools that can support the migration process, even though they do not migrate any objects directly.
Have a look at the [tools/README](tools/README.md) to find out more
