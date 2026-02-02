#!/usr/bin/env python3
"""
CAD Agent - Natural Language to CadQuery Code Generation

This agent converts natural language part descriptions into executable
CadQuery Python code, then generates CAD exports (STEP, STL, etc.).

Architecture:
    User Description → LLM (Claude) → CadQuery Code → Wrapper → Exports

Usage:
    from src.agents.cad_agent import CADAgent

    agent = CADAgent()
    result = agent.generate("Create a 50mm cube with rounded edges")
    print(result.code)
    print(result.output_files)

Requirements:
    - anthropic (Claude API) or ollama (local LLM)
    - cadquery-ocp, cadquery (for execution)
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path

# Try to import LLM clients
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class CADGenerationResult:
    """Result from CAD agent generation"""
    success: bool
    description: str
    code: str
    parameters: dict = field(default_factory=dict)
    output_files: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "description": self.description,
            "code": self.code,
            "parameters": self.parameters,
            "output_files": self.output_files,
            "metadata": self.metadata,
            "error": self.error
        }


# System prompt for CAD code generation
CAD_SYSTEM_PROMPT = """You are a CadQuery expert. Your task is to convert natural language
descriptions of mechanical parts into executable CadQuery Python code.

RULES:
1. Always output valid Python code that uses CadQuery
2. Start with `import cadquery as cq`
3. Store the final result in a variable called `result`
4. Use named constants for ALL dimensions at the top of the code
5. Add comments explaining non-obvious operations
6. Use metric units (millimeters) unless specified otherwise
7. Apply appropriate fillets/chamfers for manufacturability
8. Use standard hole sizes for fasteners (M3=3.2mm, M4=4.3mm, M5=5.3mm clearance)

STANDARD REFERENCES:
- NEMA 17 motor: 42.3mm face, 31mm hole spacing, M3 holes, 22mm center bore
- NEMA 23 motor: 56.4mm face, 47.1mm hole spacing, M5 holes
- 2020 extrusion: 20x20mm profile, 6mm T-slot, M5 hardware
- 3030 extrusion: 30x30mm profile, 8mm T-slot, M6 hardware

COMMON PATTERNS:

Box with fillets:
```python
result = cq.Workplane("XY").box(W, H, D).edges().fillet(R)
```

Mounting holes pattern:
```python
result = (
    cq.Workplane("XY")
    .box(W, H, D)
    .faces(">Z").workplane()
    .rect(HOLE_SPACING_X, HOLE_SPACING_Y, forConstruction=True)
    .vertices()
    .hole(HOLE_DIA)
)
```

Shell (enclosure):
```python
result = cq.Workplane("XY").box(W, H, D).faces(">Z").shell(-WALL)
```

OUTPUT FORMAT:
Return ONLY the Python code, no markdown fences, no explanations before or after.
The code must be directly executable."""


# Prompt template for generation
GENERATION_PROMPT = """Create CadQuery code for the following part:

{description}

Additional requirements:
- Make all dimensions parametric (use named constants)
- The result must be stored in a variable called `result`
- Include appropriate fillets for 3D printing (minimum 0.5mm on sharp edges)
- Add mounting features if the part needs to be attached to something

Generate the Python code:"""


class CADAgent:
    """
    Agent that converts natural language to CadQuery code.

    Supports multiple LLM backends:
    - Claude (Anthropic API)
    - Ollama (local LLMs)
    - Direct code (bypass LLM for testing)
    """

    def __init__(
        self,
        backend: Literal["claude", "ollama", "direct"] = "claude",
        model: str = "claude-sonnet-4-20250514",
        ollama_url: str = "http://localhost:11434",
        output_dir: Optional[Path] = None
    ):
        """
        Initialize CAD Agent.

        Args:
            backend: LLM backend to use
            model: Model name (claude-sonnet-4-20250514, llama3, codellama, etc.)
            ollama_url: Ollama API URL if using local LLM
            output_dir: Directory for generated files
        """
        self.backend = backend
        self.model = model
        self.ollama_url = ollama_url
        self.output_dir = Path(output_dir) if output_dir else Path("./output")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize client based on backend
        if backend == "claude":
            if not ANTHROPIC_AVAILABLE:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
            self.client = anthropic.Anthropic()
        elif backend == "ollama":
            if not HTTPX_AVAILABLE:
                raise RuntimeError("httpx package not installed. Run: pip install httpx")
            self.client = None  # Use httpx directly
        else:
            self.client = None

    def _call_claude(self, prompt: str) -> str:
        """Call Claude API for code generation."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=CAD_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API for code generation."""
        import httpx

        response = httpx.post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": self.model,
                "prompt": f"{CAD_SYSTEM_PROMPT}\n\n{prompt}",
                "stream": False
            },
            timeout=120.0
        )
        response.raise_for_status()
        return response.json()["response"]

    def _generate_code(self, description: str) -> str:
        """Generate CadQuery code from description using configured LLM."""
        prompt = GENERATION_PROMPT.format(description=description)

        if self.backend == "claude":
            return self._call_claude(prompt)
        elif self.backend == "ollama":
            return self._call_ollama(prompt)
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    def _clean_code(self, code: str) -> str:
        """Clean generated code - remove markdown fences, etc."""
        # Remove markdown code fences
        code = re.sub(r'^```python\s*\n?', '', code, flags=re.MULTILINE)
        code = re.sub(r'^```\s*\n?', '', code, flags=re.MULTILINE)

        # Remove any leading/trailing whitespace
        code = code.strip()

        # Ensure import statement
        if not code.startswith("import"):
            code = "import cadquery as cq\n\n" + code

        return code

    def _extract_parameters(self, code: str) -> dict:
        """Extract parameter constants from generated code."""
        params = {}

        # Match lines like: WIDTH = 50  or  HOLE_DIA = 3.2
        pattern = r'^([A-Z][A-Z0-9_]*)\s*=\s*([0-9.]+)'

        for match in re.finditer(pattern, code, re.MULTILINE):
            name = match.group(1)
            value = float(match.group(2))
            params[name] = value

        return params

    def _execute_code(
        self,
        code: str,
        output_name: str,
        formats: list[str] = ["STEP", "STL"]
    ) -> tuple[list[str], dict]:
        """
        Execute CadQuery code and export results.

        Returns:
            Tuple of (output_files, metadata)
        """
        try:
            from src.tools.cadquery_wrapper import CadQueryWrapper

            wrapper = CadQueryWrapper(output_dir=self.output_dir)
            result = wrapper.generate(
                code=code,
                output_name=output_name,
                formats=formats
            )

            output_files = [result.output_file] if result.output_file else []
            metadata = {
                "bounding_box": result.bounding_box,
                "volume": result.volume,
                "surface_area": result.surface_area
            }

            return output_files, metadata

        except ImportError:
            # CadQuery not available, return code only
            return [], {"note": "CadQuery not installed - code generated but not executed"}
        except Exception as e:
            return [], {"error": str(e)}

    def generate(
        self,
        description: str,
        output_name: Optional[str] = None,
        formats: list[str] = ["STEP", "STL"],
        execute: bool = True
    ) -> CADGenerationResult:
        """
        Generate CAD from natural language description.

        This is the main entry point for the CAD Agent.

        Args:
            description: Natural language description of the part
            output_name: Base name for output files (auto-generated if not provided)
            formats: Export formats (STEP, STL, DXF, SVG)
            execute: Whether to execute code and generate files

        Returns:
            CADGenerationResult with code, files, and metadata
        """
        # Generate output name if not provided
        if not output_name:
            # Create slug from description
            slug = re.sub(r'[^a-z0-9]+', '_', description.lower())[:30]
            output_name = f"part_{slug}"

        try:
            # Generate code via LLM
            raw_code = self._generate_code(description)
            code = self._clean_code(raw_code)
            parameters = self._extract_parameters(code)

            # Execute if requested
            output_files = []
            metadata = {}

            if execute:
                output_files, metadata = self._execute_code(code, output_name, formats)

            return CADGenerationResult(
                success=True,
                description=description,
                code=code,
                parameters=parameters,
                output_files=output_files,
                metadata=metadata
            )

        except Exception as e:
            return CADGenerationResult(
                success=False,
                description=description,
                code="",
                error=str(e)
            )

    def generate_from_template(
        self,
        template_name: str,
        parameters: dict,
        output_name: Optional[str] = None
    ) -> CADGenerationResult:
        """
        Generate CAD from a predefined template with custom parameters.

        Args:
            template_name: Name of template (nema17_mount, enclosure, bracket, etc.)
            parameters: Dict of parameter values to override
            output_name: Base name for output files

        Returns:
            CADGenerationResult
        """
        templates = self._get_templates()

        if template_name not in templates:
            return CADGenerationResult(
                success=False,
                description=f"Template: {template_name}",
                code="",
                error=f"Unknown template: {template_name}. Available: {list(templates.keys())}"
            )

        template = templates[template_name]

        # Merge default parameters with provided ones
        merged_params = {**template["defaults"], **parameters}

        # Format template code with parameters
        code = template["code"].format(**merged_params)

        # Execute
        if not output_name:
            output_name = f"{template_name}_{hash(str(parameters)) % 10000}"

        output_files, metadata = self._execute_code(code, output_name)

        return CADGenerationResult(
            success=True,
            description=f"Template: {template_name}",
            code=code,
            parameters=merged_params,
            output_files=output_files,
            metadata=metadata
        )

    def _get_templates(self) -> dict:
        """Get available parametric templates."""
        return {
            "box": {
                "description": "Simple box with optional fillets",
                "defaults": {"WIDTH": 50, "HEIGHT": 30, "DEPTH": 20, "FILLET": 2},
                "code": """import cadquery as cq

WIDTH = {WIDTH}
HEIGHT = {HEIGHT}
DEPTH = {DEPTH}
FILLET = {FILLET}

result = (
    cq.Workplane("XY")
    .box(WIDTH, HEIGHT, DEPTH)
    .edges()
    .fillet(FILLET)
)
"""
            },
            "nema17_mount": {
                "description": "NEMA 17 stepper motor mounting plate",
                "defaults": {"THICKNESS": 5, "FILLET": 2},
                "code": """import cadquery as cq

# NEMA 17 standard dimensions
NEMA17_SIZE = 42.3
NEMA17_HOLE_SPACING = 31
NEMA17_CENTER_BORE = 22
M3_CLEARANCE = 3.2
THICKNESS = {THICKNESS}
FILLET = {FILLET}

result = (
    cq.Workplane("XY")
    .box(NEMA17_SIZE, NEMA17_SIZE, THICKNESS)
    .faces(">Z")
    .workplane()
    .rect(NEMA17_HOLE_SPACING, NEMA17_HOLE_SPACING, forConstruction=True)
    .vertices()
    .hole(M3_CLEARANCE)
    .faces(">Z")
    .workplane()
    .hole(NEMA17_CENTER_BORE)
    .edges("|Z")
    .fillet(FILLET)
)
"""
            },
            "enclosure": {
                "description": "Electronics enclosure with removable lid",
                "defaults": {"WIDTH": 100, "DEPTH": 60, "HEIGHT": 40, "WALL": 2},
                "code": """import cadquery as cq

WIDTH = {WIDTH}
DEPTH = {DEPTH}
HEIGHT = {HEIGHT}
WALL = {WALL}

# Create shell
result = (
    cq.Workplane("XY")
    .box(WIDTH, DEPTH, HEIGHT)
    .faces(">Z")
    .shell(-WALL)
)
"""
            },
            "bracket_l": {
                "description": "L-shaped mounting bracket",
                "defaults": {"BASE_WIDTH": 40, "BASE_DEPTH": 30, "WALL_HEIGHT": 35, "THICKNESS": 4, "HOLE_DIA": 5},
                "code": """import cadquery as cq

BASE_WIDTH = {BASE_WIDTH}
BASE_DEPTH = {BASE_DEPTH}
WALL_HEIGHT = {WALL_HEIGHT}
THICKNESS = {THICKNESS}
HOLE_DIA = {HOLE_DIA}

result = (
    cq.Workplane("XY")
    # Base plate
    .box(BASE_WIDTH, BASE_DEPTH, THICKNESS)
    # Vertical wall
    .faces(">Y")
    .workplane()
    .transformed(offset=(0, WALL_HEIGHT/2 - THICKNESS/2, 0))
    .box(BASE_WIDTH, WALL_HEIGHT, THICKNESS)
    # Base mounting holes
    .faces("<Z")
    .workplane()
    .rect(BASE_WIDTH - 10, BASE_DEPTH - 10, forConstruction=True)
    .vertices()
    .hole(HOLE_DIA)
    # Fillet the L-joint
    .edges("|Z")
    .edges(">Y")
    .fillet(THICKNESS * 0.8)
)
"""
            }
        }

    def list_templates(self) -> dict:
        """List available templates with descriptions."""
        templates = self._get_templates()
        return {
            name: {
                "description": t["description"],
                "parameters": list(t["defaults"].keys()),
                "defaults": t["defaults"]
            }
            for name, t in templates.items()
        }


# CLI interface
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="CAD Agent - Natural Language to CadQuery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate from description (requires Claude API key)
  python cad_agent.py "Create a 50mm cube with 5mm rounded edges"

  # Use a template
  python cad_agent.py --template nema17_mount --params '{"THICKNESS": 8}'

  # List available templates
  python cad_agent.py --list-templates

  # Use local LLM (Ollama)
  python cad_agent.py --backend ollama --model codellama "Create a bracket"
        """
    )

    parser.add_argument("description", nargs="?", help="Part description")
    parser.add_argument("--template", "-t", help="Use a predefined template")
    parser.add_argument("--params", "-p", help="Template parameters as JSON")
    parser.add_argument("--list-templates", action="store_true", help="List available templates")
    parser.add_argument("--backend", choices=["claude", "ollama", "direct"], default="claude")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Model to use")
    parser.add_argument("--output", "-o", help="Output name")
    parser.add_argument("--no-execute", action="store_true", help="Generate code only, don't execute")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.list_templates:
        agent = CADAgent(backend="direct")
        templates = agent.list_templates()

        if args.json:
            print(json.dumps(templates, indent=2))
        else:
            print("Available Templates:\n")
            for name, info in templates.items():
                print(f"  {name}:")
                print(f"    Description: {info['description']}")
                print(f"    Parameters: {', '.join(info['parameters'])}")
                print(f"    Defaults: {info['defaults']}")
                print()
        return 0

    if not args.description and not args.template:
        parser.error("Either description or --template is required")

    try:
        agent = CADAgent(backend=args.backend, model=args.model)

        if args.template:
            params = json.loads(args.params) if args.params else {}
            result = agent.generate_from_template(
                args.template, params, output_name=args.output
            )
        else:
            result = agent.generate(
                args.description,
                output_name=args.output,
                execute=not args.no_execute
            )

        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"Success: {result.success}")
            if result.error:
                print(f"Error: {result.error}")
            else:
                print(f"\nGenerated Code:\n{'='*50}")
                print(result.code)
                print('='*50)
                if result.parameters:
                    print(f"\nParameters: {result.parameters}")
                if result.output_files:
                    print(f"\nOutput Files: {result.output_files}")
                if result.metadata:
                    print(f"\nMetadata: {result.metadata}")

        return 0 if result.success else 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
