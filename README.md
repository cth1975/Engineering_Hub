# Engineering Hub

An AI-agentic engineering environment for the complete product lifecycle: **CAD → Analysis → Manufacturing**.

Built entirely on open-source tools, designed from the ground up for AI agent automation.

## Vision

Natural language descriptions become manufactured parts through an automated pipeline:

```
"Create a bracket that mounts to a 2020 extrusion
 and holds a NEMA 17 stepper motor"
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                    ENGINEERING HUB                            │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐   │
│  │  CAD    │ →  │ Analysis│ →  │  Review │ →  │   CAM   │   │
│  │ Agent   │    │  Agent  │    │  Gate   │    │  Agent  │   │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
   G-code / STL / STEP ready for fabrication
```

## Project Requirements

| Dimension | Specification |
|-----------|---------------|
| **Domain** | Multi-domain (mechanical, electrical, structural) |
| **Scale** | Mixed (handheld to architectural) |
| **Manufacturing** | 3D printing, CNC, laser cutting, injection molding |
| **Output Formats** | G-code, STL, STEP, DXF, SVG |
| **Analysis** | FEA (structural/thermal), CFD |
| **Team Size** | Small team (2-5 engineers) |
| **Platform** | Cross-platform via Docker (dev on macOS/Linux/Windows) |

## Technology Stack

### Core Principle: Text-Centric Tools

AI agents work best with text. Every tool in this stack uses text-based configuration, scripts, or code—enabling LLMs to generate, modify, and understand the entire pipeline.

### CAD Layer

| Tool | Purpose | Why |
|------|---------|-----|
| **[CadQuery](https://cadquery.readthedocs.io/)** | Primary parametric CAD | Pure Python, LLM-friendly, parametric by design |
| **[Build123d](https://build123d.readthedocs.io/)** | Alternative/modern CAD | CadQuery evolution, cleaner API, better type hints |
| **[cq-editor](https://github.com/CadQuery/CQ-editor)** | Visual feedback | Real-time preview of CadQuery scripts |
| **[FreeCAD](https://www.freecad.org/)** | Integration platform | Python API, analysis workbench, CAM |

**Example CadQuery Code (AI-Generated):**
```python
import cadquery as cq

# NEMA 17 motor mount bracket for 2020 extrusion
bracket = (
    cq.Workplane("XY")
    .box(42, 42, 5)  # NEMA 17 face plate size
    .faces(">Z")
    .workplane()
    .rect(31, 31, forConstruction=True)  # NEMA 17 hole pattern
    .vertices()
    .hole(3.2)  # M3 clearance holes
    .faces(">Z")
    .workplane()
    .hole(22.5)  # Center bore for motor shaft
    .faces("<Y")
    .workplane()
    .transformed(offset=(0, 0, -10))
    .rect(20, 6, forConstruction=True)
    .vertices()
    .hole(5.2)  # 2020 extrusion T-slot holes
)

cq.exporters.export(bracket, "nema17_bracket.step")
```

### Analysis Layer

| Tool | Domain | Integration |
|------|--------|-------------|
| **[CalculiX](http://www.calculix.de/)** | FEA (structural, thermal) | Text-based input (.inp), batch processing |
| **[OpenFOAM](https://openfoam.org/)** | CFD | Dictionary configs, fully scriptable |
| **[Elmer](https://www.elmerfem.org/)** | Multi-physics FEM | Text config, Python bindings |
| **[FreeCAD FEM](https://wiki.freecad.org/FEM_Workbench)** | Integrated analysis | Wraps CalculiX/Elmer, Python API |
| **[Gmsh](https://gmsh.info/)** | Meshing | Text-based .geo files, Python API |
| **[ParaView](https://www.paraview.org/)** | Visualization | Post-processing, Python scripting |

### Manufacturing Layer (CAM)

| Tool | Output | Use Case |
|------|--------|----------|
| **[FreeCAD Path](https://wiki.freecad.org/Path_Workbench)** | G-code | CNC milling, routing |
| **[PrusaSlicer CLI](https://github.com/prusa3d/PrusaSlicer)** | G-code | FDM 3D printing |
| **[SuperSlicer](https://github.com/supermerill/SuperSlicer)** | G-code | Advanced 3D printing |
| **[PyCAM](https://pycam.sourceforge.net/)** | G-code | Python-scriptable CAM |
| **[Inkscape CLI](https://inkscape.org/)** | DXF/SVG | Laser cutting profiles |
| **[CAMotics](https://camotics.org/)** | Simulation | G-code verification |

### Infrastructure

| Tool | Purpose |
|------|---------|
| **Docker** | Containerized, reproducible environment |
| **Python 3.11+** | Primary scripting language |
| **FastAPI** | Agent API layer |
| **Git** | Version control for parametric models |
| **PostgreSQL** | Project/revision metadata |
| **MinIO** | File storage (STEP, STL, G-code) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENGINEERING HUB                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         AGENT LAYER                                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │
│  │  │   CAD    │  │ Analysis │  │  Review  │  │   CAM    │            │   │
│  │  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │            │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘            │   │
│  └───────┼─────────────┼─────────────┼─────────────┼────────────────────┘   │
│          │             │             │             │                        │
│  ┌───────┴─────────────┴─────────────┴─────────────┴────────────────────┐   │
│  │                         API LAYER (FastAPI)                          │   │
│  │  /generate-cad  │  /run-analysis  │  /generate-cam  │  /export      │   │
│  └───────┬─────────────┬─────────────┬─────────────┬────────────────────┘   │
│          │             │             │             │                        │
│  ┌───────┴─────────────┴─────────────┴─────────────┴────────────────────┐   │
│  │                         TOOL LAYER                                   │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │
│  │  │ CadQuery │  │CalculiX │  │  Gmsh    │  │ Slicer   │            │   │
│  │  │ Build123d│  │ OpenFOAM │  │ FreeCAD  │  │ FreeCAD  │            │   │
│  │  │          │  │ Elmer    │  │ FEM      │  │ Path     │            │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         STORAGE LAYER                                │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                          │   │
│  │  │ PostgreSQL│  │  MinIO   │  │   Git    │                          │   │
│  │  │ (metadata)│  │ (files)  │  │ (models) │                          │   │
│  │  └──────────┘  └──────────┘  └──────────┘                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Foundation (Current)
- [x] Project planning and architecture
- [x] Docker development environment
- [x] CadQuery wrapper with CLI
- [x] FastAPI orchestration layer
- [x] Export to STL/STEP/DXF
- [ ] Test Docker build and verify stack

### Phase 2: CAD Agent
- [ ] Natural language → CadQuery code generation
- [ ] Parametric model library (common components)
- [ ] Version control integration for models
- [ ] Visual preview pipeline

### Phase 3: Analysis Integration
- [ ] Gmsh meshing automation
- [ ] CalculiX FEA integration
- [ ] Results interpretation agent
- [ ] Design iteration loop

### Phase 4: Manufacturing Pipeline
- [ ] Slicer integration (3D printing)
- [ ] FreeCAD Path integration (CNC)
- [ ] DXF generation (laser cutting)
- [ ] G-code validation

### Phase 5: Full Automation
- [ ] End-to-end pipeline orchestration
- [ ] Human approval gates
- [ ] Batch processing
- [ ] API for external integrations

## Directory Structure

```
Engineering_Hub/
├── README.md                 # This file
├── docker/                   # Docker configurations
│   ├── Dockerfile.cadquery   # CadQuery environment
│   ├── Dockerfile.analysis   # FEA/CFD environment
│   ├── Dockerfile.cam        # CAM/slicer environment
│   └── docker-compose.yml    # Full stack orchestration
├── src/                      # Source code
│   ├── agents/               # AI agent implementations
│   │   ├── cad_agent.py
│   │   ├── analysis_agent.py
│   │   └── cam_agent.py
│   ├── api/                  # FastAPI endpoints
│   ├── tools/                # Tool wrappers
│   │   ├── cadquery_wrapper.py
│   │   ├── calculix_wrapper.py
│   │   └── slicer_wrapper.py
│   └── utils/                # Shared utilities
├── models/                   # Parametric model library
│   ├── fasteners/
│   ├── enclosures/
│   └── brackets/
├── examples/                 # Example projects
├── tests/                    # Test suite
└── docs/                     # Additional documentation
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Git

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/Engineering_Hub.git
cd Engineering_Hub

# Start the development environment
docker-compose up -d

# Run a simple CAD generation
python src/tools/cadquery_wrapper.py "Create a 50mm cube with 10mm corner fillets"
```

### Development Setup (Native)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install CadQuery
pip install cadquery-ocp cadquery

# Install cq-editor for visualization
pip install cq-editor

# Run cq-editor
cq-editor
```

## Platform Recommendations

| Platform | Best For | Notes |
|----------|----------|-------|
| **Linux (Ubuntu 22.04+)** | Production, heavy analysis | Best OpenFOAM/CalculiX support |
| **macOS** | Development | Native CadQuery, Docker for analysis |
| **Windows + WSL2** | Development | Run Linux tools in WSL, native cq-editor |
| **Docker** | All platforms | Recommended for reproducibility |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is open source. See [LICENSE](LICENSE) for details.

## Resources

### Documentation
- [CadQuery Documentation](https://cadquery.readthedocs.io/)
- [Build123d Documentation](https://build123d.readthedocs.io/)
- [FreeCAD Wiki](https://wiki.freecad.org/)
- [CalculiX Manual](http://www.dhondt.de/ccx_2.20.pdf)
- [OpenFOAM User Guide](https://www.openfoam.com/documentation/user-guide)

### Tutorials
- [CadQuery Examples](https://cadquery.readthedocs.io/en/latest/examples.html)
- [FreeCAD FEM Tutorial](https://wiki.freecad.org/FEM_tutorial)
- [OpenFOAM Tutorials](https://www.openfoam.com/documentation/tutorial-guide)

### Community
- [CadQuery Discord](https://discord.gg/Bj9AQPsCfx)
- [FreeCAD Forum](https://forum.freecad.org/)
- [OpenFOAM Forum](https://www.cfd-online.com/Forums/openfoam/)

---

*Built with AI-first principles for the age of agentic engineering.*
