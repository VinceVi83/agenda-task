import secrets
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
import sys
import os
import asyncio
from config_loader import cfg, setup_logging, Utils

import logging
setup_logging()
logger = logging.getLogger(__name__)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scheduler import scheduler, MCPManager

app = FastAPI(
    title="Scheduler API",
    description="API to manage scheduled tasks",
    version="1.0.0"
)

security = HTTPBasic()

def check_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, cfg.system.user)
    correct_password = secrets.compare_digest(credentials.password, cfg.system.password)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Identifiants incorrects",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

manager = None
current_scheduler = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

SERVER_IP = Utils.get_server_ip()

class Task(BaseModel):
    """Scheduled task definition model

    Role: Represents a scheduled task with its configuration and execution parameters.

    Methods:
        id (str): Unique identifier for the task.
        function (str): Function name to execute when triggered.
        trigger_type (str): Type of trigger mechanism (cron, date-based).
        description (Optional[str]): Human-readable description of the task.
        cron (Optional[Dict[str, str]]): Cron expression parameters if applicable.
        run_date (Optional[str]): Specific execution date for one-time tasks.
        args (Optional[List[Any]]): Arguments to pass to the function.
        status (Optional[str]): Current execution status ("ok", "error").
        state (Optional[str]): Task lifecycle state ("active", "paused").
        skip_next (Optional[List[int]]): List of executions to skip.
        end_date (Optional[str]): Scheduled termination date for task.
        hidden (Optional[str]): Visibility flag for UI display.
    """
    id: str
    function: str
    trigger_type: str
    description: Optional[str] = ""
    cron: Optional[Dict[str, str]] = None
    run_date: Optional[str] = None
    args: Optional[List[Any]] = []
    status: Optional[str] = "ok"
    state: Optional[str] = "active"
    skip_next: Optional[List[int]] = []
    end_date: Optional[str] = None
    hidden: Optional[str] = None

class ConfigResponse(BaseModel):
    """Configuration response model

    Role: Returns current scheduler configuration settings to clients.

    Methods:
        days_to_show (int): Number of days in the calendar view to display.
        show_hidden (Optional[bool]): Whether hidden tasks are visible.
    """
    days_to_show: int
    show_hidden: Optional[bool] = False

class ConfigRequest(BaseModel):
    """Configuration update request model

    Role: Accepts configuration changes from clients for scheduler settings.

    Methods:
        days_to_show (int): Number of calendar days to display in UI.
        show_hidden (Optional[bool]): Flag to toggle hidden task visibility.
    """
    days_to_show: int
    show_hidden: Optional[bool] = False

class TaskResponse(BaseModel):
    """Task operation response model

    Role: Standardized response for all task-related API operations.

    Methods:
        success (bool): Indicates whether the operation completed successfully.
        message (str): Human-readable status or error message.
        task_id (Optional[str]): Identifier of affected task if applicable.
        next_execution (Optional[str]): Next scheduled execution timestamp.
    """
    success: bool
    message: str
    task_id: Optional[str] = None
    next_execution: Optional[str] = None

class TaskListResponse(BaseModel):
    """Task list response model

    Role: Returns complete list of all configured tasks in the scheduler.

    Methods:
        tasks (List[Dict[str, Any]]): List of task dictionaries with full details.
    """
    tasks: List[Dict[str, Any]]

class RescheduleRequest(BaseModel):
    """Task rescheduling request model

    Role: Accepts new scheduling parameters for modifying existing task timing.

    Methods:
        new_cron_params (Dict[str, str]): Updated cron expression values.
        end_date (str): Optional termination date to set on the task.
    """
    new_cron_params: Dict[str, str]
    end_date: str

class SkipRequest(BaseModel):
    """Task skip request model

    Role: Accepts instructions for skipping future executions of a scheduled task.

    Methods:
        number (int): Number of upcoming executions to skip.
    """
    number: int

@app.get("/", tags=["General"])
def read_root(username: str = Depends(check_credentials)):
    return {"message": "Scheduler API is running", "status": "ok"}

@app.get("/config", tags=["Config"], response_model=ConfigResponse)
def get_config(username: str = Depends(check_credentials)):
    return {"days_to_show": current_scheduler.days_to_show}

@app.post("/config", tags=["Config"])
def update_config(request: ConfigRequest, username: str = Depends(check_credentials)):
    try:
        current_scheduler.save_config(request.days_to_show)
        return {"success": True, "days_to_show": current_scheduler.days_to_show}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/tasks", tags=["Tasks"], response_model=TaskListResponse)
def list_tasks(username: str = Depends(check_credentials)):
    tasks = current_scheduler.tasks
    return {"tasks": tasks}

@app.post("/tasks", tags=["Tasks"], response_model=TaskResponse)
def add_task(task: Task, username: str = Depends(check_credentials)):
    try:
        task_dict = task.dict()
        current_scheduler.add_task(task_dict)
        next_execution = current_scheduler._next_execution(task.id)
        return {
            "success": True,
            "message": f"Task {task.id} added successfully",
            "task_id": task.id,
            "next_execution": next_execution
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error adding task: {str(e)}")

@app.put("/tasks/{task_id}", tags=["Tasks"], response_model=TaskResponse)
def modify_task(task_id: str, task: Task, username: str = Depends(check_credentials)):
    try:
        if task.id != task_id:
            raise HTTPException(status_code=400, detail="Task ID in path and body must match")
        task_dict = task.dict()
        current_scheduler.modify_task(task_dict)
        next_execution = current_scheduler._next_execution(task_id)
        return {
            "success": True,
            "message": f"Task {task_id} modified successfully",
            "task_id": task_id,
            "next_execution": next_execution
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error modifying task: {str(e)}")

@app.post("/tasks/{task_id}/pause", tags=["Tasks"], response_model=TaskResponse)
def pause_task(task_id: str, username: str = Depends(check_credentials)):
    try:
        success = current_scheduler.pause_task(task_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Could not pause task {task_id}")
        next_execution = current_scheduler._next_execution(task_id)
        return {
            "success": True,
            "message": f"Task {task_id} paused successfully",
            "task_id": task_id,
            "next_execution": next_execution
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error pausing task: {str(e)}")

@app.post("/tasks/{task_id}/resume", tags=["Tasks"], response_model=TaskResponse)
def resume_task(task_id: str, username: str = Depends(check_credentials)):
    try:
        success = current_scheduler.resume_task(task_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Could not resume task {task_id}")
        next_execution = current_scheduler._next_execution(task_id)
        return {
            "success": True,
            "message": f"Task {task_id} resumed successfully",
            "task_id": task_id,
            "next_execution": next_execution
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error resuming task: {str(e)}")

@app.delete("/tasks/{task_id}", tags=["Tasks"], response_model=TaskResponse)
def remove_task(task_id: str, username: str = Depends(check_credentials)):
    current_scheduler.remove_task(task_id, save=True)
    return {
        "success": True,
        "message": f"Task {task_id} removed successfully",
        "task_id": task_id
    }

@app.post("/tasks/{task_id}/reschedule", tags=["Tasks"], response_model=TaskResponse)
def reschedule_task(task_id: str, request: RescheduleRequest):
    try:
        current_scheduler.reschedule(
            task_id=task_id,
            new_cron_params=request.new_cron_params,
            end_date=request.end_date
        )
        next_execution = current_scheduler._next_execution(task_id)
        return {
            "success": True,
            "message": f"Task {task_id} rescheduled successfully",
            "task_id": task_id,
            "next_execution": next_execution
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error rescheduling task: {str(e)}")

@app.post("/tasks/{task_id}/reset-reschedule", tags=["Tasks"], response_model=TaskResponse)
def reset_reschedule(task_id: str, username: str = Depends(check_credentials)):
    try:
        current_scheduler.reset_reschedule(task_id)
        next_execution = current_scheduler._next_execution(task_id)
        return {
            "success": True,
            "message": f"Task {task_id} reschedule reset successfully",
            "task_id": task_id,
            "next_execution": next_execution
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error resetting reschedule: {str(e)}")

@app.post("/tasks/{task_id}/skip/{number}", tags=["Tasks"], response_model=TaskResponse)
def add_skip(task_id: str, number: int, username: str = Depends(check_credentials)):
    try:
        current_scheduler.add_skip(task_id, number)
        return {
            "success": True,
            "message": f"Skip number {number} added to task {task_id}",
            "task_id": task_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error adding skip: {str(e)}")

@app.delete("/tasks/{task_id}/skip/{number}", tags=["Tasks"], response_model=TaskResponse)
def remove_skip(task_id: str, number: int, username: str = Depends(check_credentials)):
    try:
        current_scheduler.remove_skip(task_id, number)
        return {
            "success": True,
            "message": f"Skip number {number} removed from task {task_id}",
            "task_id": task_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error removing skip: {str(e)}")

@app.get("/tasks/{task_id}/next-execution", tags=["Tasks"])
def get_next_execution(task_id: str, username: str = Depends(check_credentials)):
    try:
        next_execution = current_scheduler._next_execution(task_id)
        if next_execution:
            return {
                "task_id": task_id,
                "next_execution": next_execution,
                "success": True
            }
        else:
            return {
                "task_id": task_id,
                "next_execution": None,
                "success": False,
                "message": "Task not found or no next execution scheduled"
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error getting next execution: {str(e)}")

@app.post("/shutdown", tags=["General"])
def shutdown_scheduler(username: str = Depends(check_credentials)):
    try:
        current_scheduler.shutdown()
        return {"success": True, "message": "Scheduler shutdown successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error shutting down scheduler: {str(e)}")

from fastapi.responses import FileResponse

@app.get("/gui", tags=["General"])
def serve_gui(username: str = Depends(check_credentials)):
    return FileResponse("index.html")

@app.get("/function_docs.json", tags=["General"])
def serve_function_docs(username: str = Depends(check_credentials)):
    if os.path.exists("function_docs.json"):
        from fastapi.responses import JSONResponse
        with open("function_docs.json", "r", encoding="utf-8") as f:
            return JSONResponse(content=json.load(f))
    return JSONResponse(content={"functions": {}}, status_code=404)

@app.get("/api/config", tags=["General"])
def get_ui_config(username: str = Depends(check_credentials)):
    return {"api_url": f"https://{SERVER_IP}:{cfg.system.port}"}

@app.on_event("startup")
@app.get("/api/config", tags=["General"])
def get_ui_config(username: str = Depends(check_credentials)):
    return {"api_url": f"https://{SERVER_IP}:{cfg.system.port}"}

@app.on_event("startup")
async def startup_event():
    global manager, current_scheduler
    loop = asyncio.get_running_loop()
    manager = MCPManager()
    current_scheduler = scheduler(manager)
    current_scheduler.set_event_loop(loop) 
    logger.info("Starting initialization...")
    await manager.initialize_all_functions()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0", 
        port=cfg.system.port,
        ssl_keyfile=cfg.system.key_pem,
        ssl_certfile=cfg.system.cert_pem,
        log_config=None
    )
