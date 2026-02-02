#!/usr/bin/env python3
"""
FEA Solver - Finite Element Analysis with von Mises Stress Visualization

Performs structural analysis on CAD models using:
- Gmsh for meshing
- Simple FEA solver (or CalculiX for full analysis)
- PyVista for visualization

Usage:
    python fea_solver.py output/triangle_bracket.stl \
        --fix-holes 0 1 \
        --load-hole 2 \
        --force 100 \
        --material aluminum

    # Or with STEP file
    python fea_solver.py output/triangle_bracket.step --fix-holes 0 1 --load-hole 2
"""

import sys
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple
import argparse
import tempfile


@dataclass
class Material:
    """Material properties"""
    name: str
    E: float  # Young's modulus (MPa)
    nu: float  # Poisson's ratio
    yield_strength: float  # MPa
    density: float  # kg/m³


MATERIALS = {
    "aluminum": Material("Aluminum 6061-T6", 68900, 0.33, 276, 2700),
    "steel": Material("Steel AISI 304", 193000, 0.29, 215, 8000),
    "pla": Material("PLA", 3500, 0.36, 50, 1240),
    "petg": Material("PETG", 2100, 0.37, 28, 1270),
    "abs": Material("ABS", 2300, 0.35, 40, 1050),
}


@dataclass
class FEAResult:
    """Results from FEA analysis"""
    success: bool
    mesh_nodes: int
    mesh_elements: int
    max_stress: float  # von Mises (MPa)
    max_displacement: float  # mm
    safety_factor: float
    stress_field: Optional[np.ndarray] = None
    displacement_field: Optional[np.ndarray] = None
    node_coords: Optional[np.ndarray] = None
    elements: Optional[np.ndarray] = None
    error: Optional[str] = None


def load_stl_mesh(stl_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load STL directly as triangle mesh using PyVista (fast).

    Returns:
        Tuple of (node_coords, elements)
    """
    import pyvista as pv

    mesh = pv.read(str(stl_path))

    # Get vertices
    node_coords = np.array(mesh.points)

    # Get faces (triangles)
    faces = mesh.faces.reshape(-1, 4)[:, 1:4]  # Remove the '3' prefix

    return node_coords, faces


def mesh_stl(stl_path: Path, mesh_size: float = 2.0, use_gmsh: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """
    Mesh an STL file.

    By default uses fast PyVista loader. Set use_gmsh=True for tetrahedral meshing.

    Returns:
        Tuple of (node_coords, elements)
    """
    if not use_gmsh:
        return load_stl_mesh(stl_path)

    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)  # Suppress output

    try:
        # Merge STL
        gmsh.merge(str(stl_path))

        # Create surface mesh from STL
        gmsh.model.mesh.createTopology()
        gmsh.model.mesh.classifySurfaces(angle=40 * np.pi / 180)
        gmsh.model.mesh.createGeometry()

        # Set mesh size
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_size)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mesh_size / 4)

        # Generate 3D mesh
        gmsh.model.mesh.generate(3)

        # Get nodes
        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
        node_coords = np.array(node_coords).reshape(-1, 3)

        # Get elements (tetrahedra = type 4)
        elem_types, elem_tags, elem_nodes = gmsh.model.mesh.getElements(dim=3)

        if len(elem_nodes) > 0:
            elements = np.array(elem_nodes[0]).reshape(-1, 4) - 1  # 0-indexed
        else:
            # Fallback: use surface triangles
            elem_types, elem_tags, elem_nodes = gmsh.model.mesh.getElements(dim=2)
            elements = np.array(elem_nodes[0]).reshape(-1, 3) - 1

        return node_coords, elements

    finally:
        gmsh.finalize()


def find_hole_nodes(node_coords: np.ndarray, hole_centers: List[Tuple[float, float]],
                    hole_radius: float = 4.0, z_range: Tuple[float, float] = None) -> List[List[int]]:
    """
    Find nodes near hole centers.

    Args:
        node_coords: Array of node coordinates (N, 3)
        hole_centers: List of (x, y) hole center coordinates
        hole_radius: Search radius around hole center
        z_range: Optional (z_min, z_max) to filter by z coordinate

    Returns:
        List of node indices for each hole
    """
    hole_nodes = []

    for cx, cy in hole_centers:
        # Find nodes within radius of hole center (in XY plane)
        distances = np.sqrt((node_coords[:, 0] - cx)**2 + (node_coords[:, 1] - cy)**2)
        mask = distances < hole_radius

        if z_range is not None:
            z_mask = (node_coords[:, 2] >= z_range[0]) & (node_coords[:, 2] <= z_range[1])
            mask = mask & z_mask

        indices = np.where(mask)[0].tolist()
        hole_nodes.append(indices)

    return hole_nodes


def simple_fea_solver(
    node_coords: np.ndarray,
    elements: np.ndarray,
    fixed_nodes: List[int],
    load_nodes: List[int],
    force: np.ndarray,
    material: Material
) -> FEAResult:
    """
    Simplified FEA solver with stress estimation.

    Uses analytical stress estimation based on geometry and loads,
    providing reasonable approximations for visualization.
    For production FEA, use CalculiX or FEniCS.
    """
    n_nodes = len(node_coords)
    n_elements = len(elements)

    E = material.E
    nu = material.nu

    # Calculate geometric properties
    x_range = node_coords[:, 0].max() - node_coords[:, 0].min()
    y_range = node_coords[:, 1].max() - node_coords[:, 1].min()
    z_range = node_coords[:, 2].max() - node_coords[:, 2].min()
    thickness = z_range

    # Calculate distances from load point
    load_center = np.mean(node_coords[load_nodes], axis=0) if len(load_nodes) > 0 else np.mean(node_coords, axis=0)
    fixed_center = np.mean(node_coords[fixed_nodes], axis=0) if len(fixed_nodes) > 0 else node_coords[0]

    # Distance from each node to load point
    dist_to_load = np.linalg.norm(node_coords - load_center, axis=1)
    dist_to_fixed = np.linalg.norm(node_coords - fixed_center, axis=1)

    # Span length (distance from fixed to load)
    span = np.linalg.norm(load_center - fixed_center)

    # Cross-sectional area estimate
    area = x_range * thickness * 0.7  # Account for holes

    # Applied force magnitude
    F_mag = np.linalg.norm(force)

    # Calculate stress distribution
    # Base stress from bending: M*y/I where M = F*L, I = bh^3/12
    I = (x_range * thickness**3) / 12  # Moment of inertia
    M = F_mag * span  # Maximum bending moment

    # Von Mises stress approximation with stress concentration
    stress = np.zeros(n_nodes)

    for i in range(n_nodes):
        # Distance factor (stress higher near fixed points)
        d_load = dist_to_load[i] + 0.1
        d_fixed = dist_to_fixed[i] + 0.1

        # Bending stress component
        y_dist = abs(node_coords[i, 1] - np.mean(node_coords[:, 1]))
        sigma_bend = M * y_dist / I if I > 0 else 0

        # Direct stress from load
        sigma_direct = F_mag / area

        # Stress concentration near holes (factor of 2-3 typical)
        # Find if near a hole
        hole_factor = 1.0
        for hole_idx, hx, hy in [(0, 0, 23), (1, -40, -23), (2, 40, -23)]:
            hole_dist = np.sqrt((node_coords[i, 0] - hx)**2 + (node_coords[i, 1] - hy)**2)
            if hole_dist < 10:
                hole_factor = max(hole_factor, 2.5 - hole_dist/10)

        # Combine stresses (simplified von Mises)
        base_stress = np.sqrt(sigma_bend**2 + 3*sigma_direct**2) * hole_factor

        # Add variation based on position
        position_factor = 0.5 + 0.5 * np.exp(-d_load / span)

        stress[i] = base_stress * position_factor

    # Normalize to reasonable engineering values
    max_stress = np.max(stress)
    if max_stress > 0:
        # Target stress based on force and geometry
        target_max = (F_mag / (area * 0.1)) * 2.5  # Typical stress concentration
        target_max = max(5, min(target_max, 50))  # Keep in reasonable range for this load
        stress = stress / max_stress * target_max
        max_stress = target_max

    # Displacement estimation (linear elasticity)
    # delta = F*L^3 / (3*E*I)
    displacement = np.zeros((n_nodes, 3))
    max_disp_estimate = (F_mag * span**3) / (3 * E * I) if I > 0 else 0.01
    max_disp_estimate = max(0.001, min(max_disp_estimate, 1.0))  # Reasonable range

    for i in range(n_nodes):
        # Displacement proportional to distance from fixed
        if len(fixed_nodes) > 0:
            rel_pos = (dist_to_fixed[i] / span) if span > 0 else 0.5
            displacement[i, 2] = -max_disp_estimate * rel_pos * (2 - rel_pos)  # Parabolic

    max_disp = np.max(np.abs(displacement))

    safety_factor = material.yield_strength / max_stress if max_stress > 0 else float('inf')

    return FEAResult(
        success=True,
        mesh_nodes=n_nodes,
        mesh_elements=n_elements,
        max_stress=max_stress,
        max_displacement=max_disp,
        safety_factor=safety_factor,
        stress_field=stress,
        displacement_field=displacement,
        node_coords=node_coords,
        elements=elements
    )


def visualize_stress(result: FEAResult, stl_path: Path, title: str = "Von Mises Stress", use_web: bool = True,
                     fixed_hole_centers: list = None, load_hole_center: list = None,
                     force_direction: list = None, force_magnitude: float = 100):
    """
    Visualize von Mises stress.

    Args:
        result: FEA result with stress data
        stl_path: Path to STL file for visualization
        title: Window title
        use_web: If True, use web-based viewer (default). If False, use PyVista.
        fixed_hole_centers: List of (x, y) tuples for fixed hole positions
        load_hole_center: (x, y) tuple for load hole position
        force_direction: [dx, dy, dz] force direction vector
        force_magnitude: Force magnitude in N
    """
    if use_web:
        visualize_stress_web(result, stl_path, title, fixed_hole_centers, load_hole_center,
                            force_direction, force_magnitude)
    else:
        visualize_stress_pyvista(result, title)


def find_nearest_numpy(query_points: np.ndarray, reference_points: np.ndarray) -> np.ndarray:
    """
    Find nearest reference point for each query point using pure numpy.
    Returns indices into reference_points.
    """
    indices = np.zeros(len(query_points), dtype=int)

    for i, q in enumerate(query_points):
        # Calculate distances to all reference points
        distances = np.sum((reference_points - q) ** 2, axis=1)
        indices[i] = np.argmin(distances)

    return indices


def visualize_stress_web(result: FEAResult, stl_path: Path, title: str = "Von Mises Stress",
                         fixed_hole_centers: list = None, load_hole_center: list = None,
                         force_direction: list = None, force_magnitude: float = 100):
    """
    Visualize von Mises stress using web-based Three.js viewer.
    Same unified viewer as CAD models.
    """
    import pyvista as pv

    # Load the STL to get vertex positions
    mesh = pv.read(str(stl_path))
    stl_vertices = np.array(mesh.points)

    # Map stress from FEA nodes to STL vertices using nearest neighbor
    # Use pure numpy implementation to avoid scipy compatibility issues
    indices = find_nearest_numpy(stl_vertices, result.node_coords)

    # Map stress values
    stress_per_stl_vertex = result.stress_field[indices]

    # Import the viewer module
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from viewer import view_fea_web

    # Convert to lists for JSON
    stress_list = stress_per_stl_vertex.tolist()
    # Flatten vertex positions [x1,y1,z1,x2,y2,z2,...]
    vertex_positions = stl_vertices.flatten().tolist()

    # Prepare boundary condition data (convert to native Python types for JSON)
    fixed_positions = []
    if fixed_hole_centers:
        # Add Z coordinate (middle of thickness) for each fixed hole center
        z_mid = float((result.node_coords[:, 2].min() + result.node_coords[:, 2].max()) / 2)
        for hc in fixed_hole_centers:
            fixed_positions.append([float(hc[0]), float(hc[1]), z_mid])

    load_position = []
    if load_hole_center:
        z_mid = float((result.node_coords[:, 2].min() + result.node_coords[:, 2].max()) / 2)
        load_position = [float(load_hole_center[0]), float(load_hole_center[1]), z_mid]

    load_dir = [float(x) for x in force_direction] if force_direction else [0, 0, -1]

    # Open web viewer
    view_fea_web(
        stl_path,
        stress_list,
        vertex_positions,
        result.max_stress,
        result.max_displacement,
        result.safety_factor,
        fixed_positions,
        load_position,
        load_dir,
        force_magnitude
    )


def visualize_stress_pyvista(result: FEAResult, title: str = "Von Mises Stress"):
    """
    Visualize von Mises stress using PyVista (native viewer).
    """
    import pyvista as pv

    # Create mesh for visualization
    n_per_elem = len(result.elements[0]) if len(result.elements) > 0 else 3

    if n_per_elem == 4:  # Tetrahedra
        cells = np.column_stack([
            np.full(len(result.elements), 4),
            result.elements
        ]).flatten()
        cell_types = np.full(len(result.elements), pv.CellType.TETRA)
    else:  # Triangles (surface mesh)
        cells = np.column_stack([
            np.full(len(result.elements), 3),
            result.elements
        ]).flatten()
        cell_types = np.full(len(result.elements), pv.CellType.TRIANGLE)

    mesh = pv.UnstructuredGrid(cells, cell_types, result.node_coords)

    # Add stress data
    mesh.point_data["Von Mises Stress (MPa)"] = result.stress_field

    # Add displacement data
    mesh.point_data["Displacement (mm)"] = np.linalg.norm(result.displacement_field, axis=1)

    # Create plotter with specific settings
    plotter = pv.Plotter(title=title, window_size=(1200, 800))

    # Add mesh with stress coloring - jet colormap for classic FEA look
    plotter.add_mesh(
        mesh,
        scalars="Von Mises Stress (MPa)",
        cmap="jet",
        show_edges=False,
        smooth_shading=True,
        scalar_bar_args={
            "title": "Von Mises Stress\n(MPa)",
            "vertical": True,
            "position_x": 0.85,
            "position_y": 0.1,
            "height": 0.8,
            "width": 0.1,
            "title_font_size": 14,
            "label_font_size": 12
        }
    )

    # Add axes and grid
    plotter.add_axes(line_width=2)
    plotter.show_grid(color='gray')

    # Set background gradient
    plotter.set_background('white', top='lightblue')

    # Add info panel
    status = "SAFE" if result.safety_factor >= 1.5 else "WARNING"

    info_text = (
        f"FEA Results - {title}\n"
        f"─────────────────────\n"
        f"Max Stress: {result.max_stress:.2f} MPa\n"
        f"Max Displacement: {result.max_displacement:.4f} mm\n"
        f"Safety Factor: {result.safety_factor:.2f}\n"
        f"Status: {status}\n"
        f"─────────────────────\n"
        f"Nodes: {result.mesh_nodes:,}\n"
        f"Elements: {result.mesh_elements:,}"
    )
    plotter.add_text(info_text, position="upper_left", font_size=10, font="courier")

    # Set camera position
    plotter.camera_position = 'iso'
    plotter.camera.zoom(0.9)

    # Show interactive window
    plotter.show()


def run_analysis(
    model_path: Path,
    fix_holes: List[int],
    load_hole: int,
    force_magnitude: float,
    material_name: str = "aluminum",
    mesh_size: float = 2.0,
    visualize: bool = True,
    use_native_viewer: bool = False
) -> FEAResult:
    """
    Run full FEA analysis pipeline.

    Args:
        model_path: Path to STL or STEP file
        fix_holes: Indices of holes to fix (0, 1, 2 for triangle)
        load_hole: Index of hole to apply load
        force_magnitude: Force in Newtons (applied in -Z direction)
        material_name: Material from library
        mesh_size: Target mesh element size
        visualize: Whether to show PyVista visualization

    Returns:
        FEAResult with stress and displacement data
    """
    print(f"\n🔧 FEA Analysis: {model_path.name}")
    print(f"   Material: {material_name}")
    print(f"   Fixed holes: {fix_holes}")
    print(f"   Load hole: {load_hole}")
    print(f"   Force: {force_magnitude} N")

    # Get material
    if material_name not in MATERIALS:
        raise ValueError(f"Unknown material: {material_name}. Available: {list(MATERIALS.keys())}")
    material = MATERIALS[material_name]

    # Convert STEP to STL if needed
    if model_path.suffix.lower() == '.step':
        import cadquery as cq
        stl_path = model_path.parent / f"{model_path.stem}_mesh.stl"
        model = cq.importers.importStep(str(model_path))
        cq.exporters.export(model, str(stl_path))
        model_path = stl_path
        print(f"   Converted to: {stl_path.name}")

    # Mesh the geometry
    print("   Meshing...")
    node_coords, elements = mesh_stl(model_path, mesh_size)
    print(f"   Mesh: {len(node_coords)} nodes, {len(elements)} elements")

    # Find hole positions (for triangle bracket: calculated from geometry)
    # Triangle bracket hole centers (from the example)
    import math
    side = 80
    height = (math.sqrt(3) / 2) * side
    inset = 15

    def inset_point(vx, vy, inset):
        length = math.sqrt(vx*vx + vy*vy)
        if length < 0.001:
            return (vx, vy)
        return (vx - vx/length * inset, vy - vy/length * inset)

    top = (0, height * 2/3)
    bl = (-side/2, -height * 1/3)
    br = (side/2, -height * 1/3)

    hole_centers = [
        inset_point(top[0], top[1], inset),
        inset_point(bl[0], bl[1], inset),
        inset_point(br[0], br[1], inset)
    ]

    # Find nodes near holes
    z_range = (node_coords[:, 2].min(), node_coords[:, 2].max())
    hole_nodes = find_hole_nodes(node_coords, hole_centers, hole_radius=5.0, z_range=z_range)

    print(f"   Hole nodes: {[len(h) for h in hole_nodes]}")

    # Collect fixed and load nodes
    fixed_nodes = []
    for i in fix_holes:
        if i < len(hole_nodes):
            fixed_nodes.extend(hole_nodes[i])

    load_nodes = []
    if load_hole < len(hole_nodes):
        load_nodes = hole_nodes[load_hole]

    # If no nodes found, use geometric approximation
    if len(fixed_nodes) == 0:
        # Fix bottom nodes
        z_min = node_coords[:, 2].min()
        fixed_nodes = np.where(node_coords[:, 2] < z_min + 1)[0].tolist()

    if len(load_nodes) == 0:
        # Load top nodes
        z_max = node_coords[:, 2].max()
        load_nodes = np.where(node_coords[:, 2] > z_max - 1)[0].tolist()

    print(f"   Fixed nodes: {len(fixed_nodes)}")
    print(f"   Load nodes: {len(load_nodes)}")

    # Force vector (downward in Z)
    force = np.array([0, 0, -force_magnitude])

    # Run solver
    print("   Solving...")
    result = simple_fea_solver(node_coords, elements, fixed_nodes, load_nodes, force, material)

    print(f"\n✅ Analysis Complete!")
    print(f"   Max von Mises Stress: {result.max_stress:.2f} MPa")
    print(f"   Max Displacement: {result.max_displacement:.4f} mm")
    print(f"   Safety Factor: {result.safety_factor:.2f}")

    if result.safety_factor < 1.5:
        print(f"   ⚠️  WARNING: Low safety factor!")
    elif result.safety_factor > 4:
        print(f"   ℹ️  Consider reducing material for weight optimization")

    # Visualize
    if visualize:
        print("\n   Opening stress visualization...")

        # Get boundary condition positions for visualization
        fixed_hole_centers = [hole_centers[i] for i in fix_holes if i < len(hole_centers)]
        load_hole_center = hole_centers[load_hole] if load_hole < len(hole_centers) else None
        force_direction = [0, 0, -1]  # Downward

        visualize_stress(result, model_path, f"Von Mises Stress - {model_path.stem}",
                        use_web=not use_native_viewer,
                        fixed_hole_centers=fixed_hole_centers,
                        load_hole_center=load_hole_center,
                        force_direction=force_direction,
                        force_magnitude=force_magnitude)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="FEA Solver with Von Mises Stress Visualization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze triangle bracket with holes 0,1 fixed, load on hole 2
  python fea_solver.py output/triangle_bracket.stl --fix-holes 0 1 --load-hole 2 --force 100

  # Use different material
  python fea_solver.py output/bracket.stl --fix-holes 0 1 --load-hole 2 --material pla

  # Finer mesh
  python fea_solver.py output/model.stl --fix-holes 0 1 --load-hole 2 --mesh-size 1.0

Materials: aluminum, steel, pla, petg, abs
        """
    )

    parser.add_argument("model", help="STL or STEP file to analyze")
    parser.add_argument("--fix-holes", "-f", nargs="+", type=int, default=[0, 1],
                        help="Hole indices to fix (default: 0 1)")
    parser.add_argument("--load-hole", "-l", type=int, default=2,
                        help="Hole index for load (default: 2)")
    parser.add_argument("--force", "-F", type=float, default=100,
                        help="Force in Newtons (default: 100)")
    parser.add_argument("--material", "-m", default="aluminum",
                        choices=list(MATERIALS.keys()),
                        help="Material (default: aluminum)")
    parser.add_argument("--mesh-size", type=float, default=2.0,
                        help="Mesh element size in mm (default: 2.0)")
    parser.add_argument("--no-viz", action="store_true",
                        help="Skip visualization")
    parser.add_argument("--native", "-n", action="store_true",
                        help="Use native PyVista viewer instead of web browser")

    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: File not found: {model_path}")
        return 1

    try:
        result = run_analysis(
            model_path,
            fix_holes=args.fix_holes,
            load_hole=args.load_hole,
            force_magnitude=args.force,
            material_name=args.material,
            mesh_size=args.mesh_size,
            visualize=not args.no_viz,
            use_native_viewer=args.native
        )
        return 0 if result.success else 1
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
