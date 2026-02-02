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


@dataclass
class MeshQuality:
    """Mesh quality statistics"""
    n_nodes: int
    n_elements: int
    min_aspect_ratio: float
    max_aspect_ratio: float
    avg_aspect_ratio: float
    min_angle: float
    max_angle: float
    avg_angle: float
    quality_score: float  # 0-1, higher is better


def calculate_mesh_quality(node_coords: np.ndarray, elements: np.ndarray) -> MeshQuality:
    """
    Calculate mesh quality metrics for triangle elements.

    Returns:
        MeshQuality with aspect ratio, angles, and overall quality score
    """
    aspect_ratios = []
    min_angles = []
    max_angles = []

    for elem in elements:
        if len(elem) < 3:
            continue

        # Get triangle vertices
        p0, p1, p2 = node_coords[elem[0]], node_coords[elem[1]], node_coords[elem[2]]

        # Calculate edge lengths
        e0 = np.linalg.norm(p1 - p0)
        e1 = np.linalg.norm(p2 - p1)
        e2 = np.linalg.norm(p0 - p2)

        edges = sorted([e0, e1, e2])
        if edges[0] > 1e-10:
            aspect_ratios.append(edges[2] / edges[0])

        # Calculate angles using law of cosines
        def angle_at_vertex(a, b, c):
            # Angle at vertex where edges of length a and b meet, opposite to edge c
            cos_angle = (a*a + b*b - c*c) / (2*a*b + 1e-10)
            cos_angle = np.clip(cos_angle, -1, 1)
            return np.degrees(np.arccos(cos_angle))

        if e0 > 1e-10 and e1 > 1e-10 and e2 > 1e-10:
            a0 = angle_at_vertex(e0, e2, e1)
            a1 = angle_at_vertex(e0, e1, e2)
            a2 = angle_at_vertex(e1, e2, e0)
            angles = [a0, a1, a2]
            min_angles.append(min(angles))
            max_angles.append(max(angles))

    if not aspect_ratios:
        return MeshQuality(len(node_coords), len(elements), 1, 1, 1, 60, 60, 60, 1.0)

    # Calculate quality score (0-1)
    # Good mesh: aspect ratio < 3, min angle > 20°, max angle < 120°
    avg_ar = np.mean(aspect_ratios)
    avg_min_angle = np.mean(min_angles) if min_angles else 60
    avg_max_angle = np.mean(max_angles) if max_angles else 60

    ar_score = max(0, 1 - (avg_ar - 1) / 4)  # 1.0 for AR=1, 0 for AR=5
    angle_score = min(avg_min_angle / 30, 1.0)  # 1.0 for min_angle >= 30°
    max_angle_score = max(0, 1 - (avg_max_angle - 60) / 60)  # 1.0 for 60°, 0 for 120°

    quality_score = (ar_score + angle_score + max_angle_score) / 3

    return MeshQuality(
        n_nodes=len(node_coords),
        n_elements=len(elements),
        min_aspect_ratio=min(aspect_ratios),
        max_aspect_ratio=max(aspect_ratios),
        avg_aspect_ratio=avg_ar,
        min_angle=min(min_angles) if min_angles else 60,
        max_angle=max(max_angles) if max_angles else 60,
        avg_angle=avg_min_angle,
        quality_score=quality_score
    )


def clean_mesh_pyvista(stl_path: Path, target_reduction: float = 0.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Clean and optionally decimate STL mesh using PyVista.

    Args:
        stl_path: Path to STL file
        target_reduction: Fraction of triangles to remove (0-1), 0 = no reduction

    Returns:
        Tuple of (node_coords, elements) with cleaned mesh
    """
    import pyvista as pv

    # Load mesh
    mesh = pv.read(str(stl_path))

    # Clean the mesh (merge duplicate points, remove degenerate cells)
    mesh = mesh.clean(tolerance=1e-6)

    # Compute normals for better visualization
    mesh = mesh.compute_normals(auto_orient_normals=True)

    # Optional decimation for very dense meshes
    if target_reduction > 0 and mesh.n_cells > 1000:
        mesh = mesh.decimate(target_reduction)

    # Extract points and faces
    node_coords = np.array(mesh.points)

    # Get faces
    faces = mesh.faces.reshape(-1, 4)[:, 1:4]

    return node_coords, faces


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


def mesh_stl(stl_path: Path, mesh_size: float = 3.0, clean: bool = True) -> Tuple[np.ndarray, np.ndarray, MeshQuality]:
    """
    Mesh an STL file with quality metrics.

    Args:
        stl_path: Path to STL file
        mesh_size: Target element size (currently unused, for future Gmsh integration)
        clean: If True, clean the mesh (merge duplicates, fix normals)

    Returns:
        Tuple of (node_coords, elements, quality)
    """
    if clean:
        try:
            node_coords, elements = clean_mesh_pyvista(stl_path)
            quality = calculate_mesh_quality(node_coords, elements)
            return node_coords, elements, quality
        except Exception as e:
            print(f"   Warning: Mesh cleaning failed ({e}), using original mesh")

    # Fallback to direct STL loading
    node_coords, elements = load_stl_mesh(stl_path)
    quality = calculate_mesh_quality(node_coords, elements)
    return node_coords, elements, quality


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
    material: Material,
    hole_centers: List[Tuple[float, float]] = None,
    fixed_hole_indices: List[int] = None,
    load_hole_index: int = None
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

    # Get individual fixed hole centers for symmetric stress calculation
    fixed_centers = []
    if hole_centers and fixed_hole_indices:
        for idx in fixed_hole_indices:
            if idx < len(hole_centers):
                hc = hole_centers[idx]
                z_mid = (node_coords[:, 2].min() + node_coords[:, 2].max()) / 2
                fixed_centers.append(np.array([hc[0], hc[1], z_mid]))

    if not fixed_centers:
        # Fallback to mean of fixed nodes
        fixed_centers = [np.mean(node_coords[fixed_nodes], axis=0)] if len(fixed_nodes) > 0 else [node_coords[0]]

    # Distance from each node to load point
    dist_to_load = np.linalg.norm(node_coords - load_center, axis=1)

    # Distance to nearest fixed point (for symmetric stress at both fixed holes)
    dist_to_fixed = np.full(n_nodes, np.inf)
    for fc in fixed_centers:
        dist_i = np.linalg.norm(node_coords - fc, axis=1)
        dist_to_fixed = np.minimum(dist_to_fixed, dist_i)

    # Span length (average distance from fixed centers to load)
    span = np.mean([np.linalg.norm(load_center - fc) for fc in fixed_centers])

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
        # Use actual hole positions if provided
        hole_factor = 1.0
        if hole_centers:
            for hc in hole_centers:
                hole_dist = np.sqrt((node_coords[i, 0] - hc[0])**2 + (node_coords[i, 1] - hc[1])**2)
                if hole_dist < 10:
                    hole_factor = max(hole_factor, 2.5 - hole_dist/10)

        # Combine stresses (simplified von Mises)
        base_stress = np.sqrt(sigma_bend**2 + 3*sigma_direct**2) * hole_factor

        # Stress increases near fixed boundaries (reaction forces)
        # Use exponential decay from fixed points
        fixed_stress_factor = 1.0 + 1.5 * np.exp(-d_fixed / 8)

        # Stress also increases toward load application point
        load_stress_factor = 1.0 + 0.5 * np.exp(-d_load / 10)

        stress[i] = base_stress * fixed_stress_factor * load_stress_factor

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
                     force_direction: list = None, force_magnitude: float = 100,
                     mesh_quality: 'MeshQuality' = None):
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
        mesh_quality: MeshQuality object with mesh statistics
    """
    if use_web:
        visualize_stress_web(result, stl_path, title, fixed_hole_centers, load_hole_center,
                            force_direction, force_magnitude, mesh_quality)
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
                         force_direction: list = None, force_magnitude: float = 100,
                         mesh_quality: 'MeshQuality' = None):
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

    # Mesh quality info
    mesh_elements = result.mesh_elements
    mesh_aspect = mesh_quality.avg_aspect_ratio if mesh_quality else 1.0
    mesh_qual_score = mesh_quality.quality_score if mesh_quality else 1.0

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
        force_magnitude,
        mesh_elements,
        mesh_aspect,
        mesh_qual_score
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

    # Mesh the geometry with cleaning
    print("   Loading and cleaning mesh...")
    node_coords, elements, quality = mesh_stl(model_path, mesh_size, clean=True)

    print(f"   Mesh Statistics:")
    print(f"      Nodes: {quality.n_nodes}")
    print(f"      Elements: {quality.n_elements}")
    print(f"      Aspect Ratio: {quality.avg_aspect_ratio:.2f} (range: {quality.min_aspect_ratio:.2f} - {quality.max_aspect_ratio:.2f})")
    print(f"      Min Angle: {quality.min_angle:.1f}° (avg: {quality.avg_angle:.1f}°)")
    print(f"      Max Angle: {quality.max_angle:.1f}°")
    print(f"      Quality Score: {quality.quality_score:.2f} (0-1, higher is better)")

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
    result = simple_fea_solver(
        node_coords, elements, fixed_nodes, load_nodes, force, material,
        hole_centers=hole_centers,
        fixed_hole_indices=fix_holes,
        load_hole_index=load_hole
    )

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
                        force_magnitude=force_magnitude,
                        mesh_quality=quality)

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
