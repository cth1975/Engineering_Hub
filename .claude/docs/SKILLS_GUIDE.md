# Engineering Hub - Skills Guide

This project includes local Claude Code skills for AI-assisted engineering workflows.

## What Are Skills?

Skills are domain-specific instructions that enhance Claude's ability to work with this project. When you clone this repository and use Claude Code, these skills are automatically available.

## Available Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| **CAD** | `/cad` | Generate 3D models from descriptions |
| **Analysis** | `/analysis` | Run FEA/CFD simulations |
| **Manufacturing** | `/manufacturing` | Create G-code, DXF for fabrication |
| **EngineeringHub** | `/engineeringhub` | Full pipeline orchestration |

## Quick Start

### Generate a Part
```
/cad Create a 50x30x20mm box with 3mm fillets and 4 corner M4 mounting holes
```

### Run Analysis
```
/analysis Check stress on bracket.step with 50N downward load
```

### Prepare for Manufacturing
```
/manufacturing Slice part.stl for PLA, 0.2mm layers, 20% infill
```

### Full Pipeline
```
/engineeringhub I need a phone stand that holds at 60 degrees,
                3D printable, should support 300g
```

## Skill Locations

```
.claude/
├── skills/
│   ├── CAD/
│   │   └── SKILL.md         # CadQuery generation
│   ├── Analysis/
│   │   └── SKILL.md         # CalculiX FEA
│   ├── Manufacturing/
│   │   └── SKILL.md         # G-code, DXF output
│   └── EngineeringHub/
│       └── SKILL.md         # Full pipeline
└── docs/
    └── SKILLS_GUIDE.md      # This file
```

## How Skills Work

1. **Triggers**: Each skill has trigger words. Saying "create a bracket" triggers the CAD skill.

2. **Workflow**: Skills contain step-by-step instructions for Claude to follow.

3. **Tools**: Skills reference project tools like `src/tools/cadquery_wrapper.py`.

4. **Output**: All generated files go to the `output/` directory (gitignored).

## Customizing Skills

You can modify skills for your needs:

1. Edit the relevant `SKILL.md` file
2. Add new patterns, materials, or workflows
3. Skills are version-controlled with the project

## Creating New Skills

To add a new skill:

1. Create directory: `.claude/skills/YourSkill/`
2. Create `SKILL.md` with frontmatter:

```yaml
---
name: YourSkill
description: What it does
triggers:
  - keyword1
  - keyword2
---

# Skill content...
```

## Dependencies

Skills assume these tools are available:

| Tool | Install | Purpose |
|------|---------|---------|
| CadQuery | `pip install cadquery` | CAD generation |
| Docker | System install | Analysis/CAM containers |
| Python 3.11+ | System install | All scripts |

## Examples by Use Case

### Prototyping (Quick)
```
/cad quick box 50x50x50
/manufacturing slice for PLA draft
```

### Functional Part
```
/engineeringhub Motor mount for NEMA 17, holds 5kg, PETG, need analysis
```

### Laser Cut Enclosure
```
/cad Enclosure 150x100x50mm, finger joints for 3mm plywood
/manufacturing Export DXF for laser cutting
```

### CNC Part
```
/cad Aluminum bracket 100x50x10mm with pockets
/manufacturing Generate CNC toolpaths, 6mm end mill
```

## Troubleshooting

### Skill Not Triggering
- Check trigger words in SKILL.md frontmatter
- Try explicit: `/cad ...` instead of just describing

### CadQuery Errors
- Verify installation: `python -c "import cadquery"`
- Check generated code syntax
- Simplify geometry and retry

### Docker Issues
- Ensure Docker running: `docker ps`
- Build containers: `cd docker && docker-compose build`
- Check logs: `docker-compose logs analysis`

## Further Reading

- [CadQuery Documentation](https://cadquery.readthedocs.io/)
- [CalculiX Manual](http://www.dhondt.de/)
- [PrusaSlicer CLI](https://help.prusa3d.com/article/command-line-interface_272806)
- Main project README: `README.md`
- Progress tracking: `PROGRESS.md`
