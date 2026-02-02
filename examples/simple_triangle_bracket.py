#!/usr/bin/env python3
"""
Simple Triangle Bracket for FEA Testing

A triangular bracket with clean geometry (no chamfers/fillets)
for better mesh quality in FEA analysis.

Parameters:
    SIDE_LENGTH: Triangle side length (mm)
    THICKNESS: Plate thickness (mm)
    HOLE_DIAMETER: Bolt hole diameter (mm)
    HOLE_INSET: Distance from corner to hole center (mm)
"""

import cadquery as cq
import math
from pathlib import Path

# Parameters
SIDE_LENGTH = 80       # Length of triangle side (mm)
THICKNESS = 6          # Plate thickness (mm)
HOLE_DIAMETER = 6.5    # M6 clearance hole
HOLE_INSET = 15        # Distance from corner to hole center


def inset_point(vertex: tuple, inset: float, center: tuple = (0, 0)) -> tuple:
    """Move a point toward center by inset amount."""
    cx, cy = center
    vx, vy = vertex
    dx, dy = cx - vx, cy - vy
    length = math.sqrt(dx * dx + dy * dy)
    return (vx + dx / length * inset, vy + dy / length * inset)


def create_simple_bracket(
    side_length: float = SIDE_LENGTH,
    thickness: float = THICKNESS,
    hole_diameter: float = HOLE_DIAMETER,
    hole_inset: float = HOLE_INSET
) -> cq.Workplane:
    """
    Create a simple triangular bracket without chamfers or fillets.
    """
    # Calculate equilateral triangle vertices
    height = (math.sqrt(3) / 2) * side_length

    # Vertices centered at origin: top, bottom-left, bottom-right
    top = (0, height * 2 / 3)
    bottom_left = (-side_length / 2, -height * 1 / 3)
    bottom_right = (side_length / 2, -height * 1 / 3)

    # Calculate hole positions (inset from corners toward center)
    hole_top = inset_point(top, hole_inset)
    hole_bl = inset_point(bottom_left, hole_inset)
    hole_br = inset_point(bottom_right, hole_inset)

    # Build the bracket (simple, no chamfers/fillets)
    result = (
        cq.Workplane("XY")
        # Create triangle profile
        .moveTo(*top)
        .lineTo(*bottom_right)
        .lineTo(*bottom_left)
        .close()
        .extrude(thickness)
        # Add bolt holes at each corner
        .faces(">Z")
        .workplane()
        .pushPoints([hole_top, hole_bl, hole_br])
        .hole(hole_diameter)
    )

    return result


# Create the bracket
result = create_simple_bracket()

# Export if run directly
if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Export files
    step_path = output_dir / "simple_bracket.step"
    stl_path = output_dir / "simple_bracket.stl"

    cq.exporters.export(result, str(step_path))
    # Export STL with fine tessellation
    cq.exporters.export(result, str(stl_path), exportType="STL",
                        tolerance=0.05, angularTolerance=0.05)

    # Print info
    bb = result.val().BoundingBox()
    print(f"Simple Triangle Bracket Created!")
    print(f"   Side length: {SIDE_LENGTH} mm")
    print(f"   Thickness: {THICKNESS} mm")
    print(f"   Holes: 3x {HOLE_DIAMETER}mm diameter")
    print(f"   Size: {bb.xmax - bb.xmin:.1f} x {bb.ymax - bb.ymin:.1f} x {bb.zmax - bb.zmin:.1f} mm")
    print(f"   Volume: {result.val().Volume():.1f} mm^3")
    print(f"\n   Files:")
    print(f"   - {step_path}")
    print(f"   - {stl_path}")
    print(f"\n   View with: ./view {stl_path}")
