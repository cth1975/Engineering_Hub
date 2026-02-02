#!/usr/bin/env python3
"""
CadQuery Wrapper - Text-to-CAD generation tool

This wrapper enables AI agents to generate parametric CAD models from
Python/CadQuery code and export to various formats.

Usage:
    # As module
    from src.tools.cadquery_wrapper import CadQueryWrapper
    wrapper = CadQueryWrapper()
    result = wrapper.execute_code(cadquery_code)
    wrapper.export(result, "output.step", format="STEP")

    # As CLI
    python cadquery_wrapper.py "Create a 50mm cube" --output cube.step
"""

import sys
import json
import tempfile
from pathlib import Path
from typing import Optional, Union, Literal
from dataclasses import dataclass, asdict

# Check if running inside container or has CadQuery
try:
    import cadquery as cq
    from cadquery import exporters
    CADQUERY_AVAILABLE = True
except ImportError:
    CADQUERY_AVAILABLE = False
    cq = None


@dataclass
class CADResult:
    """Result from CAD generation"""
    success: bool
    message: str
    code: str
    output_file: Optional[str] = None
    format: Optional[str] = None
    bounding_box: Optional[dict] = None
    volume: Optional[float] = None
    surface_area: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


ExportFormat = Literal["STEP", "STL", "DXF", "SVG", "AMF", "VRML", "VTP", "JSON"]


class CadQueryWrapper:
    """
    Wrapper for CadQuery CAD operations.

    Designed for AI agent interaction:
    - Execute CadQuery Python code
    - Export to multiple formats
    - Return structured results with metadata
    """

    SUPPORTED_FORMATS = {
        "STEP": {"ext": ".step", "description": "Standard CAD exchange format"},
        "STL": {"ext": ".stl", "description": "3D printing mesh format"},
        "DXF": {"ext": ".dxf", "description": "2D drawing exchange format"},
        "SVG": {"ext": ".svg", "description": "2D vector graphics"},
        "AMF": {"ext": ".amf", "description": "Additive manufacturing format"},
        "VRML": {"ext": ".wrl", "description": "Virtual reality modeling"},
        "VTP": {"ext": ".vtp", "description": "VTK polygon data"},
        "JSON": {"ext": ".json", "description": "CadQuery JSON format"},
    }

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize CadQuery wrapper.

        Args:
            output_dir: Directory for output files. Defaults to ./output
        """
        if not CADQUERY_AVAILABLE:
            raise RuntimeError(
                "CadQuery not installed. Install with: pip install cadquery-ocp cadquery"
            )

        self.output_dir = Path(output_dir) if output_dir else Path("./output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._last_result = None

    def execute_code(self, code: str, result_var: str = "result") -> Union[cq.Workplane, None]:
        """
        Execute CadQuery code and return the result.

        Args:
            code: CadQuery Python code to execute
            result_var: Name of the variable containing the result

        Returns:
            CadQuery Workplane object or None on error
        """
        # Create execution namespace with CadQuery available
        namespace = {
            "cq": cq,
            "cadquery": cq,
            "Workplane": cq.Workplane,
            "Vector": cq.Vector,
            "Assembly": cq.Assembly,
        }

        try:
            exec(code, namespace)
            self._last_result = namespace.get(result_var)
            return self._last_result
        except Exception as e:
            raise RuntimeError(f"Code execution failed: {e}")

    def export(
        self,
        workplane: cq.Workplane,
        filename: str,
        format: ExportFormat = "STEP",
        **export_options
    ) -> Path:
        """
        Export CadQuery object to file.

        Args:
            workplane: CadQuery Workplane to export
            filename: Output filename (extension added if missing)
            format: Export format (STEP, STL, DXF, etc.)
            **export_options: Additional options passed to exporter

        Returns:
            Path to exported file
        """
        format = format.upper()
        if format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {format}. Use: {list(self.SUPPORTED_FORMATS.keys())}")

        # Ensure correct extension
        ext = self.SUPPORTED_FORMATS[format]["ext"]
        filepath = self.output_dir / filename
        if filepath.suffix.lower() != ext:
            filepath = filepath.with_suffix(ext)

        # Export based on format
        if format == "STEP":
            exporters.export(workplane, str(filepath), exportType="STEP")
        elif format == "STL":
            exporters.export(workplane, str(filepath), exportType="STL", **export_options)
        elif format == "DXF":
            exporters.exportDXF(workplane, str(filepath), **export_options)
        elif format == "SVG":
            exporters.exportSVG(workplane, str(filepath), **export_options)
        elif format == "AMF":
            exporters.export(workplane, str(filepath), exportType="AMF")
        elif format == "VRML":
            exporters.export(workplane, str(filepath), exportType="VRML")
        elif format == "VTP":
            exporters.export(workplane, str(filepath), exportType="VTP")
        elif format == "JSON":
            exporters.export(workplane, str(filepath), exportType="TJS")

        return filepath

    def get_properties(self, workplane: cq.Workplane) -> dict:
        """
        Get geometric properties of a CadQuery object.

        Returns:
            Dictionary with bounding_box, volume, surface_area
        """
        try:
            bb = workplane.val().BoundingBox()
            bounding_box = {
                "min": {"x": bb.xmin, "y": bb.ymin, "z": bb.zmin},
                "max": {"x": bb.xmax, "y": bb.ymax, "z": bb.zmax},
                "size": {
                    "x": bb.xmax - bb.xmin,
                    "y": bb.ymax - bb.ymin,
                    "z": bb.zmax - bb.zmin
                }
            }
        except:
            bounding_box = None

        try:
            volume = workplane.val().Volume()
        except:
            volume = None

        try:
            # Surface area calculation
            surface_area = sum(f.Area() for f in workplane.val().Faces())
        except:
            surface_area = None

        return {
            "bounding_box": bounding_box,
            "volume": volume,
            "surface_area": surface_area
        }

    def generate(
        self,
        code: str,
        output_name: str,
        formats: list[ExportFormat] = ["STEP", "STL"],
        result_var: str = "result"
    ) -> CADResult:
        """
        Full generation pipeline: execute code, export to formats, return result.

        This is the primary method for AI agent interaction.

        Args:
            code: CadQuery Python code
            output_name: Base name for output files (without extension)
            formats: List of export formats
            result_var: Variable name containing the result in the code

        Returns:
            CADResult with success status, file paths, and geometry metadata
        """
        try:
            # Execute the code
            workplane = self.execute_code(code, result_var)

            if workplane is None:
                return CADResult(
                    success=False,
                    message=f"No result found in variable '{result_var}'",
                    code=code,
                    error=f"Variable '{result_var}' is None or not defined"
                )

            # Export to all requested formats
            output_files = []
            for fmt in formats:
                try:
                    filepath = self.export(workplane, output_name, format=fmt)
                    output_files.append(str(filepath))
                except Exception as e:
                    output_files.append(f"ERROR ({fmt}): {e}")

            # Get geometry properties
            props = self.get_properties(workplane)

            return CADResult(
                success=True,
                message=f"Successfully generated {len(output_files)} output files",
                code=code,
                output_file=output_files[0] if output_files else None,
                format=formats[0] if formats else None,
                bounding_box=props.get("bounding_box"),
                volume=props.get("volume"),
                surface_area=props.get("surface_area")
            )

        except Exception as e:
            return CADResult(
                success=False,
                message=f"Generation failed: {e}",
                code=code,
                error=str(e)
            )


# Example parametric models for reference
EXAMPLE_MODELS = {
    "cube": '''
# Simple cube
result = cq.Workplane("XY").box(50, 50, 50)
''',

    "rounded_cube": '''
# Cube with rounded edges
result = (
    cq.Workplane("XY")
    .box(50, 50, 50)
    .edges()
    .fillet(5)
)
''',

    "nema17_bracket": '''
# NEMA 17 motor mount bracket
NEMA17_SIZE = 42.3
NEMA17_HOLE_SPACING = 31
NEMA17_CENTER_HOLE = 22
MOUNT_THICKNESS = 5
M3_CLEARANCE = 3.2

result = (
    cq.Workplane("XY")
    .box(NEMA17_SIZE, NEMA17_SIZE, MOUNT_THICKNESS)
    .faces(">Z")
    .workplane()
    .rect(NEMA17_HOLE_SPACING, NEMA17_HOLE_SPACING, forConstruction=True)
    .vertices()
    .hole(M3_CLEARANCE)
    .faces(">Z")
    .workplane()
    .hole(NEMA17_CENTER_HOLE)
)
''',

    "enclosure": '''
# Simple electronics enclosure
WIDTH = 100
DEPTH = 60
HEIGHT = 40
WALL = 2

# Outer shell
outer = cq.Workplane("XY").box(WIDTH, DEPTH, HEIGHT)

# Inner cavity (shell operation)
result = outer.faces(">Z").shell(-WALL)
''',
}


def main():
    """CLI interface for CadQuery wrapper"""
    import argparse

    parser = argparse.ArgumentParser(
        description="CadQuery Wrapper - Generate CAD from code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run example model
  python cadquery_wrapper.py --example cube --output my_cube

  # Execute code from file
  python cadquery_wrapper.py --file model.py --output my_model

  # Execute inline code
  python cadquery_wrapper.py --code "result = cq.Workplane('XY').box(10,10,10)"
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--example", choices=list(EXAMPLE_MODELS.keys()),
                       help="Run a built-in example model")
    group.add_argument("--file", type=Path, help="Execute code from file")
    group.add_argument("--code", type=str, help="Execute inline CadQuery code")
    group.add_argument("--list-examples", action="store_true",
                       help="List available example models")

    parser.add_argument("--output", "-o", default="output",
                        help="Output filename (without extension)")
    parser.add_argument("--formats", "-f", nargs="+", default=["STEP", "STL"],
                        choices=list(CadQueryWrapper.SUPPORTED_FORMATS.keys()),
                        help="Export formats")
    parser.add_argument("--output-dir", type=Path, default=Path("./output"),
                        help="Output directory")
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON")

    args = parser.parse_args()

    if args.list_examples:
        print("Available example models:")
        for name, code in EXAMPLE_MODELS.items():
            print(f"\n=== {name} ===")
            print(code)
        return 0

    # Determine code to execute
    if args.example:
        code = EXAMPLE_MODELS[args.example]
    elif args.file:
        code = args.file.read_text()
    else:
        code = args.code

    try:
        wrapper = CadQueryWrapper(output_dir=args.output_dir)
        result = wrapper.generate(
            code=code,
            output_name=args.output,
            formats=args.formats
        )

        if args.json:
            print(result.to_json())
        else:
            print(f"Success: {result.success}")
            print(f"Message: {result.message}")
            if result.output_file:
                print(f"Output: {result.output_file}")
            if result.bounding_box:
                size = result.bounding_box.get("size", {})
                print(f"Size: {size.get('x', 0):.2f} x {size.get('y', 0):.2f} x {size.get('z', 0):.2f} mm")
            if result.volume:
                print(f"Volume: {result.volume:.2f} mm³")
            if result.error:
                print(f"Error: {result.error}")

        return 0 if result.success else 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
