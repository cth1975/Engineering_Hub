#!/usr/bin/env python3
"""
Example: Simple L-Bracket

Demonstrates basic CadQuery parametric modeling for Engineering Hub.
This bracket mounts to a flat surface and holds a rod.

Parameters:
    - base_width: Width of the base plate
    - base_depth: Depth of the base plate
    - wall_height: Height of the vertical wall
    - thickness: Material thickness
    - hole_diameter: Mounting hole diameter
    - rod_diameter: Diameter of rod to hold
"""

import cadquery as cq

# Parametric dimensions (mm)
BASE_WIDTH = 40
BASE_DEPTH = 30
WALL_HEIGHT = 35
THICKNESS = 4
HOLE_DIAMETER = 5  # M5 clearance
ROD_DIAMETER = 10

# Create the L-bracket
result = (
    cq.Workplane("XY")
    # Base plate
    .box(BASE_WIDTH, BASE_DEPTH, THICKNESS)
    # Move to create vertical wall
    .faces(">Y")
    .workplane()
    .transformed(offset=(0, WALL_HEIGHT/2 - THICKNESS/2, 0))
    .box(BASE_WIDTH, WALL_HEIGHT, THICKNESS)
    # Add mounting holes to base
    .faces("<Z")
    .workplane()
    .rect(BASE_WIDTH - 10, BASE_DEPTH - 10, forConstruction=True)
    .vertices()
    .hole(HOLE_DIAMETER)
    # Add rod hole to vertical wall
    .faces(">Y")
    .workplane()
    .transformed(offset=(0, WALL_HEIGHT/2, 0))
    .hole(ROD_DIAMETER)
    # Fillet the L-joint for strength
    .edges("|Z")
    .edges(">Y")
    .fillet(THICKNESS * 0.8)
)

# Export if run directly
if __name__ == "__main__":
    from pathlib import Path
    from cadquery import exporters

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    exporters.export(result, str(output_dir / "simple_bracket.step"))
    exporters.export(result, str(output_dir / "simple_bracket.stl"))

    print(f"Exported to {output_dir}")
    print(f"Bounding box: {result.val().BoundingBox()}")
