import argparse
import os
import ast
import json
import sys
import contextlib
import subprocess
import time
import importlib
import asyncio
import nest_asyncio
from datetime import datetime
from typing import Any, Dict, List
from config_loader import cfg, setup_logging
from mcp import ClientSession
from mcp.client.sse import sse_client

import logging
setup_logging()
logger = logging.getLogger(__name__)

@contextlib.contextmanager
def change_dir(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)

def main():
    logger.info("Starting all orchestrator services...")
    backend_process = None
    frontend_process = None
    try:
        backend_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "fast_api:app", "--host", "0.0.0.0", "--port", f'{cfg.system.port}'],
            stdout=None,
            stderr=None
        )
        while True:
            if backend_process.poll() is not None:
                logger.info("Backend stopped unexpectedly.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if frontend_process and frontend_process.poll() is None:
            frontend_process.terminate()
        if backend_process and backend_process.poll() is None:
            backend_process.terminate()

if __name__ == "__main__":
    main()
