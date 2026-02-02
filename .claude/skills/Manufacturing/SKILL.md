---
name: Manufacturing
description: Generate manufacturing outputs - G-code for 3D printing and CNC, DXF for laser cutting
triggers:
  - manufacture
  - manufacturing
  - gcode
  - g-code
  - slice
  - print
  - 3d print
  - cnc
  - mill
  - laser
  - cut
  - cam
---

# Manufacturing Skill

Generate manufacturing-ready outputs from CAD models.

## Capabilities

- 3D printing G-code (via PrusaSlicer)
- CNC toolpaths (via FreeCAD Path) - future
- Laser cutting DXF/SVG profiles
- G-code validation and preview

## Usage

```
/manufacturing Slice model.stl for Prusa MK3S with 0.2mm layers
/manufacturing Generate DXF profile for laser cutting 3mm acrylic
/manufacturing Create G-code for CNC milling from model.step
```

## Prerequisites

Manufacturing tools require Docker:

```bash
cd docker
docker-compose up cam -d
```

## 3D Printing Workflow

### 1. Ensure STL Exists

From CAD skill, you should have:
```
output/model.stl
```

### 2. Configure Slicer

PrusaSlicer CLI options:

```bash
prusa-slicer \
  --load /path/to/printer.ini \
  --layer-height 0.2 \
  --fill-density 20% \
  --support-material \
  --output output/model.gcode \
  output/model.stl
```

### 3. Common Print Profiles

**Draft (Fast)**
```bash
--layer-height 0.3
--fill-density 15%
--perimeters 2
```

**Standard**
```bash
--layer-height 0.2
--fill-density 20%
--perimeters 3
```

**Strong (Functional)**
```bash
--layer-height 0.2
--fill-density 40%
--perimeters 4
--top-solid-layers 5
--bottom-solid-layers 5
```

**Fine (Visual)**
```bash
--layer-height 0.1
--fill-density 20%
--perimeters 3
```

### 4. Material Settings

| Material | Nozzle | Bed | Notes |
|----------|--------|-----|-------|
| PLA | 210°C | 60°C | Easy, good detail |
| PETG | 240°C | 80°C | Stronger, flexible |
| ABS | 250°C | 100°C | Needs enclosure |
| TPU | 230°C | 50°C | Flexible, slow print |

### 5. Return Results

Provide:
- G-code file path
- Estimated print time
- Estimated filament usage
- Layer count
- Any warnings (overhangs, supports needed)

## Laser Cutting Workflow

### 1. Generate 2D Profile

From CadQuery, create a 2D section:

```python
import cadquery as cq
from cadquery import exporters

# Create or load 3D model
model = cq.Workplane("XY").box(100, 50, 3)

# Get top face as 2D
profile = model.faces(">Z").wires().toPending()

# Export as DXF
exporters.exportDXF(profile, "output/profile.dxf")
```

Or use the wrapper:
```bash
python src/tools/cadquery_wrapper.py --code "..." --formats DXF SVG
```

### 2. DXF Considerations

- **Kerf compensation**: Laser removes material (typically 0.1-0.3mm)
- **Tab connections**: For parts that would fall through
- **Engraving vs cutting**: Different line colors/layers
- **Material thickness**: Match to design

### 3. Return Results

Provide:
- DXF/SVG file path
- Total cut length (for cost estimate)
- Bounding box size
- Material recommendations

## CNC Milling Workflow (Future - Phase 4)

### Planned Approach

1. Import STEP into FreeCAD
2. Use Path workbench for toolpath generation
3. Configure tools, speeds, feeds
4. Export G-code for specific machine

### Key Parameters

| Parameter | Description |
|-----------|-------------|
| Tool diameter | End mill size |
| Spindle speed | RPM |
| Feed rate | mm/min |
| Depth of cut | Per pass |
| Step over | For pocketing |

## G-code Validation

Before sending to machine:

```bash
# Visualize with CAMotics
camotics output/model.gcode

# Or use online validators
# https://ncviewer.com/
```

Check for:
- No collisions
- Reasonable travel moves
- Correct start/end positions
- Safe tool changes

## Files

- Dockerfile: `docker/Dockerfile.cam`
- STL input: `output/*.stl`
- G-code output: `output/*.gcode`
- DXF output: `output/*.dxf`
- SVG output: `output/*.svg`

## Integration with Analysis

Before manufacturing, consider:
1. Run stress analysis (Analysis skill)
2. Verify safety factor > 2 for functional parts
3. Check thermal requirements if heat-exposed
4. Document material choice rationale
