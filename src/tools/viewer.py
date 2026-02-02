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
