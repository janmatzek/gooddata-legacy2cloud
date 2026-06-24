# (C) 2026 GoodData Corporation
"""
This module contains utilities for working with mapping files.
"""

import csv
import logging
import os

from typing import Literal

from gooddata_legacy2cloud.id_mappings import IdMappings

logger = logging.getLogger("migration")


# TODO: return single object instead of a tuple
def get_mapping_files(
    files: list[str], client_prefix: str | None = None
) -> tuple[list[str], dict[str, bool]]:
    """
    Determines which mapping files to use based on the parameters.

    Returns:
        A tuple containing:
        - A list of mapping files to use, with duplicates removed.
        - A dictionary with file status (True if file exists, False if missing)
    """

    # First file is the primary one (for writing)
    primary_file = files[0]
    files_to_use = files[:]
    file_status = {file: os.path.exists(file) for file in files_to_use}

    # Add client-prefixed file if client_prefix is specified
    if client_prefix:
        if len(files) == 1:
            prefixed_file = f"{client_prefix}{primary_file}"
            if os.path.exists(prefixed_file):
                files_to_use.append(prefixed_file)
                file_status[prefixed_file] = True
            else:
                # Still include the file in the status dictionary, but mark as missing
                files_to_use.append(prefixed_file)
                file_status[prefixed_file] = False

    return files_to_use, file_status


def format_mapping_files_info(files: list[str], file_status: dict[str, bool]) -> str:
    """
    Formats the mapping files information for display.

    Args:
        files: List of mapping files
        file_status: Dictionary with file status (True if exists, False if missing)

    Returns:
        A formatted string with the files and their status
    """
    result = []
    for file in files:
        status = "(loaded)" if file_status[file] else "(MISSING)"
        result.append(f"{file} {status}")

    return ", ".join(result)


def filter_objects_by_mapping_files(
    objects: list,
    filter_mode: Literal["default_only", "all"],
    id_mappings: IdMappings,
    default_mapping_file: str,
    object_type: Literal[
        "metrics", "insights", "dashboards", "reports", "pixel perfect dashboards"
    ],
):
    """
    Filters objects based on their presence in mapping files.

    Args:
        objects: List of objects to filter
        filter_mode: 'default_only' to check only default mapping file, 'all' to check all mapping files
        id_mappings: IdMappings instance with loaded mapping files
        default_mapping_file: Path to the default mapping file (or comma-separated list, first file is used)
        object_type: Type of objects being filtered (for logging)

    Returns:
        Filtered list of objects
    """
    if filter_mode is None:
        return objects

    # Get Legacy IDs from the appropriate mapping files
    legacy_ids = set()

    if filter_mode == "default_only":
        # Only check default mapping file (first file if comma-separated)
        primary_file = default_mapping_file.split(",")[0].strip()
        if os.path.exists(primary_file):
            try:
                with open(primary_file, "r") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row and len(row) >= 1:
                            legacy_ids.add(row[0])
                logger.info(
                    "Filtering %s based on default mapping file: %s",
                    object_type,
                    primary_file,
                )
                logger.info(
                    "Found %d %s Legacy identifiers in the default mapping file",
                    len(legacy_ids),
                    object_type,
                )
            except Exception as e:
                logger.warning(
                    "Error reading default mapping file '%s': %s",
                    primary_file,
                    e,
                )
        else:
            logger.warning(
                "Default mapping file '%s' does not exist. No filtering by mapping will be applied.",
                primary_file,
            )
            return objects
    else:  # 'all'
        # Check all loaded mapping files
        loaded_files = id_mappings.get_loaded_files()
        if loaded_files:
            legacy_ids = set(id_mappings.get().keys())
            logger.info(
                "Filtering %s based on all loaded mapping files: %s",
                object_type,
                ", ".join(loaded_files),
            )
            logger.info(
                "Found %d %s Legacy identifiers in the mapping files",
                len(legacy_ids),
                object_type,
            )
        else:
            logger.warning(
                "No mapping files were successfully loaded. No filtering by mapping will be applied."
            )
            return objects

    # Filter objects that are not in the mapping files
    original_count = len(objects)

    # Extract identifier based on object type
    filtered_objects = []
    for obj in objects:
        # Different object types have identifiers in different places
        identifier = None

        if object_type == "metrics":
            # Metrics structure: obj["metric"]["meta"]["identifier"]
            if (
                "metric" in obj
                and "meta" in obj["metric"]
                and "identifier" in obj["metric"]["meta"]
            ):
                identifier = obj["metric"]["meta"]["identifier"]
        elif object_type == "insights":
            # Insights structure: obj["visualizationObject"]["meta"]["identifier"]
            if (
                "visualizationObject" in obj
                and "meta" in obj["visualizationObject"]
                and "identifier" in obj["visualizationObject"]["meta"]
            ):
                identifier = obj["visualizationObject"]["meta"]["identifier"]
        elif object_type == "dashboards":
            # Dashboards structure: obj["analyticalDashboard"]["meta"]["identifier"]
            if (
                "analyticalDashboard" in obj
                and "meta" in obj["analyticalDashboard"]
                and "identifier" in obj["analyticalDashboard"]["meta"]
            ):
                identifier = obj["analyticalDashboard"]["meta"]["identifier"]
        elif object_type == "pixel perfect dashboards":
            # Pixel Perfect Dashboards structure: obj["projectDashboard"]["meta"]["identifier"]
            if (
                "projectDashboard" in obj
                and "meta" in obj["projectDashboard"]
                and "identifier" in obj["projectDashboard"]["meta"]
            ):
                identifier = obj["projectDashboard"]["meta"]["identifier"]
        elif object_type == "reports":
            # Reports structure: obj["report"]["meta"]["identifier"]
            if (
                "report" in obj
                and "meta" in obj["report"]
                and "identifier" in obj["report"]["meta"]
            ):
                identifier = obj["report"]["meta"]["identifier"]
            elif (
                "reportDefinition" in obj
                and "meta" in obj["reportDefinition"]
                and "identifier" in obj["reportDefinition"]["meta"]
            ):
                identifier = obj["reportDefinition"]["meta"]["identifier"]

        # Include only if identifier is not in the mapping files
        if identifier is not None and identifier not in legacy_ids:
            filtered_objects.append(obj)

    filtered_count = len(filtered_objects)

    logger.info(
        "Filtered out %d %s. Keeping %d unmapped %s for processing.",
        original_count - filtered_count,
        object_type,
        filtered_count,
        object_type,
    )

    return filtered_objects
