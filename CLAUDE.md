# Engineering Hub - AI Assistant Instructions

This file contains instructions for AI assistants (Claude, etc.) working on this project.

---

## Project Overview

**Engineering Hub** is an AI-agentic engineering environment for the complete product lifecycle:
- **CAD**: CadQuery/Build123d (Python-based parametric modeling)
- **Analysis**: CalculiX (FEA), OpenFOAM (CFD), Gmsh (meshing)
- **Manufacturing**: PrusaSlicer, FreeCAD Path (G-code generation)

**Core Principle:** Text-centric tools that LLMs can generate and manipulate.

---

## CRITICAL: Progress File Management

### Always Read First

At the **start of every session**, read `PROGRESS.md` to understand:
- Current phase and status
- What's been completed
- What's next in the queue
- Any blockers or issues

```
Read PROGRESS.md before doing any work
```

### Always Update After Work

At the **end of every session** or after **significant work**, update `PROGRESS.md`:

1. **Update "Last Updated" date** at the top
2. **Update "Current State" section** - move completed items, add new next items
3. **Update "Phase Progress" checkboxes** - mark completed tasks
4. **Add to "Session Notes"** - brief summary of what was done

### Session Note Format

```markdown
### YYYY-MM-DD - Brief Title
- Bullet point of what was accomplished
- Another accomplishment
- Any issues encountered

**Next session should:**
1. First priority task
2. Second priority task
```

---

## Key Architecture Decisions

These decisions have been made - don't revisit unless explicitly asked:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CAD Engine | CadQuery | Pure Python, LLM-friendly, parametric |
| Analysis | CalculiX + OpenFOAM | Text-based configs, open source |
| Platform | Docker | Cross-platform reproducibility |
| API | FastAPI | Python ecosystem, async, OpenAPI docs |
| Meshing | Gmsh | Python API, text-based .geo files |

---

## Code Locations

| Component | Location | Description |
|-----------|----------|-------------|
| CAD Wrapper | `src/tools/cadquery_wrapper.py` | Text → CAD generation |
| API | `src/api/main.py` | REST endpoints |
| Docker | `docker/` | All Dockerfiles and compose |
| Examples | `examples/` | Sample parametric models |
| Models Library | `models/` | Reusable parametric components |

---

## Common Tasks

### Test the Docker Stack
```bash
cd docker
docker-compose build
docker-compose up -d
curl http://localhost:8000/health
```

### Run CadQuery Wrapper (Native)
```bash
pip install cadquery-ocp cadquery
python src/tools/cadquery_wrapper.py --example cube --output test_cube
```

### Run Example Model
```bash
python examples/simple_bracket.py
# Output goes to output/simple_bracket.step and .stl
```

### API Endpoints
- `GET /health` - Service health check
- `GET /cad/examples` - List example models
- `POST /cad/generate` - Generate CAD from code
- `GET /cad/job/{id}` - Get job status
- `GET /cad/download/{id}/{format}` - Download output

---

## Development Guidelines

1. **Text-First**: All tools must work via text/code input for LLM compatibility
2. **Parametric**: All dimensions should be variables, not hardcoded
3. **Export Multiple Formats**: Always support STEP (CAD exchange) and STL (3D printing)
4. **Docker for Dependencies**: Heavy tools (CalculiX, OpenFOAM) run in containers
5. **API for Everything**: All operations should be accessible via REST API

---

## Phase 2 Guidance (CAD Agent)

When starting Phase 2, focus on:
1. Create `src/agents/cad_agent.py`
2. Use Claude/LLM to generate CadQuery code from natural language
3. Integrate with existing `cadquery_wrapper.py`
4. Build a library of common parametric components in `models/`

Example agent flow:
```
User: "Create a box 50x30x20mm with 5mm fillets and 4 M4 mounting holes"
  ↓
CAD Agent: Generates CadQuery Python code
  ↓
CadQuery Wrapper: Executes code, exports STEP/STL
  ↓
Result: Files + metadata (volume, bounding box)
```

---

## Remember

- **Always update PROGRESS.md** when work is complete
- **Read PROGRESS.md first** when starting a new session
- **Commit frequently** with descriptive messages
- **Test Docker builds** before marking infrastructure complete
