# (C) 2026 GoodData Corporation
"""
This module is used for migrating dashboards. It includes functionality for
loading environment variables, setting up command line arguments, and running
the main migration process.
"""

import json
import logging
from time import time

from gooddata_legacy2cloud.arg_parsing.arg_parser import parse_dashboard_cli_args
from gooddata_legacy2cloud.backends.cloud.client import CloudClient
from gooddata_legacy2cloud.backends.cloud.object_creator import (
    process_objects,
    update_dashboards_with_full_content,
)
from gooddata_legacy2cloud.backends.cloud.object_creator_strategy import (
    CLOUD_FAILED_KPI_COMPARISON_INSIGHTS_FILE,
)
from gooddata_legacy2cloud.backends.legacy.client import LegacyClient
from gooddata_legacy2cloud.backends.legacy.filters import FilterParameters
from gooddata_legacy2cloud.backends.legacy.objects import (
    fetch_dashboard_content,
    fetch_objects_with_filters,
)
from gooddata_legacy2cloud.config.configuration_objects import DashboardConfig
from gooddata_legacy2cloud.config.env_vars import EnvVars
from gooddata_legacy2cloud.dashboards.cloud_dashboards_builder import (
    CloudDashboardsBuilder,
)
from gooddata_legacy2cloud.dashboards.data_classes import DashboardContext
from gooddata_legacy2cloud.helpers import (
    duration,
    prefix_filename,
    set_output_files_prefix,
    write_content_to_file,
)
from gooddata_legacy2cloud.id_mappings import IdMappings
from gooddata_legacy2cloud.logging.config import (
    configure_logger,
)
from gooddata_legacy2cloud.mapping.mapping_utils import (
    filter_objects_by_mapping_files,
    format_mapping_files_info,
    get_mapping_files,
)
from gooddata_legacy2cloud.metrics.element_prefetcher import ElementPrefetcher
from gooddata_legacy2cloud.models.enums import Operation
from gooddata_legacy2cloud.output_writer import OutputWriter

LEGACY_DASHBOARDS_FILE = "dashboards.json"
CLOUD_DASHBOARDS_FILE = "cloud_dashboards.json"

logger = logging.getLogger("migration")
configure_logger()


def migrate_dashboards(config: DashboardConfig):
    """The dashboard migration process."""
    start_time = time()

    env_vars = EnvVars(config.env)
    env_vars.resolve_workspaces(config.workspace_config)
    env_vars.log_connection_info()

    if config.common_config.check_parent_workspace:
        env_vars.check_parent_workspace()

    # Set output files prefix from command line arguments or client prefix
    if config.common_config.client_prefix:
        set_output_files_prefix(config.common_config.client_prefix)
    else:
        set_output_files_prefix(config.common_config.output_files_prefix)

    # Extract filter parameters from args
    filter_params = FilterParameters.from_config(config.object_filter_config)

    # Determine which mapping files to use with their status
    ldm_files, ldm_status = get_mapping_files(
        files=config.ldm_mapping_file,
        client_prefix=config.common_config.client_prefix,
    )

    metric_files, metric_status = get_mapping_files(
        files=config.metric_mapping_file,
        client_prefix=config.common_config.client_prefix,
    )

    insight_files, insight_status = get_mapping_files(
        files=config.insight_mapping_file,
        client_prefix=config.common_config.client_prefix,
    )

    dashboard_files, dashboard_status = get_mapping_files(
        files=config.dashboard_mapping_file,
        client_prefix=config.common_config.client_prefix,
    )

    # Log information about which files are being used with their status
    logger.info("Mapping files:")
    logger.info("  LDM mappings: %s", format_mapping_files_info(ldm_files, ldm_status))
    logger.info(
        "  Metric mappings: %s", format_mapping_files_info(metric_files, metric_status)
    )
    logger.info(
        "  Insight mappings: %s",
        format_mapping_files_info(insight_files, insight_status),
    )
    logger.info(
        "  Dashboard mappings: %s",
        format_mapping_files_info(dashboard_files, dashboard_status),
    )

    legacy_client = LegacyClient(
        env_vars.legacy_domain,
        env_vars.legacy_ws,
        env_vars.legacy_login,
        env_vars.legacy_password,
    )

    cloud_client = CloudClient(
        env_vars.cloud_domain, env_vars.cloud_ws, env_vars.cloud_token
    )

    # Initialize mappings with multiple files
    ldm_mappings = IdMappings(ldm_files)
    metric_mappings = IdMappings(metric_files)
    insight_mappings = IdMappings(insight_files)
    dashboard_mappings = IdMappings(dashboard_files)

    # First file is used for writing mappings
    primary_dashboard_file = (
        dashboard_files[0] if dashboard_files else config.dashboard_mapping_file
    )
    mapping_logger = OutputWriter(primary_dashboard_file)

    ctx = DashboardContext(
        legacy_client=legacy_client,
        cloud_client=cloud_client,
        ldm_mappings=ldm_mappings,
        metric_mappings=metric_mappings,
        insight_mappings=insight_mappings,
        dashboard_mappings=dashboard_mappings,
        mapping_logger=mapping_logger,
        suppress_warnings=config.object_migration_config.suppress_migration_warnings,
        client_prefix=config.common_config.client_prefix,
        dashboard_type=config.dashboard_type,
        keep_original_ids=config.keep_original_ids,
    )

    logger.info("----Fetching Legacy dashboards----")
    legacy_dashboards = fetch_objects_with_filters(
        legacy_client, config.dashboard_type, filter_params, "dashboards"
    )

    # Filter objects based on mapping files if requested
    if config.object_filter_config.without_mapped_objects:
        legacy_dashboards = filter_objects_by_mapping_files(
            legacy_dashboards,
            config.object_filter_config.without_mapped_objects,
            dashboard_mappings,
            config.dashboard_mapping_file[0],
            "dashboards",
        )

    if config.object_migration_config.dump_legacy:
        write_content_to_file(
            LEGACY_DASHBOARDS_FILE, json.dumps(legacy_dashboards, indent=4)
        )
        logger.info(
            "Legacy dashboards dumped to '%s'",
            prefix_filename(LEGACY_DASHBOARDS_FILE),
        )

    # Fetch all dashboard content (widgets and filter contexts) to populate Legacy cache for fast processing
    logger.info("----Fetching Legacy dashboard content----")
    fetch_dashboard_content(legacy_client, legacy_dashboards)

    # Element lookup strategies: compute once, execute steps once in order
    # NOTE: Must happen AFTER fetch_dashboard_content to include widgets and filter contexts
    prefetch_required = (
        config.element_values_prefetch or config.validation_element_lookup_with_metrics
    )
    validation_required = (
        config.validation_element_lookup
        or config.validation_element_lookup_with_metrics
    )

    if prefetch_required:
        prefetcher = ElementPrefetcher(legacy_client)
        # Scan dashboards for element URIs
        prefetcher.collect_element_uris_from_objects(legacy_dashboards)
        # Also scan cached widgets and filter contexts
        cached_objects = list(legacy_client.cache.values())
        if cached_objects:
            prefetcher.collect_element_uris_from_objects(cached_objects)
        prefetcher.prefetch_and_cache()

    if config.validation_element_lookup_with_metrics:
        # Extend prefetch with temporary metrics to resolve unmapped elements
        prefetcher.create_metrics_for_unmapped_elements()
        validation_required = True

    if validation_required:
        legacy_client.initialize_attribute_elements_cache()

    if config.validation_element_lookup_with_metrics:
        prefetcher.delete_created_metrics()

    if config.object_migration_config.cleanup_target_env:
        cloud_client.remove_native_dashboards()
        cloud_client.remove_native_filter_contexts()
        cloud_client.remove_native_dashboard_specific_insights()

    logger.info("----Processing Legacy dashboards (%d)----", len(legacy_dashboards))
    # Empty the log file for failed KPI comparison insights first
    with open(CLOUD_FAILED_KPI_COMPARISON_INSIGHTS_FILE, "w"):
        pass
    dashboards_builder = CloudDashboardsBuilder(ctx)
    dashboards_builder.process_legacy_dashboards(
        legacy_dashboards,
        config.common_config.skip_deploy,
        config.object_migration_config.overwrite_existing,
    )

    cloud_dashboards = dashboards_builder.get_cloud_dashboards()
    cloud_public_dashboard_ids = dashboards_builder.get_public_dashboard_ids()

    if len(legacy_dashboards) > len(cloud_dashboards):
        logger.warning(
            "----%d (out of %d) dashboards cannot be migrated----",
            len(legacy_dashboards) - len(cloud_dashboards),
            len(legacy_dashboards),
        )

    if not config.common_config.skip_deploy:
        logger.info("----Two-phase dashboard migration (%d)----", len(cloud_dashboards))

        # Phase 1: Create placeholder dashboards to establish all IDs
        logger.info(
            "Phase 1: Creating placeholder dashboards (%d)...", len(cloud_dashboards)
        )
        if config.object_migration_config.overwrite_existing:
            operation = Operation.CREATE_OR_UPDATE_WITH_RETRY
        else:
            operation = Operation.CREATE_WITH_RETRY

        _failed_placeholders, skipped_placeholders = process_objects(
            cloud_client=cloud_client,
            objects=cloud_dashboards,
            object_type="placeholder_dashboard",
            operation=operation,
        )

        # Collect IDs of dashboards that were skipped in Phase 1
        skipped_dashboard_ids = {
            dashboard["data"]["id"] for dashboard in skipped_placeholders
        }

        # Phase 2: Update placeholders with full dashboard content including drills
        # Only update dashboards that were successfully created in Phase 1
        if len(cloud_dashboards) > len(skipped_placeholders):
            dashboards_to_update_count = len(cloud_dashboards) - len(
                skipped_placeholders
            )
            logger.info(
                "Phase 2: Updating dashboards with full content (%d)...",
                dashboards_to_update_count,
            )
            _failed_updates, _ = update_dashboards_with_full_content(
                cloud_client, cloud_dashboards, skipped_dashboard_ids
            )
        else:
            logger.info(
                "Phase 2: No dashboards to update (all were skipped in Phase 1)"
            )
            _failed_updates = []

        # Create dashboard permissions for public dashboards (only for successfully created ones)
        public_dashboards_to_set_permissions = [
            dashboard_id
            for dashboard_id in cloud_public_dashboard_ids
            if dashboard_id not in skipped_dashboard_ids
        ]
        if public_dashboards_to_set_permissions:
            cloud_client.create_dashboard_permissions_for_public_dashboards(
                public_dashboards_to_set_permissions
            )

    if config.object_migration_config.dump_cloud:
        write_content_to_file(
            CLOUD_DASHBOARDS_FILE, json.dumps(cloud_dashboards, indent=4)
        )
        logger.info(
            "Cloud dashboards dumped to '%s'",
            prefix_filename(CLOUD_DASHBOARDS_FILE),
        )

    execution_time = duration(start_time)
    legacy_client.logout()
    logger.info("----DONE in %.2fs----", execution_time)
    logger.info("----Executed %d Cloud requests----", cloud_client.request_count.get())


def migrate_dashboards_cli():
    args = parse_dashboard_cli_args()
    config = DashboardConfig.from_kwargs(**args.__dict__)
    migrate_dashboards(config)
