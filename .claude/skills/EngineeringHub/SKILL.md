---
name: EngineeringHub
description: Full engineering pipeline - from description to manufactured part
triggers:
  - engineering hub
  - full pipeline
  - end to end
  - complete workflow
  - design and manufacture
  - make me a
  - build me a
  - i need a part
---

# Engineering Hub Skill

Orchestrate the complete engineering pipeline from natural language to manufacturing-ready output.

## Capabilities

- End-to-end: Description → CAD → Analysis → Manufacturing
- Human approval gates at each stage
- Iterative refinement based on analysis results
- Multi-format output for different manufacturing methods

## Usage

```
/engineeringhub I need a bracket to mount a NEMA 17 motor to 2020 extrusion,
                will hold 2kg load, needs to be 3D printable in PETG

/engineeringhub Design a 100x60x40mm electronics enclosure with ventilation,
                needs mounting ears, laser cut from 3mm acrylic
```

## Full Pipeline Workflow

### Stage 1: Requirements Capture

Parse the request to extract:

```yaml
Part:
  name: "NEMA 17 Motor Bracket"
  description: "Mounts NEMA 17 to 2020 extrusion"

Constraints:
  mechanical:
    - load: 2kg (~20N)
    - mounting: 2020 T-slot
  manufacturing:
    - method: 3D printing
    - material: PETG

Interfaces:
  - NEMA 17 mounting pattern (31mm, M3)
  - 2020 extrusion T-slot (M5)
```

### Stage 2: CAD Generation

Invoke CAD skill:
```
/cad [generated requirements]
```

Produces:
- `output/bracket.step` - CAD exchange
- `output/bracket.stl` - For analysis/printing
- CadQuery source code

**APPROVAL GATE**: Show user the model, get confirmation before analysis.

### Stage 3: Analysis (if structural requirements)

Invoke Analysis skill:
```
/analysis Run stress analysis on bracket.step with 20N load at motor mount
```

Produces:
- Max stress report
- Safety factor
- Displacement check

**Decision Point**:
- Safety factor < 2: Redesign (back to CAD)
- Safety factor 2-4: Acceptable for non-critical
- Safety factor > 4: Consider optimizing (lighter)

**APPROVAL GATE**: Show analysis results, confirm proceed to manufacturing.

### Stage 4: Manufacturing Output

Invoke Manufacturing skill:
```
/manufacturing Slice bracket.stl for PETG, functional profile
```

Produces:
- `output/bracket.gcode`
- Print time estimate
- Filament usage

**APPROVAL GATE**: Confirm ready to print/manufacture.

### Stage 5: Documentation

Generate summary:

```markdown
# NEMA 17 Motor Bracket

## Specifications
- Material: PETG
- Weight: 15g
- Print time: 45 min
- Safety factor: 3.2

## Files
- CAD: bracket.step
- Mesh: bracket.stl
- G-code: bracket.gcode

## Analysis Summary
- Max stress: 8.6 MPa (yield: 28 MPa)
- Max displacement: 0.1mm
- Status: PASS

## Print Settings
- Layer height: 0.2mm
- Infill: 40%
- Perimeters: 4
```

## Approval Gates

The pipeline has built-in approval gates. At each gate:

1. **Present Results**: Show what was created
2. **Ask for Approval**: Explicit yes/no
3. **Handle Feedback**:
   - Approved: Continue to next stage
   - Changes requested: Return to previous stage
   - Rejected: Start over with new requirements

```
🔲 Stage 1: Requirements → [CAPTURED]
   ↓
🔲 Stage 2: CAD Model
   └─ APPROVAL GATE: "Does this model look correct?"
   ↓
🔲 Stage 3: Analysis
   └─ APPROVAL GATE: "Safety factor is 3.2. Proceed?"
   ↓
🔲 Stage 4: Manufacturing
   └─ APPROVAL GATE: "G-code ready. Print time: 45min. Start?"
   ↓
✅ Stage 5: Complete
```

## Quick Mode

For simple parts without structural requirements:

```
/engineeringhub quick: 50mm cube with rounded edges, 3D print PLA
```

Skips analysis, goes directly: CAD → Manufacturing

## Iteration Examples

**Too weak (analysis failed):**
```
Analysis: Safety factor 1.2 (FAIL - need >2)
Action: Increase wall thickness from 3mm to 5mm
Re-run: CAD → Analysis
Result: Safety factor 2.8 (PASS)
```

**Manufacturing constraint:**
```
CAD: 0.5mm wall feature
Manufacturing: Cannot print <0.8mm walls
Action: Increase to 1mm minimum
Re-run: CAD (modified) → Manufacturing
```

## Project Files

| Stage | Output Files |
|-------|--------------|
| CAD | `output/*.step`, `output/*.stl` |
| Analysis | `output/*.frd`, `output/*.dat` |
| Manufacturing | `output/*.gcode`, `output/*.dxf` |
| Documentation | `output/README.md` |

## Related Skills

- `/cad` - CAD generation only
- `/analysis` - Analysis only
- `/manufacturing` - Manufacturing output only

This skill orchestrates all three in sequence with approval gates.
