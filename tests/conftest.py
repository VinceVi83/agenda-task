import pytest
import os
import time
import requests
import subprocess
import shutil
import json
import atexit
import signal
import threading
import sys

from config_loader import cfg_agendata_task

import logging
logger = logging.getLogger(__name__)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    start = time.perf_counter()
    yield
    duration = time.perf_counter() - start
    with open(f"/tmp/perf_{item.name}.log", "w") as f:
        f.write(f"{duration:.2f}")

API_BASE_URL = f'http://localhost:{cfg_agendata_task.system.port}'
TASKS_JSON = 'tasks.json'
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_backup_file = None
_parent_tasks_json = None
_is_load_test = False
_interrupted = False


def pytest_addoption(parser):
    parser.addoption(
        "--load-test", 
        action="store_true", 
        default=False,
        help="Run tests without cleaning up between them (for load testing)"
    )
    parser.addoption(
        "--disable-server-fixture",
        action="store_true",
        default=False,
        help="Disable the FastAPI server fixture (for parallel execution)"
    )

@pytest.fixture(scope="session", autouse=True)
def fastapi_server(request):
    disable_server_fixture = request.config.getoption("--disable-server-fixture")
    if disable_server_fixture:
        yield
        return
    
    parent_tasks_json = os.path.join(PARENT_DIR, TASKS_JSON)
    backup_file = None
    
    if os.path.exists(parent_tasks_json):
        backup_file = parent_tasks_json + '.bak'
        shutil.copy(parent_tasks_json, backup_file)
    
    cmd = [sys.executable, 'fast_api.py']
    cwd = PARENT_DIR
    
    process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    time.sleep(2)
    if process.poll() is not None:
        stderr_content = process.stderr.read()
        restore_tasks_json()
        process.kill()
        pytest.exit("Server process terminated unexpectedly")
    
    ready = False
    for _ in range(30):
        try:
            if requests.get(f'{API_BASE_URL}/', timeout=1).status_code == 200:
                ready = True
                break
        except:
            time.sleep(1)
    
    if not ready:
        restore_tasks_json(backup_file, parent_tasks_json)
        process.kill()
        pytest.exit("The server did not start.")
        
    yield

    process.terminate()
    process.wait()
    
    register_cleanup(backup_file, parent_tasks_json, request.config.getoption("--load-test"))

def restore_tasks_json():
    global _backup_file, _parent_tasks_json, _is_load_test
    
    if _backup_file and os.path.exists(_backup_file):
        if _is_load_test:
            os.remove(_backup_file)
        else:
            if os.path.exists(_parent_tasks_json):
                os.remove(_parent_tasks_json)
            shutil.move(_backup_file, _parent_tasks_json)

def register_cleanup(backup_file, parent_tasks_json, is_load_test):
    global _backup_file, _parent_tasks_json, _is_load_test, _interrupted
    _backup_file = backup_file
    _parent_tasks_json = parent_tasks_json
    _is_load_test = is_load_test
    _interrupted = False
    atexit.register(restore_tasks_json)
    
    def monitor_interrupt():
        global _interrupted
        try:
            while True:
                time.sleep(0.1)
                if _interrupted:
                    restore_tasks_json()
                    os._exit(1)
        except KeyboardInterrupt:
            _interrupted = True

    monitor_thread = threading.Thread(target=monitor_interrupt, daemon=True)
    monitor_thread.start()
    
    def handle_signal(signum, frame):
        global _interrupted
        _interrupted = True
        
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

def cleanup_test_tasks_before():
    parent_tasks_json = os.path.join(PARENT_DIR, TASKS_JSON)
    lock_file = os.path.join(PARENT_DIR, 'test_interrupted.lock')
    
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            backup_file = parent_tasks_json + '.bak'
            if os.path.exists(backup_file):
                if os.path.exists(parent_tasks_json):
                    os.remove(parent_tasks_json)
                shutil.move(backup_file, parent_tasks_json)
                
                try:
                    with open(parent_tasks_json, 'r') as f:
                        tasks = json.load(f)
                    
                    cleaned_tasks = [task for task in tasks if not task['id'].startswith('test_')]
                    
                    if len(cleaned_tasks) != len(tasks):
                        with open(parent_tasks_json, 'w') as f:
                            json.dump(cleaned_tasks, f, indent=2)
                except Exception as e:
                    logger.warning(f"Warning: Could not clean test tasks from recovered file: {e}")
        except Exception as e:
            pass
    
    if os.path.exists(parent_tasks_json):
        try:
            with open(parent_tasks_json, 'r') as f:
                tasks = json.load(f)
            
            cleaned_tasks = [task for task in tasks if not task['id'].startswith('test_')]
            
            if len(cleaned_tasks) != len(tasks):
                with open(parent_tasks_json, 'w') as f:
                    json.dump(cleaned_tasks, f, indent=2)
        except Exception as e:
            pass

@pytest.fixture(autouse=True)
def cleanup_test_files(request):
    yield

def make_api_request(method, endpoint, data=None):
    url = f'{API_BASE_URL}{endpoint}'
    try:
        if method == 'POST': return requests.post(url, json=data, timeout=10)
        if method == 'GET': return requests.get(url, timeout=10)
        if method == 'DELETE': return requests.delete(url, timeout=10)
    except Exception as e:
        logger.error(f"Error in make_api_request({method}, {endpoint}): {e}")
        return None

def wait_for_file(filepath, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(filepath): return True
        time.sleep(1)
    return False
