# Scheduler API & Service Orchestrator

## Project Summary
A lightweight task orchestrator with a FastAPI backend and Streamlit frontend. It features an APScheduler engine with an agenda-style calendar timeline, card/task monitoring and a backend script parser that extracts MCP tools to schedule them or execute them in APScheduler engine.

---

## Features
The system offers granular and robust management of the task lifecycle:
* **Automated Script Parsing & Tool Extraction:** Automatically scan and parse existing Python scripts to extract functions, making them instantly available for scheduling.
* **Flexible Task Scheduling:** Easily schedule recurrent automated tasks (Cron-style) or one-off, punctual executions directly via an intuitive GUI.
* **Granular Task Control (Micro-Management):** Take full control over your workload lifecycle with the ability to pause/resume tasks, skip specific executions, and apply temporary or permanent runtime modifications.
* **Visual Monitoring & Timeline:** Keep track of your orchestrated services using an agenda-style calendar timeline and interactive task/card monitoring views.

---

## Visual Interface

> **[Insert screenshot here]**

> **[Insert YouTube demo link here]**

---

## Project Architecture

The project is designed modularly, separating the user interface, control API, scheduling engine, and utility scripts:

```text
├── main.py                    # Unified startup script (Backend + Frontend)
├── fast_api.py                # REST API entry point (FastAPI)
├── scheduler.py               # Task scheduling engine (APScheduler)
├── config_loader.py           # Loads environment variables
├── gui.py                     # User graphical interface (Streamlit legacy)
├── index.html                 # User graphical interface
├── mcp_server.py              # Server / Module containing test tasks (FastMCP)
├── tests/conftest.py          # Integration tests suite (Pytest)
├── tests/run_tests.py         # Integration tests suite (Pytest)
├── tests/test_integration.py  # Integration tests suite (Pytest)
├── tasks.json                 # Local database of registered scheduled tasks (generated)
├── config.json                # Global configuration settings (generated)
└── function_docs.json         # Index of functions executable by the scheduler (generated)
```

---

## Installation Guide

### Prerequisites
* **Python 3.12** or later installed.
* `pip` package manager.

### Step 1: Clone Repository
Retrieve project files in your local workspace:
```bash
git clone <repository_url>
cd <project_name>
```
### Step 2: Install Dependencies
Install all required libraries using `pip`:

```bash
pip install fastapi uvicorn apscheduler streamlit requests pytest
```
### Step 3: Generate Index of Eligible Functions
Before starting the scheduler, you must index Python functions you want to schedule. By default, the generator searches in mcp_server.py. Simply run python generate_function_docs.py command. This produces the function_docs.json file required for proper application operation.

---

## Deployment

### Local Execution (Development)
To launch both FastAPI backend (port 8888) and Streamlit interface (port 8501) with a single command, run python main.py:
* Graphical interface access: http://localhost:8501
* API interactive documentation access (Swagger UI): http://localhost:8888/docs

### Production Deployment (Systemd Service under Linux)
To ensure the application runs in background and automatically restarts on crash or server reboot, create a Systemd service.

1. Create /etc/systemd/system/scheduler.service file with following configuration:
```bash
[Unit]
Description=Task Orchestration & Scheduling Service
After=network.target

[Service]
Type=simple
User=votre_utilisateur
WorkingDirectory=/chemin/complet/vers/le/projet
ExecStart=/chemin/complet/vers/votre/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

2. Enable and start service with commands:
```bash
sudo systemctl daemon-reload
sudo systemctl enable scheduler.service
sudo systemctl start scheduler.service
```

---

## Available APIs List

| Method | Endpoint | Tag | Description | Request (Body / Params) |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/` | General | Check API health status. | *None* |
| **POST** | `/shutdown` | General | Gracefully shuts down scheduler in background. | *None* |
| **GET** | `/config` | Config | Retrieves active global configuration. | *None* |
| **POST** | `/config` | Config | Updates number of days to display (`days_to_show`). | `{"days_to_show": int}` |
| **GET** | `/tasks` | Tasks | Lists all scheduled persisted tasks. | *None* |
| **POST** | `/tasks` | Tasks | Adds and schedules new task (`cron` or `date`). | JSON Model `Task` |
| **PUT** | `/tasks/{task_id}` | Tasks | Modifies existing task. | JSON Model `Task` |
| **DELETE** | `/tasks/{task_id}` | Tasks | Permanently removes a task from system. | *None* |
| **POST** | `/tasks/{task_id}/pause` | Tasks | Temporarily suspends execution of a task. | *None* |
| **POST** | `/tasks/{task_id}/resume` | Tasks | Resumes execution of previously suspended task. | *None* |
| **POST** | `/tasks/{task_id}/reschedule` | Tasks | Sets temporary scheduling with expiration date. | `{"new_cron_params": dict, "end_date": str}` |
| **POST** | `/tasks/{task_id}/reset-reschedule` | Tasks | Cancels rescheduling and restores original Cron. | *None* |
| **POST** | `/tasks/{task_id}/skip/{number}` | Tasks | Adds or removes a skip occurrence number. | URL Parameter `number` (int) |
| **DELETE** | `/tasks/{task_id}/skip/{number}` | Tasks | Manually removes specific skip entry. | URL Parameter `number` (int) |
| **GET** | `/tasks/{task_id}/next-execution` | Tasks | Returns next execution date in ISO format. | *None* |

---

## Testing Guide

> **[Placeholder: Write your manual or automated testing instructions here.]**
> 
> *Example scenario to document:*
> 1. *How to run integration tests suite with `pytest run_tests.py`.*
> 2. *Example HTTP `curl` requests for manually creating a task via terminal.*
> 3. *Expected behavior to observe in console during execution of a test task.*

## Future Evolution Roadmap

* **Global Configuration:**
  * Dedicated GET/POST /config endpoints.
  * Adjustment forms in index.html.

* **Dynamic Python Scripts:**
  * Runtime importation of external modules via system paths.
  * Multi-file indexing with generate_function_docs.py.
  * Strict signature and arguments validation.

* **Local LLM (Ollama / Llama.cpp):**
  * Reporting: Audit and diagnostic report on scheduler state.
  * Management: Add, edit and remove tasks in natural language.

* **Discord Bridge & Tier Services:**
  * Endpoint POST /integrations/execute-action for immediate forced triggers.

* **Debug & Force Update:**
  * "Force Update" button with st.rerun() in UI.
  * Endpoint POST /scheduler/reload all system.
