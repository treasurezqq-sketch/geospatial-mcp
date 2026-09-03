"""
Dynamic UTM projection detection and coordinate reference system transformations using pyproj.
Enables precise metric planar calculations from WGS84 geographic coordinates.
"""

from typing import Tuple, Union
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


def is_likely_projected(geom: BaseGeometry) -> bool:
    """
    Check if the geometry bounds appear to already be in a projected Cartesian coordinate system
    (coordinates in meters > 180 / 90) rather than degrees WGS84.
    """
    minx, miny, maxx, maxy = geom.bounds
    return abs(minx) > 180.0 or abs(maxx) > 180.0 or abs(miny) > 90.0 or abs(maxy) > 90.0


def get_utm_epsg(lon: float, lat: float) -> Tuple[int, int]:
    """
    Automatically deduce the optimal UTM projection zone and integer EPSG code
    for a given WGS84 longitude and latitude.

    Parameters:
      lon: Longitude in degrees (-180.0 to 180.0).
      lat: Latitude in degrees (-90.0 to 90.0).

    Returns:
      Tuple of (zone_number, epsg_code_int), e.g. (51, 32651).
    """
    # Normalize longitude to [-180.0, 180.0)
    normalized_lon = ((lon + 180.0) % 360.0) - 180.0

    # Calculate UTM Zone 1-60
    zone_number = int((normalized_lon + 180.0) / 6.0) + 1
    zone_number = max(1, min(60, zone_number))

    # Northern hemisphere (EPSG:326xx) or Southern hemisphere (EPSG:327xx)
    is_north = lat >= 0.0
    epsg_int = (32600 if is_north else 32700) + zone_number

    return zone_number, epsg_int


def reproject_geometry(
    geom: BaseGeometry,
    source_crs: Union[str, int],
    target_crs: Union[str, int],
) -> BaseGeometry:
    """
    Reproject a Shapely geometry between coordinate systems using pyproj.
    Uses always_xy=True to enforce (x, y) / (lon, lat) axis order.
    """
    src_str = f"EPSG:{source_crs}" if isinstance(source_crs, int) else str(source_crs)
    tgt_str = f"EPSG:{target_crs}" if isinstance(target_crs, int) else str(target_crs)

    if src_str.upper() == tgt_str.upper():
        return geom

    transformer = Transformer.from_crs(src_str, tgt_str, always_xy=True)
    return transform(transformer.transform, geom)
