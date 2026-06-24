# (C) 2026 GoodData Corporation
"""
This module is used for migrating dashboard permissions and creator information.
It maps Legacy user profiles to Cloud users and updates the workspace layout accordingly.
"""

import hashlib
import json
import logging
from time import time

from gooddata_legacy2cloud.arg_parsing.arg_parser import (
    parse_dashboard_permission_cli_args,
)
from gooddata_legacy2cloud.backends.cloud.client import CloudClient
from gooddata_legacy2cloud.backends.legacy.client import LegacyClient
from gooddata_legacy2cloud.backends.legacy.filters import FilterParameters
from gooddata_legacy2cloud.backends.legacy.objects import fetch_objects_with_filters
from gooddata_legacy2cloud.config.configuration_objects import (
    DashboardPermissionsConfig,
)
from gooddata_legacy2cloud.config.env_vars import EnvVars
from gooddata_legacy2cloud.dashboard_permissions.data_classes import (
    ActualChange,
    DashboardPermissionContext,
)
from gooddata_legacy2cloud.dashboard_permissions.permissions_logger import (
    PermissionsLogger,
)
from gooddata_legacy2cloud.dashboard_permissions.permissions_updater import (
    PermissionsUpdater,
)
from gooddata_legacy2cloud.helpers import (
    duration,
    prefix_filename,
    set_output_files_prefix,
    write_content_to_file,
)
from gooddata_legacy2cloud.id_mappings import IdMappings
from gooddata_legacy2cloud.layout.layout_manager import validate_layout_structure
from gooddata_legacy2cloud.logging.config import configure_logger
from gooddata_legacy2cloud.mapping.mapping_utils import (
    filter_objects_by_mapping_files,
    format_mapping_files_info,
    get_mapping_files,
)
from gooddata_legacy2cloud.user_management.data_classes import ObjectUpdate

PERMISSIONS_CHANGES_LOG_FILE = "cloud_dashboard_permissions_changes.log"
LAYOUT_BEFORE_FILE = "cloud_layout_before.json"
LAYOUT_AFTER_FILE = "cloud_layout_after.json"

logger = logging.getLogger("migration")


def _log_mapping_info(
    dashboard_files: list[str],
    dashboard_status: dict[str, bool],
) -> None:
    """Log status of resolved mapping files."""
    info = format_mapping_files_info(dashboard_files, dashboard_status)
    logger.info("Mapping files:")
    logger.info("  Dashboard mappings: %s", info)


def _initialize_clients(env_vars: EnvVars) -> tuple[LegacyClient, CloudClient]:
    """Instantiate Legacy and Cloud API clients."""
    legacy_client = LegacyClient(
        env_vars.legacy_domain,
        env_vars.legacy_ws,
        env_vars.legacy_login,
        env_vars.legacy_password,
    )
    cloud_client = CloudClient(
        env_vars.cloud_domain,
        env_vars.cloud_ws,
        env_vars.cloud_token,
    )
    return legacy_client, cloud_client


def _warn_if_missing_mappings(dashboard_mappings: IdMappings) -> None:
    """Warn user when no dashboard mappings were found."""
    if dashboard_mappings.get():
        return
    logger.warning(
        "Dashboard mapping file is empty! "
        "No dashboards can be updated without mappings."
    )
    logger.warning("Run migrate_dashboards.py first to create the mapping file.")


def _load_legacy_dashboards(
    legacy_client: LegacyClient,
    filter_params: FilterParameters,
    config: DashboardPermissionsConfig,
    dashboard_mappings: IdMappings,
) -> list[dict]:
    """Fetch and optionally filter Legacy dashboards."""
    dashboards = []
    kpi_dashboards = []
    pp_dashboards = []
    logger.info("----Fetching Legacy dashboards----")

    if not config.skip_kpi_dashboards:
        kpi_dashboards = fetch_objects_with_filters(
            legacy_client,
            "analyticalDashboard",
            filter_params,
            "dashboards",
        )
        dashboards.extend(kpi_dashboards)

    if not config.skip_pp_dashboards:
        pp_dashboards = fetch_objects_with_filters(
            legacy_client,
            "projectDashboard",
            filter_params,
            "pixel perfect dashboards",
        )
        dashboards.extend(pp_dashboards)

    if config.object_filter_config.without_mapped_objects:
        dashboards = filter_objects_by_mapping_files(
            dashboards,
            config.object_filter_config.without_mapped_objects,
            dashboard_mappings,
            config.dashboard_mapping_file[0],
            "dashboards",
        )
    logger.info("Found %d dashboards", len(dashboards))
    logger.info("  - %d KPI dashboards", len(kpi_dashboards))
    logger.info("  - %d Pixel Perfect dashboards", len(pp_dashboards))
    return dashboards


def _build_context(
    config: DashboardPermissionsConfig,
    legacy_client: LegacyClient,
    cloud_client: CloudClient,
    dashboard_mappings: IdMappings,
) -> DashboardPermissionContext:
    """Assemble context used by PermissionsUpdater."""
    return DashboardPermissionContext(
        legacy_client=legacy_client,
        cloud_client=cloud_client,
        dashboard_mappings=dashboard_mappings,
        use_email=config.use_email,
        skip_creators=config.skip_creators,
        skip_individual_grantees=config.skip_individual_grantees,
        skip_group_grantees=config.skip_group_grantees,
        permission_level=config.permission,
        keep_existing_permissions=config.keep_existing_permissions,
        print_user_mappings=config.print_user_mappings,
        client_prefix=config.common_config.client_prefix,
    )


def _log_skip_stats(skip_stats: dict[str, int]) -> None:
    """Log statistics describing skipped dashboards."""
    no_mapping = skip_stats.get("no_cloud_mapping", 0)
    if no_mapping > 0:
        logger.warning(
            "Skipped %d dashboards: not found in dashboard_mappings.csv", no_mapping
        )
    no_user = skip_stats.get("no_user_mapping", 0)
    if no_user > 0:
        logger.warning("Skipped %d dashboards: creator not found in Cloud", no_user)


def _apply_updates_if_needed(
    config: DashboardPermissionsConfig,
    cloud_client: CloudClient,
    permissions_updater: PermissionsUpdater,
    object_updates: list[ObjectUpdate],
) -> list[ActualChange]:
    """Apply updates or log dry-run message based on CLI flags."""
    if config.common_config.skip_deploy:
        logger.info(
            "[SKIP DEPLOY] Would update %d dashboard creator records",
            len(object_updates),
        )
        logger.info("(use without --skip-deploy to apply changes)")
        return []

    logger.info("----Fetching Cloud workspace layout----")
    layout = cloud_client.get_workspace_layout()
    if config.dump_layout:
        write_content_to_file(
            LAYOUT_BEFORE_FILE,
            json.dumps(layout, indent=4),
        )
        logger.info("Layout saved to '%s'", prefix_filename(LAYOUT_BEFORE_FILE))
    if not validate_layout_structure(layout):
        logger.error("Layout structure is invalid. Cannot proceed with updates.")
        return []
    logger.info("Layout retrieved successfully")

    logger.info("----Applying layout updates----")
    original_hash = hashlib.sha256(
        json.dumps(layout, sort_keys=True).encode("utf-8")
    ).hexdigest()
    modified_layout, updates_made, not_found_count, actual_changes = (
        permissions_updater.apply_layout_updates(layout, object_updates)
    )

    if config.dump_layout:
        write_content_to_file(
            LAYOUT_AFTER_FILE,
            json.dumps(modified_layout, indent=4),
        )
        logger.info("Modified layout saved to '%s'", prefix_filename(LAYOUT_AFTER_FILE))

    modified_hash = hashlib.sha256(
        json.dumps(modified_layout, sort_keys=True).encode("utf-8")
    ).hexdigest()

    if original_hash == modified_hash:
        logger.info("No changes detected in layout - skipping API update")
        logger.info(
            "Processed %d dashboards (no permission changes needed)", updates_made
        )
        if not_found_count > 0:
            logger.info(
                "%d Dashboards from Legacy not found in Cloud layout",
                not_found_count,
            )
        return actual_changes

    logger.info("----Updating Cloud workspace layout----")
    response = cloud_client.update_workspace_layout(modified_layout)
    if response.status_code in (200, 204):
        logger.info("Layout updated successfully")
        logger.info("Updated %d dashboards", updates_made)
        if not_found_count > 0:
            logger.info(
                "%d Dashboards from Legacy not found in Cloud layout",
                not_found_count,
            )
    else:
        logger.error(
            "Failed to update layout: %s - %s", response.status_code, response.text
        )
    return actual_changes


def _write_permissions_log(
    actual_changes: list[ActualChange],
    permissions_updater: PermissionsUpdater,
    env_vars: EnvVars,
    client_prefix: str | None,
) -> None:
    """Persist permissions audit information."""
    PermissionsLogger.write_permissions_changes_log(
        PERMISSIONS_CHANGES_LOG_FILE,
        actual_changes,
        permissions_updater.user_mappings,
        permissions_updater.cloud_user_map,
        permissions_updater.cloud_usergroup_map,
        env_vars.legacy_domain,
        env_vars.legacy_ws,
        env_vars.cloud_domain,
        env_vars.cloud_ws,
        client_prefix,
    )
    logger.info(
        "Permissions changes log written to '%s'",
        prefix_filename(PERMISSIONS_CHANGES_LOG_FILE),
    )


def migrate_dashboard_permissions(config: DashboardPermissionsConfig):
    """The dashboard permissions migration process."""
    configure_logger()
    start_time = time()

    env_vars = EnvVars(config.env)
    env_vars.resolve_workspaces(config.workspace_config)
    env_vars.log_connection_info()

    if config.common_config.check_parent_workspace:
        env_vars.check_parent_workspace()

    # Initialize API clients
    legacy_client, cloud_client = _initialize_clients(env_vars)

    # Set output files prefix from command line arguments or client prefix
    prefix = (
        config.common_config.client_prefix or config.common_config.output_files_prefix
    )
    set_output_files_prefix(prefix)

    filter_params = FilterParameters.from_config(config.object_filter_config)

    # Load mapping files
    kpi_dashboard_files, kpi_dashboard_status = get_mapping_files(
        files=config.dashboard_mapping_file + config.pp_dashboard_mapping_file,
        client_prefix=config.common_config.client_prefix,
    )
    pp_dashboard_files, pp_dashboard_status = get_mapping_files(
        files=config.pp_dashboard_mapping_file,
        client_prefix=config.common_config.client_prefix,
    )
    _log_mapping_info(kpi_dashboard_files, kpi_dashboard_status)
    _log_mapping_info(pp_dashboard_files, pp_dashboard_status)
    dashboard_mappings = IdMappings(kpi_dashboard_files + pp_dashboard_files)
    _warn_if_missing_mappings(dashboard_mappings)

    # Load Legacy dashboards
    legacy_dashboards = _load_legacy_dashboards(
        legacy_client,
        filter_params,
        config,
        dashboard_mappings,
    )

    # Build context and create and instance of PermissionsUpdater
    context = _build_context(config, legacy_client, cloud_client, dashboard_mappings)
    permissions_updater = PermissionsUpdater(context)

    # Process dashboards and build object updates
    object_updates, skip_stats = permissions_updater.process_dashboards(
        legacy_dashboards
    )

    # Log skip statistics
    _log_skip_stats(skip_stats)
    if not object_updates:
        logger.info("----No objects to update----")
        legacy_client.logout()
        return
    logger.info("Found mappings for %d dashboards", len(object_updates))

    # Apply updates if needed
    actual_changes = _apply_updates_if_needed(
        config,
        cloud_client,
        permissions_updater,
        object_updates,
    )

    # Write permissions log
    _write_permissions_log(
        actual_changes,
        permissions_updater,
        env_vars,
        config.common_config.client_prefix,
    )

    # Log completion time and request count
    execution_time = duration(start_time)
    legacy_client.logout()
    logger.info("----DONE in %.2fs----", execution_time)
    logger.info("----Executed %d Cloud requests----", cloud_client.request_count.get())


def migrate_dashboard_permissions_cli():
    args = parse_dashboard_permission_cli_args()
    config = DashboardPermissionsConfig.from_kwargs(**args.__dict__)
    migrate_dashboard_permissions(config)
