import subprocess
import sys
import time
import os
import ast
import json
from datetime import datetime
from typing import List, Dict, Any
from config_loader import cfg_agendata_task, setup_logging

import logging
setup_logging()
logger = logging.getLogger(__name__)

def extract_function_info(node: ast.FunctionDef) -> Dict[str, Any]:
    func_info = {
        'description': '',
        'args': [],
        'kwargs': []
    }

    if ast.get_docstring(node):
        func_info['description'] = ast.get_docstring(node).strip()

    for arg in node.args.args:
        arg_info = {
            'name': arg.arg,
            'example': f"'{arg.arg}_value'"
        }
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                pass
            elif isinstance(arg.annotation, ast.Subscript):
                pass
        
        func_info['args'].append(arg_info)
    
    for arg in node.args.kwonlyargs:
        arg_info = {
            'name': arg.arg,
            'example': f"'{arg.arg}_value'"
        }
        func_info['kwargs'].append(arg_info)
    
    return func_info


def analyze_python_file(filepath: str) -> Dict[str, Dict[str, Any]]:
    functions = {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            source_code = file.read()
        tree = ast.parse(source_code)
        module_name = os.path.splitext(os.path.basename(filepath))[0]
        module_dir = os.path.dirname(os.path.abspath(filepath))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith('_'):
                    continue
                full_name = f"{module_name}.{node.name}"
                func_info = extract_function_info(node)
                func_info['module'] = module_name
                func_info['path'] = module_dir
                functions[full_name] = func_info
        
    except Exception as e:
        logger.warning(f"Warning: Could not analyze {filepath}: {e}")
    
    return functions


def generate_function_docs(files: List[str]) -> Dict[str, Any]:
    all_functions = {}
    
    for filepath in files:
        if os.path.exists(filepath) and filepath.endswith('.py'):
            logger.info(f"Analyzing {filepath}...")
            functions = analyze_python_file(filepath)
            all_functions.update(functions)
        else:
            logger.warning(f"Warning: File {filepath} does not exist or is not a Python file")
    
    function_docs = {
        'version': '1.0',
        'generated_at': datetime.now().isoformat(),
        'functions': all_functions
    }
    
    return function_docs


def generate_doc():
    default_files = cfg_agendata_task.system.mcp
    function_docs = generate_function_docs(default_files)
    output_file = 'function_docs.json'
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(function_docs, f, indent=4, ensure_ascii=False)
        logger.info(f"Successfully generated {output_file}")
        logger.info(f"Found {len(function_docs['functions'])} functions")
    except Exception as e:
        logger.error(f"Error writing {output_file}: {e}")
        sys.exit(1)

def main():
    logger.info("Starting all orchestrator services...")
    generate_doc()
    backend_process = None
    frontend_process = None
    
    try:
        backend_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "fast_api:app", "--host", "0.0.0.0", "--port", f'{cfg_agendata_task.system.port}'],
            stdout=None,
            stderr=None
        )
        
        time.sleep(2)
        
        frontend_process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "gui.py"],
            stdout=None,
            stderr=None
        )
        
        while True:
            if backend_process.poll() is not None:
                logger.info("Backend stopped unexpectedly.")
                break
            if frontend_process.poll() is not None:
                logger.info("Frontend stopped unexpectedly.")
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
