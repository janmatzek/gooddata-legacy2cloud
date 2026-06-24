# (C) 2026 GoodData Corporation
"""
This module is used for migrating insights. It includes functionality for
loading environment variables, setting up command line arguments, and running
the main migration process.
"""

import json
import logging
from time import time

from gooddata_legacy2cloud.arg_parsing.arg_parser import parse_insight_cli_args
from gooddata_legacy2cloud.backends.cloud.client import CloudClient
from gooddata_legacy2cloud.backends.cloud.object_creator import process_objects
from gooddata_legacy2cloud.backends.legacy.client import LegacyClient
from gooddata_legacy2cloud.backends.legacy.filters import FilterParameters
from gooddata_legacy2cloud.backends.legacy.objects import fetch_objects_with_filters
from gooddata_legacy2cloud.config.configuration_objects import InsightConfig
from gooddata_legacy2cloud.config.env_vars import EnvVars
from gooddata_legacy2cloud.helpers import (
    duration,
    prefix_filename,
    set_output_files_prefix,
    write_content_to_file,
)
from gooddata_legacy2cloud.id_mappings import IdMappings
from gooddata_legacy2cloud.insights.cloud_insights_builder import CloudInsightsBuilder
from gooddata_legacy2cloud.insights.data_classes import InsightContext
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

LEGACY_INSIGHTS_FILE = "legacy_insights.json"
CLOUD_INSIGHTS_FILE = "cloud_insights.json"

logger = logging.getLogger("migration")
configure_logger()


def migrate_insights(config: InsightConfig):
    """The insight migration process."""
    start_time = time()

    env_vars = EnvVars(config.env)
    env_vars.resolve_workspaces(config.workspace_config)
    env_vars.log_connection_info()

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

    # First file is used for writing mappings
    primary_insight_file = (
        insight_files[0] if insight_files else config.insight_mapping_file
    )
    mapping_logger = OutputWriter(primary_insight_file)

    ctx = InsightContext(
        legacy_client=legacy_client,
        cloud_client=cloud_client,
        ldm_mappings=ldm_mappings,
        metric_mappings=metric_mappings,
        mapping_logger=mapping_logger,
        suppress_warnings=config.object_migration_config.suppress_migration_warnings,
        client_prefix=config.common_config.client_prefix,
        keep_original_ids=config.keep_original_ids,
    )

    logger.info("----Fetching Legacy insights----")
    legacy_insights = fetch_objects_with_filters(
        legacy_client, "visualizationObject", filter_params, "insights"
    )

    # Filter objects based on mapping files if requested
    if config.object_filter_config.without_mapped_objects:
        legacy_insights = filter_objects_by_mapping_files(
            legacy_insights,
            config.object_filter_config.without_mapped_objects,
            insight_mappings,
            config.insight_mapping_file[0],
            "insights",
        )

    # Element lookup strategies: compute once, execute steps once in order
    prefetch_required = (
        config.element_values_prefetch or config.validation_element_lookup_with_metrics
    )
    validation_required = (
        config.validation_element_lookup
        or config.validation_element_lookup_with_metrics
    )

    if prefetch_required:
        prefetcher = ElementPrefetcher(legacy_client)
        prefetcher.collect_element_uris_from_objects(legacy_insights)
        prefetcher.prefetch_and_cache()

    if config.validation_element_lookup_with_metrics:
        # Extend prefetch with temporary metrics to resolve unmapped elements
        prefetcher.create_metrics_for_unmapped_elements()
        validation_required = True

    if validation_required:
        legacy_client.initialize_attribute_elements_cache()

    if config.validation_element_lookup_with_metrics:
        prefetcher.delete_created_metrics()

    if config.object_migration_config.dump_legacy:
        write_content_to_file(
            LEGACY_INSIGHTS_FILE, json.dumps(legacy_insights, indent=4)
        )
        logger.info(
            "Legacy insights dumped to '%s'", prefix_filename(LEGACY_INSIGHTS_FILE)
        )

    logger.info("----Processing Legacy insights (%d)----", len(legacy_insights))
    insights_builder = CloudInsightsBuilder(ctx)
    insights_builder.process_legacy_insights(legacy_insights)

    if config.object_migration_config.cleanup_target_env:
        cloud_client.remove_native_insights()

    cloud_insights = insights_builder.get_cloud_insights()

    if len(legacy_insights) > len(cloud_insights):
        logger.error(
            "----%d (out of %d) insights cannot be migrated----",
            len(legacy_insights) - len(cloud_insights),
            len(legacy_insights),
        )

    if not config.common_config.skip_deploy:
        logger.info("----Pushing new Cloud insights (%d)----", len(cloud_insights))
        if config.object_migration_config.overwrite_existing:
            operation = Operation.CREATE_OR_UPDATE_WITH_RETRY
        else:
            operation = Operation.CREATE_WITH_RETRY

        process_objects(
            cloud_client=cloud_client,
            objects=cloud_insights,
            object_type="insight",
            operation=operation,
        )

    if config.object_migration_config.dump_cloud:
        write_content_to_file(CLOUD_INSIGHTS_FILE, json.dumps(cloud_insights, indent=4))
        logger.info(
            "Cloud insights dumped to '%s'", prefix_filename(CLOUD_INSIGHTS_FILE)
        )

    execution_time = duration(start_time)
    legacy_client.logout()
    logger.info("----DONE in %.2fs----", execution_time)
    logger.info("----Executed %d Cloud requests----", cloud_client.request_count.get())


def migrate_insights_cli():
    args = parse_insight_cli_args()
    config = InsightConfig.from_kwargs(**args.__dict__)
    migrate_insights(config)
