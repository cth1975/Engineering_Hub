#!/usr/bin/env python3
"""
Example: Triangular Mounting Bracket

A triangular bracket with:
- Equilateral triangle shape
- 3 bolt holes (one at each corner)
- Chamfered corners for safety/aesthetics
- Filleted edges

Parameters:
    SIDE_LENGTH: Triangle side length (mm)
    THICKNESS: Plate thickness (mm)
    HOLE_DIAMETER: Bolt hole diameter (mm)
    HOLE_INSET: Distance from corner to hole center (mm)
    CHAMFER_SIZE: Corner chamfer size (mm)
    EDGE_FILLET: Top/bottom edge fillet (mm)

Usage:
    python examples/triangle_bracket.py
    ./view output/triangle_bracket.stl
"""

import cadquery as cq
import math
from pathlib import Path

# Parameters - adjust these for your needs
SIDE_LENGTH = 80       # Length of triangle side (mm)
THICKNESS = 6          # Plate thickness (mm)
HOLE_DIAMETER = 6.5    # M6 clearance hole (use 5.3 for M5, 4.3 for M4)
HOLE_INSET = 15        # Distance from corner to hole center
CHAMFER_SIZE = 10      # Chamfer on triangle points
EDGE_FILLET = 1.5      # Fillet on top/bottom edges


def inset_point(vertex: tuple, inset: float, center: tuple = (0, 0)) -> tuple:
    """Move a point toward center by inset amount."""
    cx, cy = center
    vx, vy = vertex
    dx, dy = cx - vx, cy - vy
    length = math.sqrt(dx * dx + dy * dy)
    return (vx + dx / length * inset, vy + dy / length * inset)


def create_triangle_bracket(
    side_length: float = SIDE_LENGTH,
    thickness: float = THICKNESS,
    hole_diameter: float = HOLE_DIAMETER,
    hole_inset: float = HOLE_INSET,
    chamfer_size: float = CHAMFER_SIZE,
    edge_fillet: float = EDGE_FILLET
) -> cq.Workplane:
    """
    Create a triangular bracket with chamfered corners and bolt holes.

    Returns:
        CadQuery Workplane with the bracket geometry
    """
    # Calculate equilateral triangle vertices
    # Height of equilateral triangle: h = (sqrt(3)/2) * side
    height = (math.sqrt(3) / 2) * side_length

    # Vertices centered at origin: top, bottom-left, bottom-right
    top = (0, height * 2 / 3)
    bottom_left = (-side_length / 2, -height * 1 / 3)
    bottom_right = (side_length / 2, -height * 1 / 3)

    # Calculate hole positions (inset from corners toward center)
    hole_top = inset_point(top, hole_inset)
    hole_bl = inset_point(bottom_left, hole_inset)
    hole_br = inset_point(bottom_right, hole_inset)

    # Build the bracket
    result = (
        cq.Workplane("XY")
        # Create triangle profile
        .moveTo(*top)
        .lineTo(*bottom_right)
        .lineTo(*bottom_left)
        .close()
        .extrude(thickness)
        # Chamfer the vertical edges (triangle corners)
        .edges("|Z")
        .chamfer(chamfer_size)
        # Fillet top and bottom edges
        .edges(">Z or <Z")
        .fillet(edge_fillet)
        # Add bolt holes at each corner
        .faces(">Z")
        .workplane()
        .pushPoints([hole_top, hole_bl, hole_br])
        .hole(hole_diameter)
    )

    return result


# Create the bracket
result = create_triangle_bracket()

# Export if run directly
if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Export files
    step_path = output_dir / "triangle_bracket.step"
    stl_path = output_dir / "triangle_bracket.stl"

    cq.exporters.export(result, str(step_path))
    cq.exporters.export(result, str(stl_path))

    # Print info
    bb = result.val().BoundingBox()
    print(f"✅ Triangle Bracket Created!")
    print(f"   Side length: {SIDE_LENGTH} mm")
    print(f"   Thickness: {THICKNESS} mm")
    print(f"   Holes: 3x {HOLE_DIAMETER}mm diameter")
    print(f"   Corner chamfer: {CHAMFER_SIZE} mm")
    print(f"   Size: {bb.xmax - bb.xmin:.1f} x {bb.ymax - bb.ymin:.1f} x {bb.zmax - bb.zmin:.1f} mm")
    print(f"   Volume: {result.val().Volume():.1f} mm³")
    print(f"\n   Files:")
    print(f"   - {step_path}")
    print(f"   - {stl_path}")
    print(f"\n   View with: ./view output/triangle_bracket.stl")
