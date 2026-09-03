"""
Pydantic v2 schemas and models for GeoSpatial-MCP.
Provides strict validation, dual-key compatibility (unit/target_unit),
and dual access patterns (attribute and dictionary indexing).
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

MetricUnit = Literal["sq_meters", "sq_kilometers", "hectares"]
RelationshipPredicate = Literal[
    "contains",
    "within",
    "intersects",
    "disjoint",
]


class BaseResultModel(BaseModel):
    """Base model supporting both attribute access (res.prop) and dict access (res['prop'])."""

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


# ==========================================
# Input Schemas
# ==========================================


class GeometryValidationInput(BaseModel):
    """Input parameters for geometry validation and topological repair."""

    geojson: Union[str, Dict[str, Any], List[Any]] = Field(
        description="GeoJSON geometry, Feature, FeatureCollection, or raw coordinates."
    )


class AccurateMetricsInput(BaseModel):
    """Input parameters for accurate spatial metric measurement."""

    model_config = ConfigDict(populate_by_name=True)

    geojson: Union[str, Dict[str, Any], List[Any]] = Field(
        description="Polygon or MultiPolygon GeoJSON (string, dict, or coordinates)."
    )
    unit: MetricUnit = Field(
        default="sq_meters",
        alias="target_unit",
        description="Target area unit: 'sq_meters', 'sq_kilometers', or 'hectares'.",
    )


class SpatialRelationshipInput(BaseModel):
    """Input parameters for topological relationship determination."""

    geom_a: Union[str, Dict[str, Any], List[Any]] = Field(
        description="First geometry (GeoJSON string, dict, or coordinates)."
    )
    geom_b: Union[str, Dict[str, Any], List[Any]] = Field(
        description="Second geometry (GeoJSON string, dict, or coordinates)."
    )
    predicate: RelationshipPredicate = Field(
        default="intersects",
        description="Topological predicate to evaluate: 'contains', 'within', 'intersects', 'disjoint'.",
    )


class BufferInput(BaseModel):
    """Input parameters for metric buffer generation."""

    geojson: Union[str, Dict[str, Any], List[Any]] = Field(
        description="Input geometry to buffer (GeoJSON string, dict, or coordinates)."
    )
    distance_meters: float = Field(
        description="Buffer distance/radius in meters (positive expands, negative erodes)."
    )
    quad_segs: int = Field(
        default=8,
        ge=1,
        description="Number of segments used to approximate a quarter circle (default 8).",
    )


# ==========================================
# Output Schemas
# ==========================================


class GeometryValidationResult(BaseResultModel):
    """Result of geometry topological validation and automatic repair."""

    is_valid: bool = Field(
        description="Whether the original geometry satisfies OGC Simple Features topology validity."
    )
    error_reason: Optional[str] = Field(
        default=None,
        description="Topological error cause (e.g. self-intersection, unclosed ring) if invalid.",
    )
    repaired_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Valid, compliant GeoJSON Geometry dictionary (RFC 7946 compliant).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error description if input was malformed or unparseable.",
    )


class AccurateMetricsResult(BaseResultModel):
    """Accurate planar and metric spatial measurements via automatic UTM projection."""

    area: float = Field(
        description="Calculated area value in the requested unit."
    )
    perimeter_meters: float = Field(
        description="Total boundary perimeter length in meters."
    )
    unit: str = Field(
        description="Unit of the returned area ('sq_meters', 'sq_kilometers', or 'hectares')."
    )
    projected_epsg: int = Field(
        description="EPSG integer code of the metric UTM projection used (e.g. 32650, 32718)."
    )
    error: Optional[str] = Field(
        default=None,
        description="Error description if input was malformed or non-polygonal.",
    )


class SpatialRelationshipResult(BaseResultModel):
    """Evaluation of spatial topological relationship and quantitative interaction."""

    result: bool = Field(
        description="Boolean judgment whether the requested relationship predicate holds."
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Quantitative details (intersection_area_sq_meters, distance_meters, etc.).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error description if input geometries were malformed.",
    )


class BufferResult(BaseResultModel):
    """Metric buffer generation result reprojected to EPSG:4326 WGS84."""

    buffered_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Resulting GeoJSON Geometry object in WGS84 (EPSG:4326).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error description if input was malformed or buffering failed.",
    )
