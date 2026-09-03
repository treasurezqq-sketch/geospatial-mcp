"""
Unit tests for FastMCP server endpoints and tool registrations:
- Tool registration verification
- Input format tolerance (string, dict, Feature, Markdown code block)
- Parameter alias support (unit vs target_unit)
- Friendly JSON error handling without crashes
"""

import json
import pytest
from geospatial_mcp.server import (
    mcp,
    validate_and_repair_geometry,
    calculate_accurate_metrics,
    check_spatial_relationship,
    generate_buffer,
)


class TestServerToolRegistrations:
    """Verify tool discovery on the FastMCP instance."""

    def test_registered_tool_names(self):
        """Check all 4 standard tools are registered on the FastMCP server."""
        import asyncio
        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert "validate_and_repair_geometry" in tool_names
        assert "calculate_accurate_metrics" in tool_names
        assert "check_spatial_relationship" in tool_names
        assert "generate_buffer" in tool_names


class TestServerInputTolerance:
    """Verify tool tolerance to different input formats."""

    def test_string_and_dict_and_feature_input(self):
        """Test validate_and_repair_geometry accepts dict, json str, and Feature."""
        dict_geom = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        }
        str_geom = json.dumps(dict_geom)
        feature_geom = {
            "type": "Feature",
            "properties": {"name": "Test Parcel"},
            "geometry": dict_geom,
        }
        markdown_str = f"```json\n{str_geom}\n```"

        # Dict
        res1 = validate_and_repair_geometry(dict_geom)
        assert res1.is_valid is True
        assert res1["is_valid"] is True

        # String
        res2 = validate_and_repair_geometry(str_geom)
        assert res2.is_valid is True
        assert res2["is_valid"] is True

        # Feature
        res3 = validate_and_repair_geometry(feature_geom)
        assert res3.is_valid is True
        assert res3["is_valid"] is True

        # Markdown
        res4 = validate_and_repair_geometry(markdown_str)
        assert res4.is_valid is True
        assert res4["is_valid"] is True


class TestParameterAliasCompatibility:
    """Verify dual-key alias support for unit and target_unit."""

    def test_unit_and_target_unit_alias(self):
        """Verify calling with unit or target_unit yields identical valid output."""
        poly = {
            "type": "Polygon",
            "coordinates": [[[120.0, 30.0], [120.1, 30.0], [120.1, 30.1], [120.0, 30.1], [120.0, 30.0]]],
        }
        res_by_unit = calculate_accurate_metrics(poly, unit="hectares")
        res_by_alias = calculate_accurate_metrics(poly, target_unit="hectares")

        assert res_by_unit.unit == "hectares"
        assert res_by_alias.unit == "hectares"
        assert res_by_unit.area == res_by_alias.area
        assert res_by_unit.projected_epsg == res_by_alias.projected_epsg
        assert res_by_unit["projected_epsg"] == 32650 or res_by_unit["projected_epsg"] == 32651


class TestServerFaultTolerance:
    """Verify friendly JSON error responses on invalid/malformed inputs."""

    def test_malformed_geojson_validation(self):
        """Malformed GeoJSON returns is_valid=False with error message, no crash."""
        res = validate_and_repair_geometry("{bad_json: 123}")
        assert res.is_valid is False
        assert res.error_reason is not None
        assert res.repaired_geojson is None

    def test_malformed_geojson_metrics(self):
        """Malformed GeoJSON to calculate_metrics returns zeroed metrics with error, no crash."""
        res = calculate_accurate_metrics("{bad_json: 123}")
        assert res.error is not None
        assert res.area == 0.0

    def test_malformed_geojson_relationships(self):
        """Malformed GeoJSON to check_spatial_relationship returns result=False with error, no crash."""
        res = check_spatial_relationship("{bad_json: 123}", "POINT (0 0)")
        assert res.result is False
        assert res.error is not None

    def test_malformed_geojson_buffer(self):
        """Malformed GeoJSON to generate_buffer returns None with error, no crash."""
        res = generate_buffer("{bad_json: 123}", distance_meters=50.0)
        assert res.buffered_geojson is None
        assert res.error is not None
