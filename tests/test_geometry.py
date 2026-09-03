"""
Unit tests for core geometry operations:
- Topology validation and bowtie polygon auto-repair
- Dynamic UTM projection and area calculations (equator crossing, multi-longitude)
- Deformed / unclosed GeoJSON exception capture and friendly responses
- Spatial relationship predicates (contains, within, intersects, disjoint)
- Metric buffer generation
"""

import math
import pytest
import shapely
from shapely.geometry import shape

from geospatial_mcp.core.projection import get_utm_epsg
from geospatial_mcp.core.geometry import (
    validate_and_repair,
    calculate_metrics,
    check_relationship,
    generate_buffer,
)


class TestGeometryValidationAndRepair:
    """Tests for validate_and_repair."""

    def test_valid_polygon(self):
        """Test a clean, valid square polygon."""
        clean_geojson = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        }
        res = validate_and_repair(clean_geojson)
        assert res.is_valid is True
        assert res.error_reason is None
        assert res.repaired_geojson is not None
        assert res.repaired_geojson["type"] == "Polygon"

    def test_bowtie_polygon_repair(self):
        """Test auto-repair of a self-intersecting bowtie polygon."""
        bowtie_geojson = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]],
        }
        res = validate_and_repair(bowtie_geojson)
        assert res.is_valid is False
        assert res.error_reason is not None
        assert "Self-intersection" in res.error_reason
        assert res.repaired_geojson is not None
        
        # Verify repaired geometry is valid and has expected MultiPolygon structure
        repaired_geom = shape(res.repaired_geojson)
        assert shapely.is_valid(repaired_geom)
        assert repaired_geom.area > 0

    def test_unclosed_linear_ring_detection_and_repair(self):
        """Test that unclosed polygon rings are flagged as invalid and repaired."""
        unclosed_geojson = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0]]],  # Missing closing [0, 0]
        }
        res = validate_and_repair(unclosed_geojson)
        assert res.is_valid is False
        assert "closed linestring" in (res.error_reason or "").lower()
        assert res.repaired_geojson is not None
        repaired_geom = shape(res.repaired_geojson)
        assert shapely.is_valid(repaired_geom)
        assert repaired_geom.exterior.is_closed
        assert repaired_geom.exterior.coords[0] == repaired_geom.exterior.coords[-1]

    def test_malformed_json_graceful_handling(self):
        """Test that malformed JSON strings return a friendly error result without crashing."""
        malformed_input = "{'type': 'Polygon', invalid_json_content"
        res = validate_and_repair(malformed_input)
        assert res.is_valid is False
        assert res.error is not None or res.error_reason is not None
        assert res.repaired_geojson is None


class TestAccurateMetricsAndUTM:
    """Tests for calculate_metrics and dynamic UTM projection."""

    def test_shanghai_utm_projection(self):
        """Test UTM Zone 51 North deduction in Shanghai (lon ~121.5, lat ~31.2)."""
        zone, epsg = get_utm_epsg(121.47, 31.23)
        assert zone == 51
        assert epsg == 32651

    def test_southern_hemisphere_utm_projection(self):
        """Test UTM Zone 23 South deduction in Rio de Janeiro (lon ~-43.2, lat ~-22.9)."""
        zone, epsg = get_utm_epsg(-43.20, -22.91)
        assert zone == 23
        assert epsg == 32723

    def test_equator_crossing_utm(self):
        """Test polygon crossing the equator (centroid around lat=0.0)."""
        equator_polygon = {
            "type": "Polygon",
            "coordinates": [[
                [10.0, -0.5],
                [11.0, -0.5],
                [11.0, 0.5],
                [10.0, 0.5],
                [10.0, -0.5],
            ]],
        }
        res = calculate_metrics(equator_polygon, unit="sq_meters")
        assert res.error is None
        assert res.projected_epsg in (32632, 32732)
        assert res.area > 0
        assert res.perimeter_meters > 0

    def test_unit_conversions(self):
        """Test area unit conversions between sq_meters, sq_kilometers, and hectares."""
        poly = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]],
        }
        res_m2 = calculate_metrics(poly, unit="sq_meters")
        res_km2 = calculate_metrics(poly, unit="sq_kilometers")
        res_ha = calculate_metrics(poly, unit="hectares")

        assert res_m2.unit == "sq_meters"
        assert res_km2.unit == "sq_kilometers"
        assert res_ha.unit == "hectares"

        assert math.isclose(res_km2.area, res_m2.area / 1_000_000.0, rel_tol=1e-4)
        assert math.isclose(res_ha.area, res_m2.area / 10_000.0, rel_tol=1e-4)

    def test_non_polygon_input_metrics(self):
        """Test that non-polygon input returns friendly error without crashing."""
        point_geojson = {"type": "Point", "coordinates": [121.5, 31.2]}
        res = calculate_metrics(point_geojson)
        assert res.error is not None
        assert res.area == 0.0


class TestSpatialRelationships:
    """Tests for check_relationship."""

    def test_contains_and_within(self):
        """Test contains and within predicates."""
        outer = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
        }
        inner = {
            "type": "Polygon",
            "coordinates": [[[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]],
        }
        res_contains = check_relationship(outer, inner, predicate="contains")
        assert res_contains.result is True

        res_within = check_relationship(inner, outer, predicate="within")
        assert res_within.result is True

    def test_intersects_with_shared_area(self):
        """Test overlapping polygons calculate positive intersection area."""
        poly_a = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
        }
        poly_b = {
            "type": "Polygon",
            "coordinates": [[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]],
        }
        res = check_relationship(poly_a, poly_b, predicate="intersects")
        assert res.result is True
        assert res.details.get("intersection_area_sq_meters", 0.0) > 0.0
        assert res.details.get("distance_meters") == 0.0

    def test_disjoint_with_metric_distance(self):
        """Test disjoint geometries return shortest metric distance."""
        poly_a = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        }
        poly_b = {
            "type": "Polygon",
            "coordinates": [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]],
        }
        res = check_relationship(poly_a, poly_b, predicate="disjoint")
        assert res.result is True
        assert res.details.get("distance_meters", 0.0) > 0.0
        assert res.details.get("intersection_area_sq_meters") == 0.0


class TestBufferGeneration:
    """Tests for generate_buffer."""

    def test_point_buffer_accurate_radius(self):
        """Test 1000m buffer around a point produces circle with area ~pi * r^2."""
        pt = {"type": "Point", "coordinates": [121.5, 31.2]}
        res = generate_buffer(pt, distance_meters=1000.0, quad_segs=16)
        assert res.error is None
        assert res.buffered_geojson is not None
        assert res.buffered_geojson["type"] == "Polygon"

        # Check area in local UTM
        zone, epsg = get_utm_epsg(121.5, 31.2)
        from geospatial_mcp.core.projection import reproject_geometry
        buffered_geom = shape(res.buffered_geojson)
        buffered_utm = reproject_geometry(buffered_geom, 4326, epsg)
        expected_area = math.pi * (1000.0 ** 2)
        assert math.isclose(buffered_utm.area, expected_area, rel_tol=0.05)
