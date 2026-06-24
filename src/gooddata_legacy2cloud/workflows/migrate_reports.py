# (C) 2026 GoodData Corporation
"""
This module is used for migrating reports. It includes functionality for
loading environment variables, setting up command line arguments, and running
the main migration process.
"""

import json
import logging
from time import time

from gooddata_legacy2cloud.arg_parsing.arg_parser import parse_report_cli_args
from gooddata_legacy2cloud.backends.cloud.client import CloudClient
from gooddata_legacy2cloud.backends.cloud.object_creator import process_objects
from gooddata_legacy2cloud.backends.legacy.client import LegacyClient
from gooddata_legacy2cloud.backends.legacy.filters import FilterParameters
from gooddata_legacy2cloud.backends.legacy.objects import fetch_reports_with_filters
from gooddata_legacy2cloud.config.configuration_objects import ReportConfig
from gooddata_legacy2cloud.config.env_vars import EnvVars
from gooddata_legacy2cloud.helpers import (
    duration,
    prefix_filename,
    set_output_files_prefix,
    write_content_to_file,
)
from gooddata_legacy2cloud.id_mappings import IdMappings
from gooddata_legacy2cloud.logging.config import configure_logger
from gooddata_legacy2cloud.mapping.mapping_utils import (
    filter_objects_by_mapping_files,
    format_mapping_files_info,
    get_mapping_files,
)
from gooddata_legacy2cloud.metrics.element_prefetcher import ElementPrefetcher
from gooddata_legacy2cloud.models.enums import Operation
from gooddata_legacy2cloud.output_writer import OutputWriter
from gooddata_legacy2cloud.reports.cloud_reports_builder import CloudReportsBuilder
from gooddata_legacy2cloud.reports.data_classes import ReportContext
from gooddata_legacy2cloud.reports.transformation import set_report_title_prefix

LEGACY_REPORTS_FILE = "legacy_reports.json"
CLOUD_REPORTS_FILE = "cloud_reports.json"

logger = logging.getLogger("migration")
configure_logger()


def migrate_reports(config: ReportConfig):
    """The report migration process."""
    start_time = time()

    env_vars = EnvVars(config.env)
    env_vars.resolve_workspaces(config.workspace_config)
    env_vars.log_connection_info()

    # Set output files prefix from command line arguments or client prefix
    if config.common_config.client_prefix:
        set_output_files_prefix(config.common_config.client_prefix)
    else:
        set_output_files_prefix(config.common_config.output_files_prefix)

    # Set report title prefix if specified
    if config.report_prefix is not None:
        set_report_title_prefix(config.report_prefix)

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

    report_files, report_status = get_mapping_files(
        files=config.report_mapping_file,
        client_prefix=config.common_config.client_prefix,
    )

    # Log information about which files are being used with their status
    logger.info("Mapping files:")
    logger.info("  LDM mappings: %s", format_mapping_files_info(ldm_files, ldm_status))
    logger.info(
        "  Metric mappings: %s", format_mapping_files_info(metric_files, metric_status)
    )
    logger.info(
        "  Report mappings: %s", format_mapping_files_info(report_files, report_status)
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
    report_mappings = IdMappings(report_files)

    # First file is used for writing mappings
    primary_report_file = (
        report_files[0] if report_files else config.report_mapping_file
    )
    mapping_logger = OutputWriter(primary_report_file)

    ctx = ReportContext(
        legacy_client=legacy_client,
        cloud_client=cloud_client,
        ldm_mappings=ldm_mappings,
        metric_mappings=metric_mappings,
        mapping_logger=mapping_logger,
        suppress_warnings=config.object_migration_config.suppress_migration_warnings,
        client_prefix=config.common_config.client_prefix,
        keep_original_ids=config.keep_original_ids,
    )

    logger.info("----Fetching Legacy reports----")
    # Use the specialized function for reports that handles extracting the last report definition
    legacy_reports = fetch_reports_with_filters(legacy_client, filter_params, "reports")

    # Filter objects based on mapping files if requested
    if config.object_filter_config.without_mapped_objects:
        legacy_reports = filter_objects_by_mapping_files(
            legacy_reports,
            config.object_filter_config.without_mapped_objects,
            report_mappings,
            config.report_mapping_file[0],
            "reports",
        )

    # Element lookup: prefetch optimization, then validation if needed
    if config.element_values_prefetch:
        prefetcher = ElementPrefetcher(legacy_client)
        prefetcher.collect_element_uris_from_objects(legacy_reports)
        prefetcher.prefetch_and_cache()

    if config.validation_element_lookup:
        legacy_client.initialize_attribute_elements_cache()

    if config.object_migration_config.dump_legacy:
        write_content_to_file(LEGACY_REPORTS_FILE, json.dumps(legacy_reports, indent=4))
        logger.info(
            "Legacy reports dumped to '%s'", prefix_filename(LEGACY_REPORTS_FILE)
        )

    logger.info("----Processing Legacy reports (%d)----", len(legacy_reports))
    reports_builder = CloudReportsBuilder(ctx)

    # Process the reports
    reports_builder.process_legacy_reports(legacy_reports)

    if config.object_migration_config.cleanup_target_env:
        cloud_client.remove_native_report_insights()

    cloud_reports = reports_builder.get_cloud_reports()

    if len(legacy_reports) > len(cloud_reports):
        logger.error(
            "----%d (out of %d) reports cannot be migrated----",
            len(legacy_reports) - len(cloud_reports),
            len(legacy_reports),
        )

    if not config.common_config.skip_deploy:
        logger.info("----Pushing new Cloud reports (%d)----", len(cloud_reports))
        if config.object_migration_config.overwrite_existing:
            operation = Operation.CREATE_OR_UPDATE_WITH_RETRY
        else:
            operation = Operation.CREATE_WITH_RETRY

        process_objects(
            cloud_client=cloud_client,
            objects=cloud_reports,
            object_type="report",
            operation=operation,
        )

    if config.object_migration_config.dump_cloud:
        write_content_to_file(CLOUD_REPORTS_FILE, json.dumps(cloud_reports, indent=4))
        logger.info("Cloud reports dumped to '%s'", prefix_filename(CLOUD_REPORTS_FILE))

    execution_time = duration(start_time)
    legacy_client.logout()
    logger.info("----DONE in %.2fs----", execution_time)
    logger.info("----Executed %d Cloud requests----", cloud_client.request_count.get())


def migrate_reports_cli():
    args = parse_report_cli_args()
    config = ReportConfig.from_kwargs(**args.__dict__)
    migrate_reports(config)
