#!/usr/bin/env python3
"""
3D Model Viewer - Display CAD models with rotate/pan/zoom

Two modes:
1. Web viewer (default): Opens browser with Three.js viewer
2. Native viewer: Uses PyVista for Python-native display

Usage:
    # View an STL file (opens browser)
    python viewer.py output/my_model.stl

    # View a STEP file
    python viewer.py output/my_model.step

    # Use native PyVista viewer
    python viewer.py output/my_model.stl --native

    # Auto-view latest file in output/
    python viewer.py --latest
"""

import sys
import json
import tempfile
import webbrowser
import http.server
import socketserver
import threading
from pathlib import Path
from typing import Optional
import argparse


def get_latest_model(output_dir: Path = Path("output")) -> Optional[Path]:
    """Find the most recently modified STL or STEP file."""
    files = list(output_dir.glob("*.stl")) + list(output_dir.glob("*.step"))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def convert_step_to_stl(step_file: Path, output_dir: Path = None) -> Path:
    """Convert STEP to STL for web viewing."""
    try:
        import cadquery as cq
        from cadquery import importers

        model = importers.importStep(str(step_file))

        if output_dir is None:
            output_dir = step_file.parent

        stl_path = output_dir / f"{step_file.stem}_view.stl"
        cq.exporters.export(model, str(stl_path), exportType="STL")
        return stl_path
    except Exception as e:
        raise RuntimeError(f"Failed to convert STEP to STL: {e}")


# HTML template for Three.js viewer
VIEWER_HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>Engineering Hub - 3D Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            overflow: hidden;
        }
        #container { width: 100vw; height: 100vh; }
        #info {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.7);
            padding: 15px 20px;
            border-radius: 8px;
            font-size: 14px;
            z-index: 100;
        }
        #info h2 {
            margin-bottom: 10px;
            color: #4fc3f7;
            font-size: 16px;
        }
        #info p { margin: 5px 0; color: #aaa; }
        #info .key {
            display: inline-block;
            background: #333;
            padding: 2px 8px;
            border-radius: 4px;
            font-family: monospace;
            margin-right: 5px;
        }
        #controls {
            position: absolute;
            bottom: 10px;
            left: 10px;
            background: rgba(0,0,0,0.7);
            padding: 10px 15px;
            border-radius: 8px;
            z-index: 100;
        }
        #controls button {
            background: #4fc3f7;
            border: none;
            color: #000;
            padding: 8px 16px;
            margin: 0 5px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
        }
        #controls button:hover { background: #81d4fa; }
        #stats {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.7);
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 12px;
            z-index: 100;
        }
        #loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 18px;
            color: #4fc3f7;
        }
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="info">
        <h2>🔧 Engineering Hub Viewer</h2>
        <p><span class="key">Left drag</span> Rotate</p>
        <p><span class="key">Right drag</span> Pan</p>
        <p><span class="key">Scroll</span> Zoom</p>
        <p><span class="key">R</span> Reset view</p>
    </div>
    <div id="controls">
        <button onclick="resetView()">Reset View</button>
        <button onclick="toggleWireframe()">Wireframe</button>
        <button onclick="cycleColor()">Color</button>
    </div>
    <div id="stats">
        <div id="filename">Loading...</div>
        <div id="triangles"></div>
        <div id="size"></div>
    </div>
    <div id="loading">Loading model...</div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>

    <script>
        // Configuration
        const MODEL_URL = '__MODEL_URL__';
        const MODEL_NAME = '__MODEL_NAME__';

        // Three.js setup
        let scene, camera, renderer, controls, mesh;
        let wireframe = false;
        let colorIndex = 0;
        const colors = [0x4fc3f7, 0x81c784, 0xffb74d, 0xe57373, 0xba68c8, 0x90a4ae];

        function init() {
            // Scene
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x1a1a2e);

            // Camera
            camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 10000);
            camera.position.set(100, 100, 100);

            // Renderer
            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(window.devicePixelRatio);
            document.getElementById('container').appendChild(renderer.domElement);

            // Controls
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;

            // Lights
            const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
            scene.add(ambientLight);

            const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(100, 100, 100);
            scene.add(directionalLight);

            const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
            directionalLight2.position.set(-100, -100, -100);
            scene.add(directionalLight2);

            // Grid
            const gridHelper = new THREE.GridHelper(200, 20, 0x444444, 0x333333);
            scene.add(gridHelper);

            // Axes
            const axesHelper = new THREE.AxesHelper(50);
            scene.add(axesHelper);

            // Load model
            loadModel();

            // Events
            window.addEventListener('resize', onWindowResize);
            document.addEventListener('keydown', onKeyDown);

            // Animate
            animate();
        }

        function loadModel() {
            const loader = new THREE.STLLoader();

            loader.load(MODEL_URL, function(geometry) {
                // Center geometry
                geometry.computeBoundingBox();
                const center = new THREE.Vector3();
                geometry.boundingBox.getCenter(center);
                geometry.translate(-center.x, -center.y, -center.z);

                // Material
                const material = new THREE.MeshPhongMaterial({
                    color: colors[colorIndex],
                    specular: 0x444444,
                    shininess: 30,
                    flatShading: false
                });

                // Mesh
                mesh = new THREE.Mesh(geometry, material);
                scene.add(mesh);

                // Fit camera to model
                fitCameraToModel();

                // Update stats
                document.getElementById('loading').style.display = 'none';
                document.getElementById('filename').textContent = MODEL_NAME;
                document.getElementById('triangles').textContent =
                    `Triangles: ${(geometry.attributes.position.count / 3).toLocaleString()}`;

                const box = geometry.boundingBox;
                const size = new THREE.Vector3();
                box.getSize(size);
                document.getElementById('size').textContent =
                    `Size: ${size.x.toFixed(1)} × ${size.y.toFixed(1)} × ${size.z.toFixed(1)} mm`;

            }, undefined, function(error) {
                document.getElementById('loading').textContent = 'Error loading model: ' + error;
            });
        }

        function fitCameraToModel() {
            if (!mesh) return;

            const box = new THREE.Box3().setFromObject(mesh);
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);

            camera.position.set(maxDim * 1.5, maxDim * 1.5, maxDim * 1.5);
            controls.target.set(0, 0, 0);
            controls.update();
        }

        function resetView() {
            fitCameraToModel();
        }

        function toggleWireframe() {
            if (!mesh) return;
            wireframe = !wireframe;
            mesh.material.wireframe = wireframe;
        }

        function cycleColor() {
            if (!mesh) return;
            colorIndex = (colorIndex + 1) % colors.length;
            mesh.material.color.setHex(colors[colorIndex]);
        }

        function onWindowResize() {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }

        function onKeyDown(event) {
            if (event.key === 'r' || event.key === 'R') resetView();
            if (event.key === 'w' || event.key === 'W') toggleWireframe();
            if (event.key === 'c' || event.key === 'C') cycleColor();
        }

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }

        init();
    </script>
</body>
</html>
'''

# FEA Viewer HTML template with stress coloring
FEA_VIEWER_HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>Engineering Hub - FEA Stress Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            overflow: hidden;
        }
        #container { width: 100vw; height: 100vh; }
        #info {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.85);
            padding: 15px 20px;
            border-radius: 8px;
            font-size: 14px;
            z-index: 100;
            min-width: 220px;
        }
        #info h2 {
            margin-bottom: 10px;
            color: #ff6b6b;
            font-size: 16px;
        }
        #info p { margin: 5px 0; color: #aaa; }
        #info .value { color: #4fc3f7; font-weight: bold; }
        #info .safe { color: #81c784; }
        #info .warning { color: #ffb74d; }
        #info .danger { color: #e57373; }
        #info .key {
            display: inline-block;
            background: #333;
            padding: 2px 8px;
            border-radius: 4px;
            font-family: monospace;
            margin-right: 5px;
        }
        #colorbar {
            position: absolute;
            right: 20px;
            top: 50%;
            transform: translateY(-50%);
            width: 30px;
            height: 300px;
            background: linear-gradient(to bottom, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff);
            border: 2px solid #fff;
            border-radius: 4px;
            z-index: 100;
        }
        #colorbar-labels {
            position: absolute;
            right: 60px;
            top: 50%;
            transform: translateY(-50%);
            height: 300px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            font-size: 12px;
            color: #fff;
            z-index: 100;
        }
        #colorbar-title {
            position: absolute;
            right: 20px;
            top: calc(50% - 170px);
            transform: translateY(-50%);
            font-size: 12px;
            color: #fff;
            z-index: 100;
            text-align: center;
            width: 80px;
        }
        #controls {
            position: absolute;
            bottom: 10px;
            left: 10px;
            background: rgba(0,0,0,0.7);
            padding: 10px 15px;
            border-radius: 8px;
            z-index: 100;
        }
        #controls button {
            background: #ff6b6b;
            border: none;
            color: #fff;
            padding: 8px 16px;
            margin: 0 5px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
        }
        #controls button:hover { background: #ff8a8a; }
        #loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 18px;
            color: #ff6b6b;
        }
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="info">
        <h2>FEA Results</h2>
        <p>Model: <span class="value" id="model-name">__MODEL_NAME__</span></p>
        <p>Max Stress: <span class="value" id="max-stress">__MAX_STRESS__</span> MPa</p>
        <p>Max Disp: <span class="value" id="max-disp">__MAX_DISP__</span> mm</p>
        <p>Safety Factor: <span class="value __SAFETY_CLASS__" id="safety">__SAFETY_FACTOR__</span></p>
        <hr style="margin: 10px 0; border-color: #444;">
        <p><span class="key">Left drag</span> Rotate</p>
        <p><span class="key">Scroll</span> Zoom</p>
        <p><span class="key">R</span> Reset view</p>
    </div>
    <div id="colorbar-title">Von Mises<br>Stress (MPa)</div>
    <div id="colorbar"></div>
    <div id="colorbar-labels">
        <span id="max-label">__MAX_STRESS__</span>
        <span id="mid-label">__MID_STRESS__</span>
        <span id="min-label">0.00</span>
    </div>
    <div id="controls">
        <button onclick="resetView()">Reset View</button>
        <button onclick="toggleWireframe()">Wireframe</button>
    </div>
    <div id="loading">Loading FEA results...</div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>

    <script>
        const MODEL_URL = '__MODEL_URL__';
        const STRESS_DATA = __STRESS_DATA__;
        const VERTEX_POSITIONS = __VERTEX_POSITIONS__;
        const MAX_STRESS = __MAX_STRESS_RAW__;

        let scene, camera, renderer, controls, mesh;
        let wireframe = false;

        // Jet colormap (blue -> cyan -> green -> yellow -> red)
        function jetColor(value) {
            // value from 0 to 1
            let r, g, b;
            if (value < 0.25) {
                r = 0;
                g = 4 * value;
                b = 1;
            } else if (value < 0.5) {
                r = 0;
                g = 1;
                b = 1 - 4 * (value - 0.25);
            } else if (value < 0.75) {
                r = 4 * (value - 0.5);
                g = 1;
                b = 0;
            } else {
                r = 1;
                g = 1 - 4 * (value - 0.75);
                b = 0;
            }
            return new THREE.Color(r, g, b);
        }

        function init() {
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x1a1a2e);

            camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 10000);
            camera.position.set(100, 100, 100);

            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(window.devicePixelRatio);
            document.getElementById('container').appendChild(renderer.domElement);

            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;

            // Lighting
            const ambient = new THREE.AmbientLight(0xffffff, 0.6);
            scene.add(ambient);
            const dir1 = new THREE.DirectionalLight(0xffffff, 0.8);
            dir1.position.set(100, 100, 100);
            scene.add(dir1);
            const dir2 = new THREE.DirectionalLight(0xffffff, 0.4);
            dir2.position.set(-100, -100, -100);
            scene.add(dir2);

            // Grid
            const grid = new THREE.GridHelper(200, 20, 0x444444, 0x333333);
            scene.add(grid);

            loadModel();

            window.addEventListener('resize', onResize);
            document.addEventListener('keydown', onKeyDown);
            animate();
        }

        // Find nearest vertex in reference positions
        function findNearestStress(x, y, z) {
            let minDist = Infinity;
            let bestIdx = 0;

            for (let i = 0; i < VERTEX_POSITIONS.length; i += 3) {
                const dx = x - VERTEX_POSITIONS[i];
                const dy = y - VERTEX_POSITIONS[i + 1];
                const dz = z - VERTEX_POSITIONS[i + 2];
                const dist = dx*dx + dy*dy + dz*dz;

                if (dist < minDist) {
                    minDist = dist;
                    bestIdx = Math.floor(i / 3);
                }
            }
            return STRESS_DATA[bestIdx] || 0;
        }

        function loadModel() {
            const loader = new THREE.STLLoader();
            loader.load(MODEL_URL, function(geometry) {
                geometry.computeBoundingBox();
                const center = new THREE.Vector3();
                geometry.boundingBox.getCenter(center);

                // Apply stress colors to vertices by matching positions
                const positions = geometry.attributes.position;
                const colors = new Float32Array(positions.count * 3);

                for (let i = 0; i < positions.count; i++) {
                    const x = positions.getX(i);
                    const y = positions.getY(i);
                    const z = positions.getZ(i);

                    const stressValue = findNearestStress(x, y, z);
                    const normalizedStress = stressValue / MAX_STRESS;
                    const color = jetColor(Math.min(1, Math.max(0, normalizedStress)));

                    colors[i * 3] = color.r;
                    colors[i * 3 + 1] = color.g;
                    colors[i * 3 + 2] = color.b;
                }

                // Center the geometry after computing colors
                geometry.translate(-center.x, -center.y, -center.z);
                geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                const material = new THREE.MeshPhongMaterial({
                    vertexColors: true,
                    side: THREE.DoubleSide,
                    flatShading: false
                });

                mesh = new THREE.Mesh(geometry, material);
                scene.add(mesh);

                fitCamera();
                document.getElementById('loading').style.display = 'none';
            });
        }

        function fitCamera() {
            if (!mesh) return;
            const box = new THREE.Box3().setFromObject(mesh);
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            camera.position.set(maxDim * 1.5, maxDim * 1.5, maxDim * 1.5);
            controls.target.set(0, 0, 0);
            controls.update();
        }

        function resetView() { fitCamera(); }

        function toggleWireframe() {
            if (!mesh) return;
            wireframe = !wireframe;
            mesh.material.wireframe = wireframe;
        }

        function onResize() {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }

        function onKeyDown(e) {
            if (e.key === 'r' || e.key === 'R') resetView();
            if (e.key === 'w' || e.key === 'W') toggleWireframe();
        }

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }

        init();
    </script>
</body>
</html>
'''


def create_viewer_html(stl_path: Path, output_dir: Path = None) -> Path:
    """Create HTML viewer file for the STL."""
    if output_dir is None:
        output_dir = stl_path.parent

    html_path = output_dir / f"{stl_path.stem}_viewer.html"

    # Create HTML with embedded model path
    html_content = VIEWER_HTML.replace('__MODEL_URL__', stl_path.name)
    html_content = html_content.replace('__MODEL_NAME__', stl_path.stem)

    html_path.write_text(html_content)
    return html_path


def create_fea_viewer_html(stl_path: Path, stress_data: list, vertex_positions: list,
                           max_stress: float, max_displacement: float, safety_factor: float,
                           output_dir: Path = None) -> Path:
    """Create HTML viewer file with FEA stress coloring."""
    if output_dir is None:
        output_dir = stl_path.parent

    html_path = output_dir / f"{stl_path.stem}_fea_viewer.html"

    # Determine safety class
    if safety_factor >= 2.0:
        safety_class = "safe"
    elif safety_factor >= 1.5:
        safety_class = "warning"
    else:
        safety_class = "danger"

    # Create HTML with FEA data
    html_content = FEA_VIEWER_HTML
    html_content = html_content.replace('__MODEL_URL__', stl_path.name)
    html_content = html_content.replace('__MODEL_NAME__', stl_path.stem)
    html_content = html_content.replace('__MAX_STRESS__', f"{max_stress:.2f}")
    html_content = html_content.replace('__MID_STRESS__', f"{max_stress/2:.2f}")
    html_content = html_content.replace('__MAX_STRESS_RAW__', str(max_stress))
    html_content = html_content.replace('__MAX_DISP__', f"{max_displacement:.4f}")
    html_content = html_content.replace('__SAFETY_FACTOR__', f"{safety_factor:.2f}")
    html_content = html_content.replace('__SAFETY_CLASS__', safety_class)
    html_content = html_content.replace('__STRESS_DATA__', json.dumps(stress_data))
    html_content = html_content.replace('__VERTEX_POSITIONS__', json.dumps(vertex_positions))

    html_path.write_text(html_content)
    return html_path


def view_fea_web(stl_path: Path, stress_data: list, vertex_positions: list,
                 max_stress: float, max_displacement: float, safety_factor: float):
    """View FEA results in web browser with stress coloring."""
    html_path = create_fea_viewer_html(
        stl_path, stress_data, vertex_positions, max_stress, max_displacement, safety_factor
    )
    print(f"Created FEA viewer: {html_path.name}")
    serve_and_open(stl_path.parent, html_path.name)


def serve_and_open(directory: Path, html_file: str, port: int = 8765):
    """Start a local server and open browser."""
    import os
    os.chdir(directory)

    handler = http.server.SimpleHTTPRequestHandler

    # Find available port
    for p in range(port, port + 100):
        try:
            with socketserver.TCPServer(("", p), handler) as httpd:
                url = f"http://localhost:{p}/{html_file}"
                print(f"\n🌐 Opening viewer at: {url}")
                print("   Press Ctrl+C to close\n")

                # Open browser
                webbrowser.open(url)

                # Serve
                httpd.serve_forever()
        except OSError:
            continue
        except KeyboardInterrupt:
            print("\n👋 Viewer closed")
            break


def view_native(file_path: Path):
    """View model using PyVista (native Python viewer)."""
    try:
        import pyvista as pv
    except ImportError:
        print("PyVista not installed. Install with: pip install pyvista")
        print("Falling back to web viewer...")
        return False

    # Load mesh
    if file_path.suffix.lower() == '.stl':
        mesh = pv.read(str(file_path))
    elif file_path.suffix.lower() == '.step':
        # Convert STEP to STL first
        stl_path = convert_step_to_stl(file_path)
        mesh = pv.read(str(stl_path))
    else:
        print(f"Unsupported format: {file_path.suffix}")
        return False

    # Create plotter
    plotter = pv.Plotter(title=f"Engineering Hub - {file_path.name}")
    plotter.add_mesh(mesh, color='#4fc3f7', show_edges=False)
    plotter.add_axes()
    plotter.show_grid()
    plotter.show()

    return True


def view_web(file_path: Path):
    """View model in web browser using Three.js."""
    stl_path = file_path

    # Convert STEP to STL if needed
    if file_path.suffix.lower() == '.step':
        print(f"Converting {file_path.name} to STL for viewing...")
        stl_path = convert_step_to_stl(file_path)
        print(f"Created: {stl_path.name}")

    # Create HTML viewer
    html_path = create_viewer_html(stl_path)
    print(f"Created viewer: {html_path.name}")

    # Serve and open
    serve_and_open(stl_path.parent, html_path.name)


def main():
    parser = argparse.ArgumentParser(
        description="3D Model Viewer for Engineering Hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Controls (Web Viewer):
  Left mouse drag    Rotate model
  Right mouse drag   Pan view
  Scroll wheel       Zoom in/out
  R                  Reset view
  W                  Toggle wireframe
  C                  Cycle colors

Examples:
  python viewer.py output/my_model.stl
  python viewer.py output/my_model.step
  python viewer.py --latest
  python viewer.py output/my_model.stl --native
        """
    )

    parser.add_argument("file", nargs="?", help="STL or STEP file to view")
    parser.add_argument("--latest", "-l", action="store_true",
                        help="View the most recently modified model in output/")
    parser.add_argument("--native", "-n", action="store_true",
                        help="Use native PyVista viewer instead of web")
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("output"),
                        help="Output directory for generated files")

    args = parser.parse_args()

    # Determine file to view
    if args.latest:
        file_path = get_latest_model(args.output_dir)
        if not file_path:
            print(f"No STL or STEP files found in {args.output_dir}/")
            return 1
        print(f"Viewing latest: {file_path.name}")
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return 1
    else:
        parser.print_help()
        return 1

    # View
    print(f"\n🔧 Engineering Hub - 3D Viewer")
    print(f"   File: {file_path.name}")
    print(f"   Size: {file_path.stat().st_size / 1024:.1f} KB")

    if args.native:
        if not view_native(file_path):
            view_web(file_path)
    else:
        view_web(file_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
