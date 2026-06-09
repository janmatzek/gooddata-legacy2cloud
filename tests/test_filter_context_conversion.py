# (C) 2026 GoodData Corporation
from unittest.mock import MagicMock

from gooddata_legacy2cloud.dashboards.filter_context import FilterContext


def test_get_filter_elements_by_wraps_attributes_as_identifier_refs():
    ctx = MagicMock()
    ctx.legacy_client.get_object.return_value = {
        "attribute": {
            "meta": {"identifier": "attr.region.regionid", "category": "attribute"},
            "content": {"displayForms": ["mock", "values"]},
        }
    }
    ctx.ldm_mappings.search_mapping_identifier.return_value = "region.regionid"

    fc = FilterContext(ctx, "/gdc/md/project/obj/5002")
    filter_dict = {
        "attributeFilter": {
            "filterElementsBy": [
                {
                    "filterLocalIdentifier": "filter_region",
                    "over": {"attributes": ["/gdc/md/project/obj/5011"]},
                }
            ]
        }
    }

    result = fc._get_filter_elements_by(filter_dict)

    assert result == [
        {
            "filterLocalIdentifier": "filter_region",
            "over": {
                "attributes": [
                    {"identifier": {"id": "region.regionid", "type": "label"}}
                ]
            },
        }
    ]
