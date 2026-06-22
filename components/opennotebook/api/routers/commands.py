from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from api.command_service import CommandService

router = APIRouter()


class CommandExecutionRequest(BaseModel):
    command: str = Field(
        ..., description="Command function name (e.g., 'process_text')"
    )
    app: str = Field(..., description="Application name (e.g., 'open_notebook')")
    input: Dict[str, Any] = Field(..., description="Arguments to pass to the command")


class CommandJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class CommandJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


@router.post("/commands/jobs", response_model=CommandJobResponse)
async def execute_command(request: CommandExecutionRequest):
    """
    Submit a command for background processing.
    Returns immediately with job ID for status tracking.

    Example request:
    {
        "command": "process_text",
        "app": "open_notebook",
        "input": {
            "text": "Hello world",
            "operation": "uppercase"
        }
    }
    """
    raise HTTPException(
        status_code=403,
        detail=(
            "Generic command submission is disabled. "
            "Use the dedicated source, insight, embedding, or podcast API endpoints."
        ),
    )


@router.get("/commands/jobs/{job_id}", response_model=CommandJobStatusResponse)
async def get_command_job_status(job_id: str):
    """Get the status of a specific command job"""
    try:
        status_data = await CommandService.get_command_status(job_id)
        # The generic command-status endpoint is used by the frontend for polling.
        # Do not expose arbitrary command result payloads here because results can
        # contain user content from source/note processing jobs.
        status_data["result"] = None
        status_data["progress"] = None
        return CommandJobStatusResponse(**status_data)

    except Exception as e:
        logger.error(f"Error fetching job status: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch job status"
        )


@router.get("/commands/jobs", response_model=List[Dict[str, Any]])
async def list_command_jobs(
    command_filter: Optional[str] = Query(None, description="Filter by command name"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Maximum number of jobs to return"),
):
    """List command jobs with optional filtering"""
    try:
        jobs = await CommandService.list_command_jobs(
            command_filter=command_filter, status_filter=status_filter, limit=limit
        )
        return jobs

    except Exception as e:
        logger.error(f"Error listing command jobs: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to list command jobs"
        )


@router.delete("/commands/jobs/{job_id}")
async def cancel_command_job(job_id: str):
    """Cancel a running command job"""
    raise HTTPException(
        status_code=403,
        detail="Generic command cancellation is disabled.",
    )


@router.get("/commands/registry/debug")
async def debug_registry():
    """Debug endpoint to see what commands are registered"""
    raise HTTPException(
        status_code=403,
        detail="Command registry debug endpoint is disabled.",
    )
