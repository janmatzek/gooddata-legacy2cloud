# (C) 2026 GoodData Corporation
import logging

from gooddata_legacy2cloud.dashboards.data_classes import DashboardContext
from gooddata_legacy2cloud.helpers import get_cloud_id
from gooddata_legacy2cloud.metrics.attribute_element import AttributeElement
from gooddata_legacy2cloud.metrics.contants import DELETED_VALUE
from gooddata_legacy2cloud.models.cloud.filter_context import (
    FilterContextModel,
    FilterContextWrapper,
)

logger = logging.getLogger("migration")

# TODO: refactor FilterContext class to reuse the pydantic mode.
#   - [ ] Phase 1: class typed internally, get() dumps before return
#   - [ ] Phase 2: get() returns typed object, consumers handle it


class FilterContext:
    def __init__(self, ctx: DashboardContext, filter_context_uri: str):
        self.ctx = ctx
        self.filter_context_uri = filter_context_uri
        self.cloud_filters = []
        self.attribute_filter_configs = []
        self.missing_filter_values = {}

    @staticmethod
    def _transform_filter_type_value(obj: dict) -> str:
        filter_type = obj["attributeDisplayForm"]["meta"]["category"].lower()
        filter_type = "label" if filter_type == "attributedisplayform" else filter_type
        return filter_type

    @staticmethod
    def _transform_attribute_type_value(obj: dict) -> str:
        attr_type = obj["attribute"]["meta"]["category"].lower()
        return "label" if attr_type == "attribute" else attr_type

    def _get_filter_attribute_elements(
        self, attribute_elements: list
    ) -> tuple[list, list]:
        missing_values = []
        new_attribute_elements = []
        old_and_new_attribute_elements = [
            (filter_in, AttributeElement(self.ctx, filter_in).get())
            for filter_in in attribute_elements
        ]
        for original, new in old_and_new_attribute_elements:
            if new in ["--MISSING VALUE--", ""]:
                missing_values.append(original)
            elif new == DELETED_VALUE:
                missing_values.append(original)
            else:
                new_attribute_elements.append(new)

        return new_attribute_elements, missing_values

    def _get_filter_elements_by(self, filter: dict) -> list:
        new_filter_elements = []
        for item in filter["attributeFilter"]["filterElementsBy"]:
            new_attrs = []
            for attr in item["over"]["attributes"]:
                obj = self.ctx.legacy_client.get_object(attr)
                new_attr = self.ctx.ldm_mappings.search_mapping_identifier(
                    obj["attribute"]["meta"]["identifier"]
                )
                # NOTE: This is a workaround for a feature gap. There are Legacy cases of linked filters using references
                # to record counts in a dataset. I distinguish them from regular linked filters by length of displayForms
                # metadata. This filter setting cannot be migrated to cloud, so we drop it.
                if (
                    len(obj["attribute"].get("content", {}).get("displayForms", []))
                    == 0
                ):
                    logger.warning(
                        "Attribute display form is empty for `%s`. Skipping.", new_attr
                    )
                else:
                    new_attrs.append(
                        {
                            "identifier": {
                                "id": new_attr,
                                "type": self._transform_attribute_type_value(obj),
                            }
                        }
                    )
            if new_attrs:
                new_filter_elements.append(
                    {
                        "filterLocalIdentifier": item["filterLocalIdentifier"],
                        "over": {"attributes": new_attrs},
                    }
                )
        return new_filter_elements

    def _get_filters(self, filters: list) -> tuple[list, dict]:
        new_filters = []
        missing_filter_values = {}
        date_filter_count = 0
        for idx, filter in enumerate(filters):
            if "dateFilter" in filter:
                filter["dateFilter"]["localIdentifier"] = (
                    f"{date_filter_count}_dateFilter"
                )
                date_filter_count += 1
                if filter["dateFilter"]["type"] == "absolute":
                    if "from" in filter["dateFilter"] and "to" in filter["dateFilter"]:
                        filter["dateFilter"]["from"] = (
                            f"{filter['dateFilter']['from']} 00:00"
                        )
                        filter["dateFilter"]["to"] = (
                            f"{filter['dateFilter']['to']} 23:59"
                        )
                    else:
                        # NOTE: This can occur if the date filter is default (all
                        # time) and attribute filters have values selected. Legacy
                        # backend will then create the absolute date filter in the
                        # metadata, but it will not have from and to attributes.
                        pass
                new_filters.append(filter)
            elif "attributeFilter" in filter:
                obj = self.ctx.legacy_client.get_object(
                    filter["attributeFilter"]["displayForm"]
                )
                original_attribute_obj = self.ctx.legacy_client.get_object(
                    obj["attributeDisplayForm"]["content"]["formOf"]
                )
                original_attribute_id = self.ctx.ldm_mappings.search_mapping_identifier(
                    original_attribute_obj["attribute"]["meta"]["identifier"]
                )
                display_form = {
                    "identifier": {
                        "id": original_attribute_id,
                        "type": self._transform_filter_type_value(obj),
                    }
                }

                new_attributes, missing_values = self._get_filter_attribute_elements(
                    filter["attributeFilter"]["attributeElements"]
                )
                new_filter = {
                    "attributeFilter": {
                        "localIdentifier": filter["attributeFilter"]["localIdentifier"],
                        "attributeElements": {"values": new_attributes},
                        "displayForm": display_form,
                        "negativeSelection": filter["attributeFilter"][
                            "negativeSelection"
                        ],
                        "selectionMode": filter["attributeFilter"].get(
                            "selectionMode", "multi"
                        ),
                    }
                }
                if "title" in filter["attributeFilter"]:
                    new_filter["attributeFilter"]["title"] = filter["attributeFilter"][
                        "title"
                    ]

                if filter["attributeFilter"].get("filterElementsBy"):
                    new_filter["attributeFilter"]["filterElementsBy"] = (
                        self._get_filter_elements_by(filter)
                    )
                if missing_values:
                    key = f"filter context - {new_filter['attributeFilter']['displayForm']['identifier']['id']}"
                    missing_filter_values[key] = missing_values
                new_filters.append(new_filter)

                attribute_filter_label_id = (
                    self.ctx.ldm_mappings.search_mapping_identifier(
                        obj["attributeDisplayForm"]["meta"]["identifier"]
                    )
                )
                if attribute_filter_label_id != original_attribute_id:
                    new_attribute_filter_config = {
                        "localIdentifier": filter["attributeFilter"]["localIdentifier"],
                        "displayAsLabel": {
                            "identifier": {
                                "id": attribute_filter_label_id,
                                "type": "label",
                            }
                        },
                    }
                    self.attribute_filter_configs.append(new_attribute_filter_config)
        return new_filters, missing_filter_values

    def get_missing_filter_values(self) -> dict:
        return self.missing_filter_values

    def get(self) -> tuple[dict, dict] | dict:
        if not self.filter_context_uri:
            return {}
        obj = self.ctx.legacy_client.get_object(self.filter_context_uri)
        self.cloud_filters, self.missing_filter_values = self._get_filters(
            obj["filterContext"]["content"]["filters"]
        )
        new_filter_context_id = get_cloud_id(
            obj["filterContext"]["meta"]["title"],
            obj["filterContext"]["meta"]["identifier"],
        )
        new_filter_context = {
            "data": {
                "id": new_filter_context_id,
                "type": "filterContext",
                "attributes": {
                    "title": "filterContext",
                    "description": "",
                    "content": {"filters": self.cloud_filters, "version": "2"},
                },
            }
        }
        return {
            "identifier": {"id": new_filter_context_id, "type": "filterContext"}
        }, new_filter_context

    def get_object(self) -> FilterContextModel:
        _, raw_filter_context = self.get()
        wrapper: FilterContextWrapper = FilterContextWrapper(**raw_filter_context)
        return wrapper.data
