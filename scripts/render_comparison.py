"""
Renders a high-resolution visual comparison:
'Before Repair (Invalid Bowtie Polygon)' vs 'After Repair (OGC-Compliant MultiPolygon)'
Saves as PNG and SVG in docs/assets/ for embedding in README.md.
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from shapely.geometry import Polygon
from shapely.validation import make_valid

# Ensure output directory exists
os.makedirs("docs/assets", exist_ok=True)

# 1. Geometry definitions
# Bowtie polygon (self-intersecting at (1, 1))
bowtie_coords = [(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)]
invalid_poly = Polygon(bowtie_coords)

# Auto-repair using Shapely 2.0 GEOS make_valid
repaired_geom = make_valid(invalid_poly)

# 2. Figure styling & layout
plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"]
plt.rcParams["axes.edgecolor"] = "#CBD5E1"
plt.rcParams["axes.linewidth"] = 1.0

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.2), dpi=300)
fig.patch.set_facecolor("#FFFFFF")

# ==========================================
# Left Subplot: Before (Invalid Bowtie)
# ==========================================
ax1.set_facecolor("#FAFAFA")
ax1.set_title("BEFORE: Invalid Self-Intersecting Polygon\n(LLM Geometry Hallucination)", 
              fontsize=14, fontweight="bold", color="#B91C1C", pad=15)

# Plot invalid bowtie path
xs = [p[0] for p in bowtie_coords]
ys = [p[1] for p in bowtie_coords]

# Draw fill using Polygon patch with winding rule
bowtie_patch = patches.Polygon(bowtie_coords, closed=True, facecolor="#FCA5A5", edgecolor="#DC2626",
                               alpha=0.35, linewidth=2.5, linestyle="--", label="Self-Intersecting Boundary")
ax1.add_patch(bowtie_patch)

# Plot vertices
ax1.scatter(xs[:-1], ys[:-1], color="#DC2626", s=90, zorder=5, edgecolors="#7F1D1D", linewidth=1.5)
for i, (x, y) in enumerate(bowtie_coords[:-1]):
    ax1.text(x + (0.07 if x < 1 else -0.18), y + (0.07 if y < 1 else -0.14),
             f"P{i+1}({x},{y})", fontsize=10, fontweight="600", color="#991B1B")

# Highlight defect at (1, 1)
ax1.scatter([1], [1], color="#EF4444", s=320, zorder=6, marker="X", edgecolors="#7F1D1D", linewidth=2)
ax1.annotate("DEFECT: Self-Intersection at (1.0, 1.0)\nViolates OGC Simple Features",
             xy=(1, 1), xytext=(0.2, 1.6),
             arrowprops=dict(facecolor="#DC2626", edgecolor="#7F1D1D", width=2, headwidth=9, shrink=0.1),
             fontsize=11, fontweight="bold", color="#B91C1C",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#FEE2E2", edgecolor="#EF4444", alpha=0.95))

# Status Badge
ax1.text(0.04, 0.94, "[INVALID] OGC Defect: Self-Intersection", transform=ax1.transAxes,
         fontsize=11, fontweight="bold", color="#FFFFFF",
         bbox=dict(boxstyle="round,pad=0.4", facecolor="#DC2626", edgecolor="none"))

ax1.set_xlim(-0.3, 2.3)
ax1.set_ylim(-0.3, 2.3)
ax1.set_aspect("equal")
ax1.grid(True, linestyle=":", color="#E2E8F0", alpha=0.8)
ax1.set_xlabel("X (Planar Coordinates)", fontsize=11, color="#64748B")
ax1.set_ylabel("Y (Planar Coordinates)", fontsize=11, color="#64748B")

# ==========================================
# Right Subplot: After (Valid MultiPolygon)
# ==========================================
ax2.set_facecolor("#FAFAFA")
ax2.set_title("AFTER: Repaired & Normalized MultiPolygon\n(FastMCP validate_and_repair_geometry)", 
              fontsize=14, fontweight="bold", color="#047857", pad=15)

# Repaired consists of 2 polygons
for poly in repaired_geom.geoms:
    px, py = poly.exterior.xy
    poly_patch = patches.Polygon(list(zip(px, py)), closed=True, facecolor="#A7F3D0", edgecolor="#059669",
                                 alpha=0.5, linewidth=2.5, linestyle="-")
    ax2.add_patch(poly_patch)
    ax2.scatter(px[:-1], py[:-1], color="#059669", s=80, zorder=5, edgecolors="#064E3B", linewidth=1.5)

# Annotate healing
ax2.annotate("Topology Auto-Healed into 2 Valid Polygons\nArea: 2.0000 | RFC 7946 Normalized",
             xy=(1.0, 1.0), xytext=(0.2, 1.6),
             arrowprops=dict(facecolor="#059669", edgecolor="#064E3B", width=2, headwidth=9, shrink=0.1),
             fontsize=11, fontweight="bold", color="#065F46",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#ECFDF5", edgecolor="#10B981", alpha=0.95))

# Status Badge
ax2.text(0.04, 0.94, "[RESOLVED] OGC Compliant: MultiPolygon", transform=ax2.transAxes,
         fontsize=11, fontweight="bold", color="#FFFFFF",
         bbox=dict(boxstyle="round,pad=0.4", facecolor="#059669", edgecolor="none"))

ax2.set_xlim(-0.3, 2.3)
ax2.set_ylim(-0.3, 2.3)
ax2.set_aspect("equal")
ax2.grid(True, linestyle=":", color="#E2E8F0", alpha=0.8)
ax2.set_xlabel("X (Coordinates)", fontsize=11, color="#64748B")
ax2.set_ylabel("Y (Coordinates)", fontsize=11, color="#64748B")

plt.tight_layout()

# Save PNG and SVG
png_path = "docs/assets/topology_repair_comparison.png"
svg_path = "docs/assets/topology_repair_comparison.svg"
plt.savefig(png_path, dpi=300, bbox_inches="tight")
plt.savefig(svg_path, bbox_inches="tight")
plt.close()

print(f"Generated comparison graphic:\n- {png_path}\n- {svg_path}")
