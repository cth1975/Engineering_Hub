---
name: CAD
description: Generate parametric CAD models from natural language descriptions using CadQuery
triggers:
  - cad
  - cadquery
  - create part
  - design part
  - make model
  - 3d model
  - parametric
  - bracket
  - enclosure
  - mount
---

# CAD Generation Skill

Generate parametric 3D CAD models from natural language descriptions.

## Capabilities

- Convert descriptions to CadQuery Python code
- Generate STEP, STL, DXF, SVG exports
- Calculate volume, surface area, bounding box
- Create parametric models with configurable dimensions

## Usage

```
/cad Create a 50mm cube with 5mm rounded edges
/cad Design a NEMA 17 motor mount for 2020 extrusion
/cad Make an enclosure 100x60x40mm with 2mm walls
```

## Workflow

When this skill is triggered:

### 1. Parse the Request

Extract from the user's description:
- **Shape type**: box, cylinder, bracket, enclosure, mount, etc.
- **Dimensions**: all measurements with units (assume mm if not specified)
- **Features**: holes, fillets, chamfers, patterns, cutouts
- **Constraints**: mounting patterns, standard sizes (NEMA, 2020 extrusion, etc.)

### 2. Generate CadQuery Code

Create Python code following these patterns:

```python
import cadquery as cq

# Always use named parameters for dimensions
WIDTH = 50
HEIGHT = 30
THICKNESS = 5

# Build the model with chained operations
result = (
    cq.Workplane("XY")
    .box(WIDTH, HEIGHT, THICKNESS)
    # Add features...
)
```

**Best Practices:**
- All dimensions as named constants at top
- Use `forConstruction=True` for reference geometry
- Chain operations fluently
- Comment non-obvious operations
- Use standard hole sizes (M3=3.2mm clearance, M4=4.3mm, M5=5.3mm)

### 3. Execute via Wrapper

Use the project's CadQuery wrapper:

```bash
# Option 1: Direct Python execution
python -c "
import cadquery as cq
# ... generated code ...
cq.exporters.export(result, 'output/model.step')
"

# Option 2: Via wrapper CLI
python src/tools/cadquery_wrapper.py --code "result = cq.Workplane('XY').box(50,50,50)" --output my_model

# Option 3: Via API (if running)
curl -X POST http://localhost:8000/cad/generate \
  -H "Content-Type: application/json" \
  -d '{"code": "result = cq.Workplane(\"XY\").box(50,50,50)", "formats": ["STEP", "STL"]}'
```

### 4. Return Results

Always provide:
- The generated CadQuery code (so user can modify)
- Export file paths
- Model properties (dimensions, volume)
- Suggestions for improvements or variations

## Common Patterns

### Box with Fillets
```python
result = cq.Workplane("XY").box(50, 30, 20).edges().fillet(3)
```

### Mounting Holes Pattern
```python
result = (
    cq.Workplane("XY")
    .box(50, 50, 5)
    .faces(">Z").workplane()
    .rect(40, 40, forConstruction=True)
    .vertices()
    .hole(3.2)  # M3 clearance
)
```

### Shell (Enclosure)
```python
result = (
    cq.Workplane("XY")
    .box(100, 60, 40)
    .faces(">Z")
    .shell(-2)  # 2mm wall thickness
)
```

### Extrusion Profile
```python
result = (
    cq.Workplane("XY")
    .moveTo(0, 0)
    .lineTo(20, 0)
    .lineTo(20, 10)
    .lineTo(10, 10)
    .lineTo(10, 20)
    .lineTo(0, 20)
    .close()
    .extrude(50)
)
```

### NEMA 17 Motor Mount
```python
NEMA17_SIZE = 42.3
NEMA17_HOLES = 31  # Hole spacing
NEMA17_BORE = 22   # Center bore

result = (
    cq.Workplane("XY")
    .box(NEMA17_SIZE, NEMA17_SIZE, 5)
    .faces(">Z").workplane()
    .rect(NEMA17_HOLES, NEMA17_HOLES, forConstruction=True)
    .vertices().hole(3.2)
    .faces(">Z").workplane()
    .hole(NEMA17_BORE)
)
```

## Standard References

| Component | Key Dimensions |
|-----------|---------------|
| NEMA 17 | 42.3mm face, 31mm hole spacing, M3 holes |
| NEMA 23 | 56.4mm face, 47.1mm hole spacing, M5 holes |
| 2020 Extrusion | 20x20mm, 6mm T-slot, M5 drop-in nuts |
| 3030 Extrusion | 30x30mm, 8mm T-slot, M6 drop-in nuts |
| M3 Clearance | 3.2mm hole |
| M4 Clearance | 4.3mm hole |
| M5 Clearance | 5.3mm hole |

## Error Handling

If CadQuery fails:
1. Check syntax errors in generated code
2. Verify geometry is valid (no zero-thickness, intersections)
3. Simplify the model and add features incrementally
4. Suggest alternative approaches

## Files

- Wrapper: `src/tools/cadquery_wrapper.py`
- API: `src/api/main.py`
- Examples: `examples/`
- Output: `output/` (gitignored)
