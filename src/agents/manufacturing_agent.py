#!/usr/bin/env python3
"""
Manufacturing Agent - CAM and Manufacturing Output Generation

This agent generates manufacturing-ready outputs:
- G-code for 3D printing (via PrusaSlicer)
- G-code for CNC milling (via FreeCAD Path)
- DXF/SVG for laser cutting

Usage:
    from src.agents.manufacturing_agent import ManufacturingAgent

    agent = ManufacturingAgent()

    # 3D printing
    result = agent.slice_for_printing("part.stl", profile="functional")

    # Laser cutting
    result = agent.generate_laser_dxf("part.step", thickness=3.0)
"""

import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path
import json


@dataclass
class PrintProfile:
    """3D printing profile settings"""
    name: str
    layer_height: float
    infill_percent: int
    perimeters: int
    top_layers: int
    bottom_layers: int
    supports: bool = False
    brim: bool = False
    description: str = ""


# Print profiles
PRINT_PROFILES = {
    "draft": PrintProfile(
        name="Draft",
        layer_height=0.3,
        infill_percent=15,
        perimeters=2,
        top_layers=3,
        bottom_layers=3,
        description="Fast printing, lower quality"
    ),
    "standard": PrintProfile(
        name="Standard",
        layer_height=0.2,
        infill_percent=20,
        perimeters=3,
        top_layers=4,
        bottom_layers=4,
        description="Balanced speed and quality"
    ),
    "functional": PrintProfile(
        name="Functional",
        layer_height=0.2,
        infill_percent=40,
        perimeters=4,
        top_layers=5,
        bottom_layers=5,
        description="Strong parts for mechanical use"
    ),
    "strong": PrintProfile(
        name="Strong",
        layer_height=0.2,
        infill_percent=60,
        perimeters=5,
        top_layers=6,
        bottom_layers=6,
        description="Maximum strength"
    ),
    "fine": PrintProfile(
        name="Fine",
        layer_height=0.1,
        infill_percent=20,
        perimeters=3,
        top_layers=6,
        bottom_layers=6,
        description="High detail, slower print"
    ),
}


@dataclass
class MaterialSettings:
    """Material-specific print settings"""
    name: str
    nozzle_temp: int
    bed_temp: int
    cooling: bool = True
    enclosure: bool = False
    notes: str = ""


MATERIALS = {
    "pla": MaterialSettings("PLA", 210, 60, cooling=True, notes="Easy to print"),
    "petg": MaterialSettings("PETG", 240, 80, cooling=True, notes="Good strength, slight stringing"),
    "abs": MaterialSettings("ABS", 250, 100, cooling=False, enclosure=True, notes="Needs enclosure, warps easily"),
    "tpu": MaterialSettings("TPU", 230, 50, cooling=False, notes="Flexible, print slow"),
    "asa": MaterialSettings("ASA", 260, 100, cooling=False, enclosure=True, notes="UV resistant, like ABS"),
}


@dataclass
class ManufacturingResult:
    """Result from manufacturing operation"""
    success: bool
    method: str  # 3d_print, laser, cnc
    output_file: Optional[str] = None
    print_time: Optional[float] = None  # minutes
    filament_used: Optional[float] = None  # grams or meters
    layers: Optional[int] = None
    cut_length: Optional[float] = None  # mm for laser
    details: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "method": self.method,
            "output_file": self.output_file,
            "print_time": self.print_time,
            "filament_used": self.filament_used,
            "layers": self.layers,
            "cut_length": self.cut_length,
            "details": self.details,
            "warnings": self.warnings,
            "error": self.error
        }


class ManufacturingAgent:
    """
    Agent for generating manufacturing outputs.

    Supports:
    - 3D printing (FDM via PrusaSlicer CLI)
    - Laser cutting (DXF/SVG from 2D profiles)
    - CNC milling (G-code via FreeCAD Path) - future
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir) if output_dir else Path("./output")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> dict:
        """List available print profiles."""
        return {
            name: {
                "name": p.name,
                "layer_height": p.layer_height,
                "infill": p.infill_percent,
                "description": p.description
            }
            for name, p in PRINT_PROFILES.items()
        }

    def list_materials(self) -> dict:
        """List available materials with settings."""
        return {
            name: {
                "name": m.name,
                "nozzle": m.nozzle_temp,
                "bed": m.bed_temp,
                "notes": m.notes
            }
            for name, m in MATERIALS.items()
        }

    def slice_for_printing(
        self,
        stl_file: str | Path,
        profile: str = "standard",
        material: str = "pla",
        output_name: Optional[str] = None,
        supports: bool = False,
        brim: bool = False,
        custom_settings: Optional[dict] = None
    ) -> ManufacturingResult:
        """
        Slice STL for 3D printing using PrusaSlicer CLI.

        Args:
            stl_file: Input STL file
            profile: Print profile (draft, standard, functional, strong, fine)
            material: Material (pla, petg, abs, tpu, asa)
            output_name: Output G-code filename
            supports: Enable support generation
            brim: Enable brim for bed adhesion
            custom_settings: Override specific settings

        Returns:
            ManufacturingResult with G-code path and print info
        """
        stl_file = Path(stl_file)

        if not stl_file.exists():
            return ManufacturingResult(
                success=False,
                method="3d_print",
                error=f"STL file not found: {stl_file}"
            )

        # Get profile and material
        if profile not in PRINT_PROFILES:
            return ManufacturingResult(
                success=False,
                method="3d_print",
                error=f"Unknown profile: {profile}. Available: {list(PRINT_PROFILES.keys())}"
            )

        if material not in MATERIALS:
            return ManufacturingResult(
                success=False,
                method="3d_print",
                error=f"Unknown material: {material}. Available: {list(MATERIALS.keys())}"
            )

        prof = PRINT_PROFILES[profile]
        mat = MATERIALS[material]

        # Build output path
        if not output_name:
            output_name = stl_file.stem

        output_file = self.output_dir / f"{output_name}.gcode"

        # Build PrusaSlicer command
        cmd = [
            "prusa-slicer",
            "--export-gcode",
            f"--layer-height={prof.layer_height}",
            f"--fill-density={prof.infill_percent}%",
            f"--perimeters={prof.perimeters}",
            f"--top-solid-layers={prof.top_layers}",
            f"--bottom-solid-layers={prof.bottom_layers}",
            f"--nozzle-diameter=0.4",
            f"--filament-type={mat.name}",
            f"--temperature={mat.nozzle_temp}",
            f"--bed-temperature={mat.bed_temp}",
        ]

        if supports or prof.supports:
            cmd.append("--support-material")

        if brim or prof.brim:
            cmd.append("--brim-width=5")

        if not mat.cooling:
            cmd.append("--cooling=0")

        # Apply custom settings
        if custom_settings:
            for key, value in custom_settings.items():
                cmd.append(f"--{key}={value}")

        cmd.extend([
            f"--output={output_file}",
            str(stl_file)
        ])

        warnings = []

        # Add warnings
        if mat.enclosure:
            warnings.append(f"{mat.name} requires an enclosed printer")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                # PrusaSlicer might not be installed, try alternative
                return ManufacturingResult(
                    success=False,
                    method="3d_print",
                    error=f"PrusaSlicer failed: {result.stderr}",
                    details={"command": " ".join(cmd)}
                )

            # Parse output for stats
            print_time = None
            filament = None
            layers = None

            for line in result.stdout.split('\n'):
                if 'print time' in line.lower():
                    # Parse print time
                    pass
                if 'filament' in line.lower():
                    # Parse filament usage
                    pass

            return ManufacturingResult(
                success=True,
                method="3d_print",
                output_file=str(output_file),
                print_time=print_time,
                filament_used=filament,
                layers=layers,
                details={
                    "profile": profile,
                    "material": material,
                    "layer_height": prof.layer_height,
                    "infill": prof.infill_percent
                },
                warnings=warnings
            )

        except FileNotFoundError:
            # PrusaSlicer not installed - generate placeholder info
            return ManufacturingResult(
                success=False,
                method="3d_print",
                error="PrusaSlicer not installed. Install from: https://github.com/prusa3d/PrusaSlicer",
                details={
                    "profile": profile,
                    "material": material,
                    "settings": {
                        "layer_height": prof.layer_height,
                        "infill": prof.infill_percent,
                        "nozzle_temp": mat.nozzle_temp,
                        "bed_temp": mat.bed_temp
                    }
                }
            )
        except subprocess.TimeoutExpired:
            return ManufacturingResult(
                success=False,
                method="3d_print",
                error="Slicing timed out (>5 min)"
            )

    def generate_laser_dxf(
        self,
        step_file: str | Path,
        output_name: Optional[str] = None,
        thickness: float = 3.0,
        kerf: float = 0.2
    ) -> ManufacturingResult:
        """
        Generate DXF profile for laser cutting.

        Extracts 2D profile from STEP file for laser/waterjet cutting.

        Args:
            step_file: Input STEP file
            output_name: Output DXF filename
            thickness: Material thickness (mm) - used for validation
            kerf: Laser kerf width (mm) for compensation

        Returns:
            ManufacturingResult with DXF path
        """
        step_file = Path(step_file)

        if not output_name:
            output_name = step_file.stem

        output_file = self.output_dir / f"{output_name}.dxf"
        svg_file = self.output_dir / f"{output_name}.svg"

        try:
            import cadquery as cq
            from cadquery import exporters

            # Load STEP and get top face profile
            model = cq.importers.importStep(str(step_file))

            # Get the largest face as the cutting profile
            faces = model.faces().vals()
            largest_face = max(faces, key=lambda f: f.Area())

            # Create a workplane from that face and get outer wire
            profile = cq.Workplane(largest_face).wires().toPending()

            # Export to DXF and SVG
            exporters.exportDXF(profile, str(output_file))
            exporters.exportSVG(profile, str(svg_file))

            # Calculate cut length
            cut_length = sum(e.Length() for e in profile.edges().vals())

            return ManufacturingResult(
                success=True,
                method="laser",
                output_file=str(output_file),
                cut_length=cut_length,
                details={
                    "thickness": thickness,
                    "kerf": kerf,
                    "svg_file": str(svg_file),
                    "note": f"Apply {kerf}mm kerf compensation in laser software"
                },
                warnings=[f"Verify material thickness matches design ({thickness}mm)"]
            )

        except ImportError:
            return ManufacturingResult(
                success=False,
                method="laser",
                error="CadQuery not installed. Run: pip install cadquery"
            )
        except Exception as e:
            return ManufacturingResult(
                success=False,
                method="laser",
                error=f"DXF generation failed: {e}"
            )

    def generate_cnc_gcode(
        self,
        step_file: str | Path,
        operation: Literal["profile", "pocket", "drill"] = "profile",
        tool_diameter: float = 6.0,
        depth: float = 5.0,
        stepdown: float = 1.0,
        feedrate: float = 500,
        output_name: Optional[str] = None
    ) -> ManufacturingResult:
        """
        Generate CNC G-code (placeholder - full implementation requires FreeCAD).

        Args:
            step_file: Input STEP file
            operation: CNC operation type
            tool_diameter: End mill diameter (mm)
            depth: Total cutting depth (mm)
            stepdown: Depth per pass (mm)
            feedrate: Feed rate (mm/min)
            output_name: Output filename

        Returns:
            ManufacturingResult (currently placeholder)
        """
        # This is a placeholder - full implementation would use FreeCAD Path workbench
        return ManufacturingResult(
            success=False,
            method="cnc",
            error="CNC G-code generation not yet implemented. Planned for Phase 4.",
            details={
                "operation": operation,
                "tool_diameter": tool_diameter,
                "depth": depth,
                "stepdown": stepdown,
                "feedrate": feedrate,
                "note": "Will use FreeCAD Path workbench"
            }
        )

    def validate_gcode(self, gcode_file: str | Path) -> dict:
        """
        Basic G-code validation.

        Args:
            gcode_file: Path to G-code file

        Returns:
            Validation results dict
        """
        gcode_file = Path(gcode_file)

        if not gcode_file.exists():
            return {"valid": False, "error": "File not found"}

        content = gcode_file.read_text()
        lines = content.split('\n')

        issues = []
        stats = {
            "total_lines": len(lines),
            "g_codes": 0,
            "m_codes": 0,
            "comments": 0,
            "travel_moves": 0,
            "print_moves": 0
        }

        for i, line in enumerate(lines):
            line = line.strip()

            if not line:
                continue

            if line.startswith(';'):
                stats["comments"] += 1
                continue

            if line.startswith('G'):
                stats["g_codes"] += 1

                if 'G0' in line:
                    stats["travel_moves"] += 1
                elif 'G1' in line:
                    stats["print_moves"] += 1

            if line.startswith('M'):
                stats["m_codes"] += 1

            # Check for common issues
            if 'G28' in line and i > 10:
                issues.append(f"Line {i+1}: G28 (home) found mid-file")

        return {
            "valid": len(issues) == 0,
            "stats": stats,
            "issues": issues
        }


def main():
    """CLI interface for Manufacturing Agent."""
    import argparse

    parser = argparse.ArgumentParser(description="Manufacturing Agent - CAM Output Generation")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Slice command
    slice_parser = subparsers.add_parser("slice", help="Slice STL for 3D printing")
    slice_parser.add_argument("stl_file", help="Input STL file")
    slice_parser.add_argument("--profile", "-p", default="standard",
                              choices=list(PRINT_PROFILES.keys()))
    slice_parser.add_argument("--material", "-m", default="pla",
                              choices=list(MATERIALS.keys()))
    slice_parser.add_argument("--output", "-o", help="Output filename")
    slice_parser.add_argument("--supports", action="store_true")
    slice_parser.add_argument("--brim", action="store_true")

    # Laser command
    laser_parser = subparsers.add_parser("laser", help="Generate DXF for laser cutting")
    laser_parser.add_argument("step_file", help="Input STEP file")
    laser_parser.add_argument("--thickness", "-t", type=float, default=3.0)
    laser_parser.add_argument("--output", "-o", help="Output filename")

    # List command
    list_parser = subparsers.add_parser("list", help="List profiles/materials")
    list_parser.add_argument("what", choices=["profiles", "materials"])

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate G-code")
    validate_parser.add_argument("gcode_file", help="G-code file to validate")

    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    agent = ManufacturingAgent()

    if args.command == "list":
        if args.what == "profiles":
            data = agent.list_profiles()
        else:
            data = agent.list_materials()

        if args.json:
            print(json.dumps(data, indent=2))
        else:
            for name, info in data.items():
                print(f"{name}: {info}")
        return 0

    elif args.command == "slice":
        result = agent.slice_for_printing(
            args.stl_file,
            profile=args.profile,
            material=args.material,
            output_name=args.output,
            supports=args.supports,
            brim=args.brim
        )

    elif args.command == "laser":
        result = agent.generate_laser_dxf(
            args.step_file,
            output_name=args.output,
            thickness=args.thickness
        )

    elif args.command == "validate":
        validation = agent.validate_gcode(args.gcode_file)
        if args.json:
            print(json.dumps(validation, indent=2))
        else:
            print(f"Valid: {validation['valid']}")
            print(f"Stats: {validation['stats']}")
            if validation['issues']:
                print("Issues:")
                for issue in validation['issues']:
                    print(f"  - {issue}")
        return 0 if validation['valid'] else 1

    else:
        parser.print_help()
        return 1

    # Output result
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Success: {result.success}")
        print(f"Method: {result.method}")
        if result.output_file:
            print(f"Output: {result.output_file}")
        if result.print_time:
            print(f"Print time: {result.print_time:.0f} min")
        if result.cut_length:
            print(f"Cut length: {result.cut_length:.1f} mm")
        if result.warnings:
            print("Warnings:")
            for w in result.warnings:
                print(f"  - {w}")
        if result.error:
            print(f"Error: {result.error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
