#!/usr/bin/env python3
"""
Engineering Hub API - FastAPI orchestration layer

Provides REST API for AI agents to interact with CAD, Analysis, and CAM services.

Endpoints:
    POST /cad/generate     - Generate CAD from CadQuery code
    POST /cad/export       - Export existing model to different formats
    GET  /cad/examples     - List available example models
    GET  /health           - Service health check
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal
from pathlib import Path
import uuid
import json

app = FastAPI(
    title="Engineering Hub API",
    description="AI-agentic engineering environment API",
    version="0.1.0",
)


# Request/Response Models
class CADGenerateRequest(BaseModel):
    """Request to generate CAD from code"""
    code: str = Field(..., description="CadQuery Python code to execute")
    output_name: Optional[str] = Field(None, description="Base name for output files")
    formats: list[str] = Field(
        default=["STEP", "STL"],
        description="Export formats (STEP, STL, DXF, SVG, etc.)"
    )
    result_var: str = Field(
        default="result",
        description="Variable name containing the result in the code"
    )


class CADGenerateResponse(BaseModel):
    """Response from CAD generation"""
    success: bool
    message: str
    job_id: str
    output_files: list[str] = []
    bounding_box: Optional[dict] = None
    volume: Optional[float] = None
    surface_area: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    services: dict[str, str]
    version: str


# In-memory job storage (replace with database in production)
jobs: dict[str, dict] = {}


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health and dependencies"""
    services = {
        "api": "healthy",
        "cadquery": "unknown",
        "analysis": "unknown",
        "cam": "unknown"
    }

    # Check CadQuery availability
    try:
        import cadquery as cq
        services["cadquery"] = "healthy"
    except ImportError:
        services["cadquery"] = "not_installed"

    return HealthResponse(
        status="healthy" if services["cadquery"] == "healthy" else "degraded",
        services=services,
        version="0.1.0"
    )


@app.get("/cad/examples")
async def list_examples():
    """List available example CAD models"""
    try:
        from src.tools.cadquery_wrapper import EXAMPLE_MODELS
        return {
            "examples": list(EXAMPLE_MODELS.keys()),
            "details": {
                name: {"lines": len(code.strip().split('\n'))}
                for name, code in EXAMPLE_MODELS.items()
            }
        }
    except ImportError:
        return {"examples": [], "error": "CadQuery wrapper not available"}


@app.post("/cad/generate", response_model=CADGenerateResponse)
async def generate_cad(request: CADGenerateRequest, background_tasks: BackgroundTasks):
    """
    Generate CAD model from CadQuery code.

    This endpoint executes CadQuery Python code and exports the result
    to the requested formats.

    Example request:
    ```json
    {
        "code": "result = cq.Workplane('XY').box(50, 50, 50)",
        "output_name": "my_cube",
        "formats": ["STEP", "STL"]
    }
    ```
    """
    job_id = str(uuid.uuid4())[:8]
    output_name = request.output_name or f"model_{job_id}"

    try:
        from src.tools.cadquery_wrapper import CadQueryWrapper

        wrapper = CadQueryWrapper(output_dir=Path("./output"))
        result = wrapper.generate(
            code=request.code,
            output_name=output_name,
            formats=request.formats,
            result_var=request.result_var
        )

        # Store job result
        jobs[job_id] = result.to_dict()

        return CADGenerateResponse(
            success=result.success,
            message=result.message,
            job_id=job_id,
            output_files=[result.output_file] if result.output_file else [],
            bounding_box=result.bounding_box,
            volume=result.volume,
            surface_area=result.surface_area,
            error=result.error
        )

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="CadQuery not available. Run in Docker container."
        )
    except Exception as e:
        return CADGenerateResponse(
            success=False,
            message=f"Generation failed: {str(e)}",
            job_id=job_id,
            error=str(e)
        )


@app.get("/cad/job/{job_id}")
async def get_job(job_id: str):
    """Get status of a CAD generation job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/cad/download/{job_id}/{format}")
async def download_output(job_id: str, format: str):
    """Download generated CAD file"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    output_file = job.get("output_file")

    if not output_file or not Path(output_file).exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        path=output_file,
        filename=Path(output_file).name,
        media_type="application/octet-stream"
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    print("Engineering Hub API starting...")
    Path("./output").mkdir(exist_ok=True)
    print("Output directory ready")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
