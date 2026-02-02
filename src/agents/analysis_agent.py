#!/usr/bin/env python3
"""
Analysis Agent - Automated FEA/CFD Analysis

This agent automates structural and thermal analysis using open-source solvers:
- CalculiX for FEA (structural, thermal)
- Gmsh for meshing
- OpenFOAM for CFD (future)

Architecture:
    STEP File → Gmsh (mesh) → CalculiX (solve) → Results Interpretation

Usage:
    from src.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    result = agent.run_structural_analysis(
        step_file="bracket.step",
        loads=[{"node": "top", "force": [0, 0, -100]}],
        constraints=[{"face": "bottom", "type": "fixed"}],
        material="aluminum_6061"
    )
    print(result.max_stress)
    print(result.safety_factor)
"""

import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path
import re


@dataclass
class Material:
    """Material properties for FEA"""
    name: str
    elastic_modulus: float  # MPa
    poisson_ratio: float
    density: float  # kg/m³ (or tonnes/mm³ for mm units)
    yield_strength: float  # MPa
    thermal_conductivity: Optional[float] = None  # W/(m·K)
    specific_heat: Optional[float] = None  # J/(kg·K)


# Material library
MATERIALS = {
    "aluminum_6061": Material(
        name="Aluminum 6061-T6",
        elastic_modulus=68900,
        poisson_ratio=0.33,
        density=2.7e-9,  # tonnes/mm³
        yield_strength=276,
        thermal_conductivity=167,
        specific_heat=896
    ),
    "steel_304": Material(
        name="Stainless Steel 304",
        elastic_modulus=193000,
        poisson_ratio=0.29,
        density=8.0e-9,
        yield_strength=215,
        thermal_conductivity=16.2,
        specific_heat=500
    ),
    "pla": Material(
        name="PLA (3D Print)",
        elastic_modulus=3500,
        poisson_ratio=0.36,
        density=1.24e-9,
        yield_strength=50
    ),
    "petg": Material(
        name="PETG (3D Print)",
        elastic_modulus=2100,
        poisson_ratio=0.37,
        density=1.27e-9,
        yield_strength=28
    ),
    "abs": Material(
        name="ABS (3D Print)",
        elastic_modulus=2300,
        poisson_ratio=0.35,
        density=1.05e-9,
        yield_strength=40
    ),
    "nylon": Material(
        name="Nylon PA12",
        elastic_modulus=2700,
        poisson_ratio=0.40,
        density=1.15e-9,
        yield_strength=75
    ),
}


@dataclass
class AnalysisResult:
    """Result from FEA analysis"""
    success: bool
    analysis_type: str
    material: str
    max_stress: Optional[float] = None  # MPa (von Mises)
    max_displacement: Optional[float] = None  # mm
    safety_factor: Optional[float] = None
    status: str = "unknown"  # pass, warn, fail
    mesh_elements: int = 0
    mesh_nodes: int = 0
    solver_time: float = 0.0
    output_files: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    error: Optional[str] = None
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "analysis_type": self.analysis_type,
            "material": self.material,
            "max_stress": self.max_stress,
            "max_displacement": self.max_displacement,
            "safety_factor": self.safety_factor,
            "status": self.status,
            "mesh_elements": self.mesh_elements,
            "mesh_nodes": self.mesh_nodes,
            "solver_time": self.solver_time,
            "output_files": self.output_files,
            "details": self.details,
            "error": self.error,
            "recommendations": self.recommendations
        }


class AnalysisAgent:
    """
    Agent for automated FEA analysis.

    Handles:
    - Mesh generation (Gmsh)
    - Solver setup (CalculiX input files)
    - Running analysis
    - Results interpretation
    """

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        mesh_size: float = 2.0  # Default mesh element size in mm
    ):
        self.work_dir = Path(work_dir) if work_dir else Path("./output/analysis")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.mesh_size = mesh_size

    def get_material(self, name: str) -> Material:
        """Get material by name."""
        if name not in MATERIALS:
            raise ValueError(f"Unknown material: {name}. Available: {list(MATERIALS.keys())}")
        return MATERIALS[name]

    def list_materials(self) -> dict:
        """List available materials."""
        return {
            name: {
                "name": m.name,
                "E": m.elastic_modulus,
                "yield": m.yield_strength
            }
            for name, m in MATERIALS.items()
        }

    def generate_mesh(
        self,
        step_file: Path,
        output_file: Path,
        mesh_size: Optional[float] = None
    ) -> tuple[bool, dict]:
        """
        Generate FEA mesh from STEP file using Gmsh.

        Args:
            step_file: Input STEP geometry
            output_file: Output mesh file (.inp for CalculiX)
            mesh_size: Element size in mm

        Returns:
            Tuple of (success, info_dict)
        """
        size = mesh_size or self.mesh_size

        # Create Gmsh script
        geo_script = f"""
// Gmsh script for meshing
Merge "{step_file}";

// Set mesh size
Mesh.CharacteristicLengthMax = {size};
Mesh.CharacteristicLengthMin = {size / 4};

// Generate 3D mesh
Mesh 3;

// Optimize mesh quality
Mesh.Optimize = 1;
Mesh.OptimizeNetgen = 1;

// Save in CalculiX format
Save "{output_file}";
"""
        geo_file = self.work_dir / "mesh.geo"
        geo_file.write_text(geo_script)

        try:
            result = subprocess.run(
                ["gmsh", str(geo_file), "-3", "-o", str(output_file), "-format", "inp"],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                return False, {"error": result.stderr}

            # Parse mesh info from output
            nodes = 0
            elements = 0
            for line in result.stdout.split('\n'):
                if 'nodes' in line.lower():
                    match = re.search(r'(\d+)\s*nodes', line, re.I)
                    if match:
                        nodes = int(match.group(1))
                if 'elements' in line.lower():
                    match = re.search(r'(\d+)\s*elements', line, re.I)
                    if match:
                        elements = int(match.group(1))

            return True, {"nodes": nodes, "elements": elements}

        except FileNotFoundError:
            return False, {"error": "Gmsh not installed. Install with: apt install gmsh"}
        except subprocess.TimeoutExpired:
            return False, {"error": "Meshing timed out"}
        except Exception as e:
            return False, {"error": str(e)}

    def generate_calculix_input(
        self,
        mesh_file: Path,
        material: Material,
        loads: list[dict],
        constraints: list[dict],
        analysis_type: Literal["static", "thermal"] = "static"
    ) -> Path:
        """
        Generate CalculiX input file.

        Args:
            mesh_file: Path to mesh .inp file
            material: Material properties
            loads: List of load definitions
            constraints: List of boundary conditions
            analysis_type: Type of analysis

        Returns:
            Path to generated input file
        """
        inp_content = f"""** CalculiX Input File
** Generated by Engineering Hub Analysis Agent
**
*HEADING
{analysis_type.title()} Analysis

** Include mesh
*INCLUDE, INPUT={mesh_file.name}

** Material Definition: {material.name}
*MATERIAL, NAME=MAT1
*ELASTIC
{material.elastic_modulus}, {material.poisson_ratio}
*DENSITY
{material.density}

** Assign material to all elements
*SOLID SECTION, ELSET=EALL, MATERIAL=MAT1

** Boundary Conditions
"""
        # Add constraints
        for i, constraint in enumerate(constraints):
            ctype = constraint.get("type", "fixed")
            node_set = constraint.get("node_set", f"NFIX{i}")

            if ctype == "fixed":
                inp_content += f"*BOUNDARY\n{node_set}, 1, 3, 0\n"
            elif ctype == "pinned":
                inp_content += f"*BOUNDARY\n{node_set}, 1, 3, 0\n"

        # Add loads
        inp_content += "\n** Loads\n"
        for i, load in enumerate(loads):
            force = load.get("force", [0, 0, 0])
            node_set = load.get("node_set", f"NLOAD{i}")

            if force[0] != 0:
                inp_content += f"*CLOAD\n{node_set}, 1, {force[0]}\n"
            if force[1] != 0:
                inp_content += f"*CLOAD\n{node_set}, 2, {force[1]}\n"
            if force[2] != 0:
                inp_content += f"*CLOAD\n{node_set}, 3, {force[2]}\n"

        # Analysis step
        inp_content += f"""
** Analysis Step
*STEP
*STATIC

** Output requests
*NODE FILE
U
*EL FILE
S, E
*NODE PRINT, NSET=NALL
U
*EL PRINT, ELSET=EALL
S

*END STEP
"""

        inp_file = self.work_dir / "analysis.inp"
        inp_file.write_text(inp_content)
        return inp_file

    def run_calculix(self, inp_file: Path) -> tuple[bool, dict]:
        """
        Run CalculiX solver.

        Args:
            inp_file: Path to input file

        Returns:
            Tuple of (success, results_dict)
        """
        job_name = inp_file.stem

        try:
            import time
            start = time.time()

            result = subprocess.run(
                ["ccx", "-i", job_name],
                cwd=inp_file.parent,
                capture_output=True,
                text=True,
                timeout=600
            )

            elapsed = time.time() - start

            if result.returncode != 0:
                return False, {"error": result.stderr, "stdout": result.stdout}

            # Parse results from .dat file
            dat_file = inp_file.parent / f"{job_name}.dat"
            frd_file = inp_file.parent / f"{job_name}.frd"

            results = {
                "solver_time": elapsed,
                "output_files": []
            }

            if dat_file.exists():
                results["output_files"].append(str(dat_file))
                # Parse max stress and displacement
                dat_content = dat_file.read_text()

                # Look for stress values
                stress_match = re.search(r'maximum.*stress.*?([0-9.E+-]+)', dat_content, re.I)
                if stress_match:
                    results["max_stress"] = float(stress_match.group(1))

                # Look for displacement values
                disp_match = re.search(r'maximum.*displacement.*?([0-9.E+-]+)', dat_content, re.I)
                if disp_match:
                    results["max_displacement"] = float(disp_match.group(1))

            if frd_file.exists():
                results["output_files"].append(str(frd_file))

            return True, results

        except FileNotFoundError:
            return False, {"error": "CalculiX (ccx) not installed. Install with: apt install calculix-ccx"}
        except subprocess.TimeoutExpired:
            return False, {"error": "Analysis timed out (>10 min)"}
        except Exception as e:
            return False, {"error": str(e)}

    def interpret_results(
        self,
        max_stress: float,
        material: Material,
        max_displacement: Optional[float] = None,
        displacement_limit: float = 1.0  # mm
    ) -> tuple[str, float, list[str]]:
        """
        Interpret analysis results and generate recommendations.

        Args:
            max_stress: Maximum von Mises stress (MPa)
            material: Material used
            max_displacement: Maximum displacement (mm)
            displacement_limit: Acceptable displacement limit

        Returns:
            Tuple of (status, safety_factor, recommendations)
        """
        safety_factor = material.yield_strength / max_stress if max_stress > 0 else float('inf')
        recommendations = []

        # Determine status
        if safety_factor < 1.0:
            status = "FAIL"
            recommendations.append(f"CRITICAL: Part will yield! SF={safety_factor:.2f}")
            recommendations.append("Increase thickness or use stronger material")
        elif safety_factor < 1.5:
            status = "FAIL"
            recommendations.append(f"Insufficient safety factor: {safety_factor:.2f} (need >1.5)")
            recommendations.append("Consider increasing wall thickness by 50%")
        elif safety_factor < 2.0:
            status = "WARN"
            recommendations.append(f"Low safety factor: {safety_factor:.2f}")
            recommendations.append("Acceptable for non-critical applications only")
        elif safety_factor < 4.0:
            status = "PASS"
            recommendations.append(f"Good safety factor: {safety_factor:.2f}")
        else:
            status = "PASS"
            recommendations.append(f"High safety factor: {safety_factor:.2f}")
            recommendations.append("Consider optimizing to reduce material/weight")

        # Check displacement
        if max_displacement and max_displacement > displacement_limit:
            if status == "PASS":
                status = "WARN"
            recommendations.append(f"Displacement {max_displacement:.2f}mm exceeds limit {displacement_limit}mm")
            recommendations.append("Increase stiffness (thicker sections or gussets)")

        return status, safety_factor, recommendations

    def run_structural_analysis(
        self,
        step_file: str | Path,
        material: str = "aluminum_6061",
        loads: list[dict] = None,
        constraints: list[dict] = None,
        mesh_size: Optional[float] = None
    ) -> AnalysisResult:
        """
        Run complete structural analysis pipeline.

        This is the main entry point for the Analysis Agent.

        Args:
            step_file: Path to STEP geometry file
            material: Material name from library
            loads: Load definitions [{"node_set": "TOP", "force": [0, 0, -100]}]
            constraints: Constraints [{"node_set": "BOTTOM", "type": "fixed"}]
            mesh_size: Mesh element size (mm)

        Returns:
            AnalysisResult with stress, displacement, safety factor
        """
        step_file = Path(step_file)
        loads = loads or [{"node_set": "NLOAD", "force": [0, 0, -100]}]
        constraints = constraints or [{"node_set": "NFIX", "type": "fixed"}]

        # Get material
        try:
            mat = self.get_material(material)
        except ValueError as e:
            return AnalysisResult(
                success=False,
                analysis_type="structural",
                material=material,
                error=str(e)
            )

        # Generate mesh
        mesh_file = self.work_dir / "mesh.inp"
        mesh_success, mesh_info = self.generate_mesh(step_file, mesh_file, mesh_size)

        if not mesh_success:
            return AnalysisResult(
                success=False,
                analysis_type="structural",
                material=material,
                error=f"Meshing failed: {mesh_info.get('error')}"
            )

        # Generate CalculiX input
        inp_file = self.generate_calculix_input(
            mesh_file, mat, loads, constraints, "static"
        )

        # Run solver
        solve_success, solve_results = self.run_calculix(inp_file)

        if not solve_success:
            return AnalysisResult(
                success=False,
                analysis_type="structural",
                material=material,
                mesh_elements=mesh_info.get("elements", 0),
                mesh_nodes=mesh_info.get("nodes", 0),
                error=f"Solver failed: {solve_results.get('error')}"
            )

        # Interpret results
        max_stress = solve_results.get("max_stress", 0)
        max_disp = solve_results.get("max_displacement", 0)

        status, sf, recommendations = self.interpret_results(max_stress, mat, max_disp)

        return AnalysisResult(
            success=True,
            analysis_type="structural",
            material=mat.name,
            max_stress=max_stress,
            max_displacement=max_disp,
            safety_factor=sf,
            status=status,
            mesh_elements=mesh_info.get("elements", 0),
            mesh_nodes=mesh_info.get("nodes", 0),
            solver_time=solve_results.get("solver_time", 0),
            output_files=solve_results.get("output_files", []),
            recommendations=recommendations
        )


def main():
    """CLI interface for Analysis Agent."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Analysis Agent - FEA Automation")

    parser.add_argument("step_file", nargs="?", help="STEP file to analyze")
    parser.add_argument("--material", "-m", default="aluminum_6061", help="Material name")
    parser.add_argument("--mesh-size", type=float, default=2.0, help="Mesh element size (mm)")
    parser.add_argument("--force", "-f", type=float, default=-100, help="Force in Z direction (N)")
    parser.add_argument("--list-materials", action="store_true", help="List available materials")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    agent = AnalysisAgent()

    if args.list_materials:
        materials = agent.list_materials()
        if args.json:
            print(json.dumps(materials, indent=2))
        else:
            print("Available Materials:\n")
            for name, info in materials.items():
                print(f"  {name}: {info['name']}")
                print(f"    E = {info['E']} MPa, Yield = {info['yield']} MPa\n")
        return 0

    if not args.step_file:
        parser.error("STEP file required (or use --list-materials)")

    result = agent.run_structural_analysis(
        args.step_file,
        material=args.material,
        loads=[{"node_set": "NLOAD", "force": [0, 0, args.force]}],
        mesh_size=args.mesh_size
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\nAnalysis Result: {result.status}")
        print(f"{'='*40}")
        print(f"Material: {result.material}")
        print(f"Mesh: {result.mesh_nodes} nodes, {result.mesh_elements} elements")
        print(f"Max Stress: {result.max_stress:.2f} MPa" if result.max_stress else "Max Stress: N/A")
        print(f"Max Displacement: {result.max_displacement:.3f} mm" if result.max_displacement else "Max Displacement: N/A")
        print(f"Safety Factor: {result.safety_factor:.2f}" if result.safety_factor else "Safety Factor: N/A")
        print(f"\nRecommendations:")
        for rec in result.recommendations:
            print(f"  - {rec}")

        if result.error:
            print(f"\nError: {result.error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
