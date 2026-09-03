"""
Core spatial geometry processing: topology validation and auto-repair,
accurate UTM metric measurements, spatial relationship evaluations, and metric buffering.
Strictly relies on shapely>=2.0 and pyproj (no GDAL, Fiona, or GeoPandas).
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import shapely
from shapely.geometry import (
    Point,
    LineString,
    Polygon,
    MultiPoint,
    MultiLineString,
    MultiPolygon,
    GeometryCollection,
    shape,
    mapping,
)
from shapely.geometry.polygon import orient
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity, make_valid

from geospatial_mcp.core.projection import (
    get_utm_epsg,
    reproject_geometry,
    is_likely_projected,
)
from geospatial_mcp.models import (
    GeometryValidationResult,
    AccurateMetricsResult,
    SpatialRelationshipResult,
    BufferResult,
    MetricUnit,
    RelationshipPredicate,
)


def _strip_markdown_code_fences(text: str) -> str:
    """Strip markdown code block markers such as ```json ... ```."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def _normalize_winding(geom: BaseGeometry) -> BaseGeometry:
    """Normalize polygon ring winding per RFC 7946 (exterior CCW, holes CW)."""
    if isinstance(geom, Polygon):
        return orient(geom, sign=1.0)
    elif isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(p, sign=1.0) for p in geom.geoms])
    elif isinstance(geom, GeometryCollection):
        rebuilt = []
        for g in geom.geoms:
            if isinstance(g, (Polygon, MultiPolygon)):
                rebuilt.append(_normalize_winding(g))
            else:
                rebuilt.append(g)
        return GeometryCollection(rebuilt)
    return geom


def to_geojson_dict(geom: BaseGeometry) -> Dict[str, Any]:
    """Convert a Shapely geometry to a standard JSON-serializable GeoJSON dict."""
    return mapping(geom)


def _check_unclosed_rings(coords: Any) -> bool:
    """Recursively check if any polygon coordinate ring is unclosed."""
    if not isinstance(coords, (list, tuple)) or len(coords) == 0:
        return False
    # If coords is a list of points [[x, y], [x, y], ...]
    if isinstance(coords[0], (list, tuple)) and not isinstance(coords[0][0], (list, tuple)):
        # This is a linear ring
        if len(coords) >= 3 and coords[0] != coords[-1]:
            return True
        return False
    # If nested list (Polygon rings or MultiPolygon)
    return any(_check_unclosed_rings(sub) for sub in coords)


def _close_unclosed_rings(coords: Any) -> Any:
    """Recursively auto-close unclosed coordinate rings."""
    if not isinstance(coords, (list, tuple)) or len(coords) == 0:
        return coords
    if isinstance(coords[0], (list, tuple)) and not isinstance(coords[0][0], (list, tuple)):
        # Linear ring
        ring = list(coords)
        if len(ring) >= 3 and ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring
    return [_close_unclosed_rings(sub) for sub in coords]


def parse_spatial_input(raw_input: Any, prefer_polygon: bool = False) -> Tuple[BaseGeometry, bool, Optional[str]]:
    """
    Ultra-robust spatial data parser designed for LLM and agent input tolerance.
    
    Accepts:
      - GeoJSON string (standard, or wrapped in Markdown ```json)
      - GeoJSON dictionary (Geometry, Feature, or FeatureCollection)
      - Bare coordinates array / nested lists
      - Existing Shapely geometry instance

    Returns:
      Tuple of (Shapely BaseGeometry, was_originally_unclosed_bool, unclosed_error_reason_or_none)
    """
    if raw_input is None:
        raise ValueError("Spatial input cannot be None.")

    if isinstance(raw_input, BaseGeometry):
        return raw_input, False, None

    data = raw_input

    # 1. Parse JSON string if string provided
    if isinstance(data, str):
        cleaned_str = _strip_markdown_code_fences(data)
        if not cleaned_str:
            raise ValueError("Empty spatial input string provided.")

        try:
            data = json.loads(cleaned_str)
        except json.JSONDecodeError as e:
            # Try WKT as fallback
            wkt_match = re.match(
                r"^(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON|GEOMETRYCOLLECTION)\b",
                cleaned_str,
                re.IGNORECASE,
            )
            if wkt_match:
                try:
                    return shapely.from_wkt(cleaned_str), False, None
                except Exception as wkt_err:
                    raise ValueError(f"Failed to parse as WKT geometry: {wkt_err}") from wkt_err
            raise ValueError(f"Invalid GeoJSON string syntax: {e}") from e

    # 2. Extract geometry from Feature or FeatureCollection
    was_unclosed = False
    unclosed_reason = None

    if isinstance(data, dict):
        geo_type = data.get("type", "")

        if geo_type == "FeatureCollection":
            features = data.get("features", [])
            if not features:
                raise ValueError("FeatureCollection contains no features.")
            geoms = []
            for f in features:
                if isinstance(f, dict) and "geometry" in f and f["geometry"]:
                    g, unclosed, _ = parse_spatial_input(f["geometry"], prefer_polygon=prefer_polygon)
                    was_unclosed = was_unclosed or unclosed
                    geoms.append(g)
            if not geoms:
                raise ValueError("No valid geometry found in FeatureCollection.")
            if len(geoms) == 1:
                return geoms[0], was_unclosed, None
            return GeometryCollection(geoms), was_unclosed, None

        elif geo_type == "Feature":
            geom_part = data.get("geometry")
            if not geom_part or not isinstance(geom_part, dict):
                raise ValueError("Feature object has missing or invalid 'geometry' field.")
            return parse_spatial_input(geom_part, prefer_polygon=prefer_polygon)

        elif geo_type in {
            "Point",
            "LineString",
            "Polygon",
            "MultiPoint",
            "MultiLineString",
            "MultiPolygon",
            "GeometryCollection",
        }:
            coords = data.get("coordinates")
            if coords is not None and _check_unclosed_rings(coords):
                was_unclosed = True
                unclosed_reason = "Points of LinearRing do not form a closed linestring"
                # Auto-close coordinates so Shapely can construct the geometry for repair
                data = dict(data)
                data["coordinates"] = _close_unclosed_rings(coords)

            try:
                geom = shape(data)
                return geom, was_unclosed, unclosed_reason
            except Exception as shape_err:
                raise ValueError(f"Failed to construct {geo_type} geometry: {shape_err}") from shape_err

        elif "coordinates" in data:
            coords = data["coordinates"]
            if _check_unclosed_rings(coords):
                was_unclosed = True
                unclosed_reason = "Points of LinearRing do not form a closed linestring"
                coords = _close_unclosed_rings(coords)
            geom = _coords_to_geom(coords, prefer_polygon=prefer_polygon)
            return geom, was_unclosed, unclosed_reason

        else:
            raise ValueError(
                f"Cannot parse dictionary as GeoJSON geometry. Keys found: {list(data.keys())}."
            )

    # 3. Handle raw coordinates array
    if isinstance(data, (list, tuple)):
        if _check_unclosed_rings(data):
            was_unclosed = True
            unclosed_reason = "Points of LinearRing do not form a closed linestring"
            data = _close_unclosed_rings(data)
        geom = _coords_to_geom(data, prefer_polygon=prefer_polygon)
        return geom, was_unclosed, unclosed_reason

    raise TypeError(f"Unsupported spatial data type: {type(data).__name__}")


def _coords_to_geom(coords: Any, prefer_polygon: bool = False) -> BaseGeometry:
    """Helper to convert coordinate lists to Shapely geometries based on nesting."""
    if not isinstance(coords, (list, tuple)) or len(coords) == 0:
        raise ValueError("Coordinate array is empty or invalid.")

    # Determine depth
    depth = 1
    curr = coords
    while isinstance(curr, (list, tuple)) and len(curr) > 0 and isinstance(curr[0], (list, tuple)):
        depth += 1
        curr = curr[0]

    if depth == 1:
        if len(coords) < 2:
            raise ValueError("Point requires at least [x, y] coordinates.")
        return Point(float(coords[0]), float(coords[1]))

    elif depth == 2:
        if len(coords) < 2:
            raise ValueError("LineString requires at least 2 coordinate pairs.")
        is_closed = len(coords) >= 4 and coords[0] == coords[-1]
        if is_closed or (prefer_polygon and len(coords) >= 3):
            ring = list(coords)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            return Polygon(ring)
        return LineString(coords)

    elif depth == 3:
        shell = list(coords[0])
        if len(shell) >= 3 and shell[0] != shell[-1]:
            shell.append(shell[0])
        holes = []
        for h in coords[1:]:
            h_list = list(h)
            if len(h_list) >= 3 and h_list[0] != h_list[-1]:
                h_list.append(h_list[0])
            holes.append(h_list)
        return Polygon(shell, holes)

    elif depth == 4:
        polys = []
        for poly_coords in coords:
            shell = list(poly_coords[0])
            if len(shell) >= 3 and shell[0] != shell[-1]:
                shell.append(shell[0])
            holes = []
            for h in poly_coords[1:]:
                h_list = list(h)
                if len(h_list) >= 3 and h_list[0] != h_list[-1]:
                    h_list.append(h_list[0])
                holes.append(h_list)
            polys.append(Polygon(shell, holes))
        return MultiPolygon(polys)

    raise ValueError(f"Unsupported coordinate nesting depth: {depth}")


# =========================================================
# 1. validate_and_repair_geometry
# =========================================================


def validate_and_repair(raw_input: Any) -> GeometryValidationResult:
    """
    Validate geometry against OGC Simple Features rules and automatically repair any topological defects.
    Tolerates unclosed rings, self-intersections (bowties), and malformed structures.
    """
    try:
        geom, was_unclosed, unclosed_reason = parse_spatial_input(raw_input)
    except Exception as e:
        return GeometryValidationResult(
            is_valid=False,
            error_reason=f"Malformed or unparseable GeoJSON: {str(e)}",
            repaired_geojson=None,
            error=str(e),
        )

    # Check validity
    is_shapely_valid = bool(shapely.is_valid(geom))

    if is_shapely_valid and not was_unclosed:
        normalized_geom = _normalize_winding(geom)
        return GeometryValidationResult(
            is_valid=True,
            error_reason=None,
            repaired_geojson=to_geojson_dict(normalized_geom),
        )
    else:
        # Invalid topology or unclosed ring
        if was_unclosed and unclosed_reason:
            reason = unclosed_reason
        else:
            reason = shapely.validation.explain_validity(geom)

        repaired = make_valid(geom)
        repaired = _normalize_winding(repaired)

        return GeometryValidationResult(
            is_valid=False,
            error_reason=reason,
            repaired_geojson=to_geojson_dict(repaired),
        )


# =========================================================
# 2. calculate_accurate_metrics
# =========================================================


def calculate_metrics(
    raw_input: Any,
    unit: MetricUnit = "sq_meters",
) -> AccurateMetricsResult:
    """
    Calculates distortion-free area and perimeter by projecting to the local optimal UTM zone.
    """
    try:
        geom, _, _ = parse_spatial_input(raw_input, prefer_polygon=True)
    except Exception as e:
        return AccurateMetricsResult(
            area=0.0,
            perimeter_meters=0.0,
            unit=unit,
            projected_epsg=0,
            error=f"Invalid polygon input: {str(e)}",
        )

    if not geom.is_valid:
        geom = make_valid(geom)

    # Require polygonal geometry for area calculations
    if geom.geom_type not in {"Polygon", "MultiPolygon", "GeometryCollection"}:
        return AccurateMetricsResult(
            area=0.0,
            perimeter_meters=0.0,
            unit=unit,
            projected_epsg=0,
            error=f"Area and perimeter calculation requires a Polygon or MultiPolygon, got: {geom.geom_type}",
        )

    centroid = geom.centroid

    if is_likely_projected(geom):
        geom_proj = geom
        epsg_code = 0
    else:
        _, epsg_code = get_utm_epsg(centroid.x, centroid.y)
        geom_proj = reproject_geometry(geom, 4326, epsg_code)

    area_sq_m = round(float(geom_proj.area), 4)
    perimeter_m = round(float(geom_proj.length), 4)

    unit_clean = unit.lower().strip()
    if unit_clean == "sq_kilometers":
        calculated_area = round(area_sq_m / 1_000_000.0, 6)
    elif unit_clean == "hectares":
        calculated_area = round(area_sq_m / 10_000.0, 6)
    else:
        unit_clean = "sq_meters"
        calculated_area = area_sq_m

    return AccurateMetricsResult(
        area=calculated_area,
        perimeter_meters=perimeter_m,
        unit=unit_clean,
        projected_epsg=epsg_code,
    )


# =========================================================
# 3. check_spatial_relationship
# =========================================================


def check_relationship(
    geom_a_raw: Any,
    geom_b_raw: Any,
    predicate: RelationshipPredicate = "intersects",
) -> SpatialRelationshipResult:
    """
    Evaluates topological relationship between two geometries and provides quantitative measurements.
    """
    try:
        geom_a, _, _ = parse_spatial_input(geom_a_raw)
        geom_b, _, _ = parse_spatial_input(geom_b_raw)
    except Exception as e:
        return SpatialRelationshipResult(
            result=False,
            details={},
            error=f"Invalid geometry input: {str(e)}",
        )

    if not geom_a.is_valid:
        geom_a = make_valid(geom_a)
    if not geom_b.is_valid:
        geom_b = make_valid(geom_b)

    pred_clean = predicate.lower().strip()

    if pred_clean == "contains":
        verdict = bool(geom_a.contains(geom_b))
    elif pred_clean == "within":
        verdict = bool(geom_a.within(geom_b))
    elif pred_clean == "intersects":
        verdict = bool(geom_a.intersects(geom_b))
    elif pred_clean == "disjoint":
        verdict = bool(geom_a.disjoint(geom_b))
    else:
        return SpatialRelationshipResult(
            result=False,
            details={},
            error=f"Unsupported predicate: '{predicate}'. Expected contains, within, intersects, or disjoint.",
        )

    # Project to metric UTM coordinates for distance / area measurement
    mid_lon = (geom_a.centroid.x + geom_b.centroid.x) / 2.0
    mid_lat = (geom_a.centroid.y + geom_b.centroid.y) / 2.0

    if is_likely_projected(geom_a) or is_likely_projected(geom_b):
        a_proj = geom_a
        b_proj = geom_b
        epsg = 0
    else:
        _, epsg = get_utm_epsg(mid_lon, mid_lat)
        a_proj = reproject_geometry(geom_a, 4326, epsg)
        b_proj = reproject_geometry(geom_b, 4326, epsg)

    details: Dict[str, Any] = {
        "predicate": pred_clean,
        "projected_epsg": epsg,
    }

    if geom_a.intersects(geom_b):
        try:
            inter = a_proj.intersection(b_proj)
            inter_area = round(float(inter.area), 4)
        except Exception:
            inter_area = 0.0
        details["intersection_area_sq_meters"] = inter_area
        details["distance_meters"] = 0.0
    else:
        try:
            dist = round(float(a_proj.distance(b_proj)), 4)
        except Exception:
            dist = 0.0
        details["intersection_area_sq_meters"] = 0.0
        details["distance_meters"] = dist

    return SpatialRelationshipResult(
        result=verdict,
        details=details,
    )


# =========================================================
# 4. generate_buffer
# =========================================================


def generate_buffer(
    raw_input: Any,
    distance_meters: float,
    quad_segs: int = 8,
) -> BufferResult:
    """
    Constructs an accurate metric buffer in UTM projection, auto-repairs self-intersections,
    and returns compliant EPSG:4326 GeoJSON.
    """
    try:
        geom, _, _ = parse_spatial_input(raw_input)
    except Exception as e:
        return BufferResult(
            buffered_geojson=None,
            error=f"Invalid geometry input for buffer: {str(e)}",
        )

    if not geom.is_valid:
        geom = make_valid(geom)

    # Project to metric UTM
    if is_likely_projected(geom):
        geom_utm = geom
        epsg = 0
    else:
        centroid = geom.centroid
        _, epsg = get_utm_epsg(centroid.x, centroid.y)
        geom_utm = reproject_geometry(geom, 4326, epsg)

    # Apply metric buffer
    buffered_utm = geom_utm.buffer(distance_meters, quad_segs=quad_segs)
    if not buffered_utm.is_valid:
        buffered_utm = make_valid(buffered_utm)

    # Reproject back to WGS84
    if epsg != 0:
        buffered_wgs84 = reproject_geometry(buffered_utm, epsg, 4326)
    else:
        buffered_wgs84 = buffered_utm

    buffered_wgs84 = _normalize_winding(buffered_wgs84)

    return BufferResult(
        buffered_geojson=to_geojson_dict(buffered_wgs84),
    )
