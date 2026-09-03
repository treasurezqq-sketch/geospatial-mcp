"""
FastMCP Server for GeoSpatial-MCP.
Exposes atomic spatial data topology verification, measurement, and analysis tools for AI agents.
Strictly relies on Shapely 2.0 native C API, PyProj, and Pydantic v2.
"""

from typing import Any, Dict, List, Optional, Union
from fastmcp import FastMCP

from geospatial_mcp.core.geometry import (
    validate_and_repair,
    calculate_metrics,
    check_relationship,
    generate_buffer as core_generate_buffer,
)
from geospatial_mcp.models import (
    GeometryValidationResult,
    AccurateMetricsResult,
    SpatialRelationshipResult,
    BufferResult,
    MetricUnit,
    RelationshipPredicate,
    AccurateMetricsInput,
)

# Initialize FastMCP Server
mcp = FastMCP(
    "geospatial-mcp",
)


@mcp.tool()
def validate_and_repair_geometry(
    geojson: Union[str, Dict[str, Any], List[Any]],
) -> GeometryValidationResult:
    """
    Validates the topological validity of a geometry against OGC Simple Features standards
    and automatically repairs topological defects (e.g. self-intersections, bowtie polygons,
    unclosed rings) into compliant GeoJSON.

    Fault tolerance: Accepts raw GeoJSON strings, Markdown-wrapped JSON, Feature,
    FeatureCollection, pure GeoJSON dictionary, or coordinate lists.

    Args:
        geojson: Input spatial data (GeoJSON string, dictionary, Feature, or coordinates array).

    Returns:
        GeometryValidationResult containing:
          - is_valid: Boolean indicating whether the original geometry was topologically valid.
          - error_reason: Detailed error description if invalid (e.g. 'Self-intersection[x y]').
          - repaired_geojson: Clean, RFC 7946 compliant GeoJSON dictionary.
    """
    return validate_and_repair(geojson)


@mcp.tool()
def calculate_accurate_metrics(
    geojson: Union[str, Dict[str, Any], List[Any]],
    unit: MetricUnit = "sq_meters",
    target_unit: Optional[MetricUnit] = None,
) -> AccurateMetricsResult:
    """
    Calculates distortion-free area and perimeter for a polygon by automatically identifying
    the optimal local UTM projection zone from the geometry centroid and reprojecting to metric units.

    Dual-parameter compatibility: Supports both `unit` and `target_unit` as the target unit argument.

    Args:
        geojson: GeoJSON Polygon, MultiPolygon, Feature, or coordinates array.
        unit: Target area unit ('sq_meters', 'sq_kilometers', or 'hectares'). Default is 'sq_meters'.
        target_unit: Alias for `unit` for backward and client compatibility.

    Returns:
        AccurateMetricsResult containing:
          - area: Calculated area in the specified target unit.
          - perimeter_meters: Total boundary perimeter in meters.
          - unit: Applied target unit name.
          - projected_epsg: Integer EPSG code of the UTM projection used (e.g. 32650, 32718).
    """
    # Normalize input through Pydantic model with alias support
    payload: Dict[str, Any] = {"geojson": geojson}
    if target_unit is not None:
        payload["target_unit"] = target_unit
    else:
        payload["unit"] = unit

    validated = AccurateMetricsInput(**payload)
    return calculate_metrics(validated.geojson, unit=validated.unit)


@mcp.tool()
def check_spatial_relationship(
    geom_a: Union[str, Dict[str, Any], List[Any]],
    geom_b: Union[str, Dict[str, Any], List[Any]],
    predicate: RelationshipPredicate = "intersects",
) -> SpatialRelationshipResult:
    """
    Determines topological relationships between two geometry objects (Point-in-Polygon,
    containment, overlap, disjoint separation) and provides quantitative readings
    (metric distance in meters or shared intersection area in square meters).

    Args:
        geom_a: First spatial object (GeoJSON string, dict, Feature, or coordinates).
        geom_b: Second spatial object (GeoJSON string, dict, Feature, or coordinates).
        predicate: Topological predicate: 'contains', 'within', 'intersects', or 'disjoint'.

    Returns:
        SpatialRelationshipResult containing:
          - result: Boolean (True/False) judgment for the requested predicate.
          - details: Dictionary with 'intersection_area_sq_meters', 'distance_meters', etc.
    """
    return check_relationship(geom_a, geom_b, predicate=predicate)


@mcp.tool()
def generate_buffer(
    geojson: Union[str, Dict[str, Any], List[Any]],
    distance_meters: float,
    quad_segs: int = 8,
) -> BufferResult:
    """
    Constructs an accurate metric buffer zone using local UTM metric projection,
    handles self-intersections, and projects back to standard EPSG:4326 GeoJSON.

    Args:
        geojson: Input geometry (GeoJSON string, dict, Feature, or coordinates).
        distance_meters: Buffer radius in meters (positive for expansion, negative for erosion).
        quad_segs: Quadrant segments for circular arc approximation (default 8).

    Returns:
        BufferResult containing:
          - buffered_geojson: Clean, RFC 7946 compliant GeoJSON dictionary in EPSG:4326.
    """
    return core_generate_buffer(
        geojson,
        distance_meters=distance_meters,
        quad_segs=quad_segs,
    )


def main() -> None:
    """CLI entrypoint to run the FastMCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
