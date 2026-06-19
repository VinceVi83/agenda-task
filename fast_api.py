from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scheduler import current_scheduler

app = FastAPI(
    title="Scheduler API",
    description="API to manage scheduled tasks",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Task(BaseModel):
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

class TaskResponse(BaseModel):
    success: bool
    message: str
    task_id: Optional[str] = None
    next_execution: Optional[str] = None

class TaskListResponse(BaseModel):
    tasks: List[Dict[str, Any]]

class RescheduleRequest(BaseModel):
    new_cron_params: Dict[str, str]
    end_date: str

class SkipRequest(BaseModel):
    number: int

class ConfigResponse(BaseModel):
    days_to_show: int

class ConfigRequest(BaseModel):
    days_to_show: int

@app.get("/", tags=["General"])
def read_root():
    return {"message": "Scheduler API is running", "status": "ok"}

@app.get("/config", tags=["Config"], response_model=ConfigResponse)
def get_config():
    return {"days_to_show": current_scheduler.days_to_show}

@app.post("/config", tags=["Config"])
def update_config(request: ConfigRequest):
    try:
        current_scheduler.save_config(request.days_to_show)
        return {"success": True, "days_to_show": current_scheduler.days_to_show}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/tasks", tags=["Tasks"], response_model=TaskListResponse)
def list_tasks():
    tasks = current_scheduler.tasks
    return {"tasks": tasks}

@app.post("/tasks", tags=["Tasks"], response_model=TaskResponse)
def add_task(task: Task):
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
def modify_task(task_id: str, task: Task):
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
def pause_task(task_id: str):
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
def resume_task(task_id: str):
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
def remove_task(task_id: str):
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
def reset_reschedule(task_id: str):
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
def add_skip(task_id: str, number: int):
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
def remove_skip(task_id: str, number: int):
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
def get_next_execution(task_id: str):
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
def shutdown_scheduler():
    try:
        current_scheduler.shutdown()
        return {"success": True, "message": "Scheduler shutdown successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error shutting down scheduler: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
