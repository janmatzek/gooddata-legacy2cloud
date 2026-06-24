# (C) 2026 GoodData Corporation
"""
This module is used for migrating metrics. It includes functionality for
loading environment variables, setting up command line arguments, and running
the main migration process.
"""

import json
import logging
from time import time

from gooddata_legacy2cloud.arg_parsing.arg_parser import parse_metric_cli_args
from gooddata_legacy2cloud.backends.cloud.client import CloudClient
from gooddata_legacy2cloud.backends.cloud.object_creator import process_objects
from gooddata_legacy2cloud.backends.legacy.client import LegacyClient
from gooddata_legacy2cloud.backends.legacy.filters import FilterParameters
from gooddata_legacy2cloud.backends.legacy.objects import fetch_objects_with_filters
from gooddata_legacy2cloud.config.configuration_objects import MetricConfig
from gooddata_legacy2cloud.config.env_vars import EnvVars
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
from gooddata_legacy2cloud.metrics.cloud_metrics_builder import CloudMetricsBuilder
from gooddata_legacy2cloud.metrics.data_classes import MetricContext
from gooddata_legacy2cloud.metrics.element_prefetcher import ElementPrefetcher
from gooddata_legacy2cloud.models.enums import Operation
from gooddata_legacy2cloud.output_writer import OutputWriter

LEGACY_METRICS_FILE = "legacy_metrics.json"
CLOUD_METRICS_FILE = "cloud_metrics.json"

logger = logging.getLogger("migration")
configure_logger()


def migrate_metrics(config: MetricConfig):
    """The metric migration process."""
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

    # Log information about which files are being used
    logger.info("Mapping files:")
    logger.info("  LDM mappings: %s", format_mapping_files_info(ldm_files, ldm_status))
    logger.info(
        "  Metric mappings: %s", format_mapping_files_info(metric_files, metric_status)
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

    # First file is used for writing mappings
    primary_metric_file = (
        metric_files[0] if metric_files else config.metric_mapping_file
    )
    mapping_logger = OutputWriter(primary_metric_file)

    logger.info("----Fetching Legacy metrics----")
    legacy_metrics = fetch_objects_with_filters(
        legacy_client, "metric", filter_params, "metrics"
    )

    # Filter objects based on mapping files if requested
    if config.object_filter_config.without_mapped_objects:
        legacy_metrics = filter_objects_by_mapping_files(
            legacy_metrics,
            config.object_filter_config.without_mapped_objects,
            metric_mappings,
            config.metric_mapping_file[0],
            "metrics",
        )

    # Element lookup: prefetch optimization, then validation if needed
    if config.element_values_prefetch:
        prefetcher = ElementPrefetcher(legacy_client)
        prefetcher.collect_element_uris_from_objects(legacy_metrics)
        prefetcher.prefetch_and_cache()

    if config.validation_element_lookup:
        legacy_client.initialize_attribute_elements_cache()

    if config.object_migration_config.dump_legacy:
        write_content_to_file(LEGACY_METRICS_FILE, json.dumps(legacy_metrics, indent=4))
        logger.info(
            "Legacy metrics dumped to '%s'", prefix_filename(LEGACY_METRICS_FILE)
        )

    logger.info("----Processing Legacy metrics (%d)----", len(legacy_metrics))
    ctx = MetricContext(
        legacy_client=legacy_client,
        cloud_client=cloud_client,
        ldm_mappings=ldm_mappings,
        mapping_logger=mapping_logger,
        keep_original_ids=config.keep_original_ids,
        ignore_folders=config.ignore_folders,
        suppress_warnings=config.object_migration_config.suppress_migration_warnings,
        client_prefix=config.common_config.client_prefix,
    )
    metrics_builder = CloudMetricsBuilder(ctx)
    metrics_builder.process_legacy_metrics(legacy_metrics)

    if config.object_migration_config.cleanup_target_env:
        cloud_client.remove_native_metrics()

    cloud_metrics = metrics_builder.get_cloud_metrics()

    if len(legacy_metrics) > len(cloud_metrics):
        logger.error(
            "----%d (out of %d) metrics cannot be migrated----",
            len(legacy_metrics) - len(cloud_metrics),
            len(legacy_metrics),
        )

    if config.object_migration_config.dump_cloud:
        write_content_to_file(CLOUD_METRICS_FILE, json.dumps(cloud_metrics, indent=4))
        logger.info("Cloud metrics dumped to '%s'", prefix_filename(CLOUD_METRICS_FILE))

    if not config.common_config.skip_deploy:
        if config.object_migration_config.overwrite_existing:
            operation = Operation.CREATE_OR_UPDATE_WITH_ERROR_FALLBACK
        else:
            operation = Operation.CREATE_WITH_ERROR_FALLBACK

        process_objects(
            cloud_client,
            cloud_metrics,
            "metric",
            operation,
        )

    execution_time = duration(start_time)
    legacy_client.logout()
    logger.info("----DONE in %.2fs----", execution_time)
    logger.info("----Executed %d Cloud requests----", cloud_client.request_count.get())


def migrate_metrics_cli():
    args = parse_metric_cli_args()
    config = MetricConfig.from_kwargs(**args.__dict__)
    migrate_metrics(config)
