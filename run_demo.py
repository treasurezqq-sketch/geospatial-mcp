"""
Quick local demonstration script for geospatial-mcp.
Run this script to directly test all 4 core spatial tools.
"""

import sys
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from geospatial_mcp.server import (
    validate_and_repair_geometry,
    calculate_accurate_metrics,
    check_spatial_relationship,
    generate_buffer,
)

print("=" * 60)
print("🌍 GeoSpatial-MCP Local Quick Demo")
print("=" * 60)

# 1. Validate and repair a self-intersecting bowtie polygon
print("\n[1] Testing 'validate_and_repair_geometry':")
bowtie = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]],
}
repair_res = validate_and_repair_geometry(bowtie)
print(f"  - Original Is Valid : {repair_res.is_valid}")
print(f"  - Defect Cause      : {repair_res.error_reason}")
print(f"  - Repaired Type     : {repair_res.repaired_geojson['type']}")
print(f"  - Repaired Polygons : {len(repair_res.repaired_geojson['coordinates'])} valid components")

# 2. Calculate accurate projected metric area & perimeter
print("\n[2] Testing 'calculate_accurate_metrics':")
shanghai_parcel = {
    "type": "Polygon",
    "coordinates": [[[121.47, 31.23], [121.48, 31.23], [121.48, 31.24], [121.47, 31.24], [121.47, 31.23]]],
}
metrics_res = calculate_accurate_metrics(shanghai_parcel, unit="hectares")
print(f"  - Auto-detected UTM : EPSG:{metrics_res.projected_epsg}")
print(f"  - Planar Area       : {metrics_res.area} {metrics_res.unit}")
print(f"  - Perimeter         : {metrics_res.perimeter_meters} meters")

# 3. Check spatial relationship between two geometries
print("\n[3] Testing 'check_spatial_relationship':")
poly_a = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
poly_b = {"type": "Polygon", "coordinates": [[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]}
relation_res = check_spatial_relationship(poly_a, poly_b, predicate="intersects")
print(f"  - Predicate Evaluated: 'intersects'")
print(f"  - Verdict Outcome    : {relation_res.result}")
print(f"  - Shared Overlap Area: {relation_res.details.get('intersection_area_sq_meters')} m²")

# 4. Generate accurate metric buffer
print("\n[4] Testing 'generate_buffer':")
pt = {"type": "Point", "coordinates": [121.5, 31.2]}
buffer_res = generate_buffer(pt, distance_meters=500.0, quad_segs=8)
print(f"  - Applied Radius: 500.0 meters")
print(f"  - Buffered Type : {buffer_res.buffered_geojson['type']}")
print(f"  - Coordinate Rings Generated Successfully!")

print("\n" + "=" * 60)
print("✅ All 4 local tools executed successfully!")
print("=" * 60)
