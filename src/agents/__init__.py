# AI Agents for Engineering Hub
"""
Agent implementations for automated CAD, Analysis, and CAM workflows.

Agents:
    - CADAgent: Natural language to CadQuery code generation
    - AnalysisAgent: FEA/CFD setup and result interpretation
    - ManufacturingAgent: G-code, DXF output generation

Usage:
    from src.agents import CADAgent, AnalysisAgent, ManufacturingAgent

    # Generate CAD from description
    cad = CADAgent()
    result = cad.generate("Create a 50mm cube with rounded edges")

    # Run structural analysis
    analysis = AnalysisAgent()
    result = analysis.run_structural_analysis("part.step", material="aluminum_6061")

    # Generate G-code for printing
    mfg = ManufacturingAgent()
    result = mfg.slice_for_printing("part.stl", profile="functional")
"""

from .cad_agent import CADAgent, CADGenerationResult
from .analysis_agent import AnalysisAgent, AnalysisResult, MATERIALS as ANALYSIS_MATERIALS
from .manufacturing_agent import (
    ManufacturingAgent,
    ManufacturingResult,
    PRINT_PROFILES,
    MATERIALS as PRINT_MATERIALS
)

__all__ = [
    "CADAgent",
    "CADGenerationResult",
    "AnalysisAgent",
    "AnalysisResult",
    "ANALYSIS_MATERIALS",
    "ManufacturingAgent",
    "ManufacturingResult",
    "PRINT_PROFILES",
    "PRINT_MATERIALS",
]
