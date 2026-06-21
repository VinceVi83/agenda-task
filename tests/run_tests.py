import subprocess
import sys
import argparse
import glob
import os
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import fcntl
import time
import requests
import glob
import os

from config_loader import cfg_agendata_task, setup_logging
import logging
setup_logging()
logger = logging.getLogger(__name__)


def cleanup_test_files():
    test_files = glob.glob('/tmp/test_*.txt')
    perf_files = glob.glob('/tmp/perf_test_*.log')
    
    files_to_remove = test_files + perf_files
    
    for filepath in files_to_remove:
        try:
            os.remove(filepath)
        except Exception as e:
            pass

def run_single_test(test_num, load_test, parallel_mode=False):
    cmd = ['pytest', 'test_integration.py', '-v', '-s']
    
    if load_test:
        cmd.append('--load-test')
    if parallel_mode:
        cmd.append('-o')
        cmd.append('addopts=--disable-server-fixture')
    
    if test_num:
        test_mapping = {
            1: 'test_integration.py::test_1_one_shot_date_task',
            2: 'test_integration.py::test_2_cron_task_with_skip',
            3: 'test_integration.py::test_3_reschedule_with_expiry',
            4: 'test_integration.py::test_4_reschedule_with_skip',
            5: 'test_integration.py::test_5_reschedule_and_reset'
        }
        
        if test_num in test_mapping:
            cmd[1] = test_mapping[test_num]
        else:
            logger.info(f"Invalid test number: {test_num}")
            return False
    
    python_cmd = [sys.executable, '-m', 'pytest'] + cmd[1:]
    env = os.environ.copy()
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env['PYTHONPATH'] = parent_dir + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run(python_cmd, cwd=os.path.dirname(os.path.abspath(__file__)), env=env)
    
    return result.returncode == 0

def run_pytest_tests(test_num=None, load_test=False, parallel=False):
    if parallel and not test_num:
        logger.info("Starting FastAPI server for parallel tests...")
        server_process = start_fastapi_server()
        if server_process is None:
            return False
        
        try:
            logger.info("Running all tests in parallel...")
            test_numbers = [1, 2, 3, 4, 5]
            
            with ThreadPoolExecutor(max_workers=len(test_numbers)) as executor:
                futures = [executor.submit(run_single_test, num, load_test, True) for num in test_numbers]
                
                results = [future.result() for future in futures]
            
            passed = sum(results)
            failed = len(results) - passed
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Parallel Test Results: {passed} passed, {failed} failed")
            logger.info(f"{'='*60}")
            test_names = {
                1: 'ONE-SHOT DATE TASK',
                2: 'CRON TASK WITH SKIP',
                3: 'RESCHEDULE WITH EXPIRY',
                4: 'RESCHEDULE WITH SKIP',
                5: 'RESCHEDULE AND RESET'
            }
            
            logger.info("\nIndividual Test Results:")
            for i, (test_num, result) in enumerate(zip(test_numbers, results), 1):
                status = f"✅ Test {test_num} PASSED" if result else f"❌ Test {test_num} FAILED"
                logger.info(f"  Test {i}: {test_names[test_num]} - {status}")
            logger.info(f"\n{'='*60}")

            log_files = sorted(glob.glob('/tmp/perf_test_*.log'))

            for log_file in log_files:
                test_name = os.path.basename(log_file).replace('perf_test_', '').replace('.log', '')
                
                try:
                    with open(log_file, 'r') as f:
                        duration = f.read().strip()
                        logger.info(f"{test_name:<40} | {duration:<12}")
                except Exception as e:
                    logger.info(f"{test_name:<40} | Error reading")
            logger.info("="*60 + "\n")
            
            return all(results)
        finally:
            stop_fastapi_server(server_process)
    else:
        result = run_single_test(test_num, load_test, False)
        if test_num:
            logger.info(f"\n{'='*60}")
            if result:
                logger.info(f"Test {test_num} PASSED")
            else:
                logger.info(f"Test {test_num} FAILED")
            logger.info(f"{'='*60}")
        return result

def start_fastapi_server():
    try:
        try:
            response = requests.get(f'http://localhost:{cfg_agendata_task.system.port}', timeout=1)
            if response.status_code == 200:
                logger.info(f"⚠️  Found existing server on port {cfg_agendata_task.system.port}, attempting to kill it...")
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['cmdline'] and 'fast_api.py' in ' '.join(proc.info['cmdline']):
                            logger.info(f"Killing existing process {proc.info['pid']}")
                            proc.kill()
                            proc.wait(timeout=5)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                        pass
        except:
            pass
        
        cmd = [sys.executable, 'fast_api.py']
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        process = subprocess.Popen(
            cmd, 
            cwd=cwd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        time.sleep(5)
        
        if process.poll() is not None:
            error_output = process.stderr.read()
            logger.info(f"❌ Server failed to start. Error: {error_output}")
            return None
        try:
            response = requests.get(f'http://localhost:{cfg_agendata_task.system.port}', timeout=2)
            if response.status_code == 200:
                logger.info("✅ FastAPI server started successfully and responding")
                return process
            else:
                logger.info(f"❌ Server started but returned status {response.status_code}")
                process.terminate()
                return None
        except Exception as e:
            logger.info(f"❌ Server process running but not responding: {e}")
            process.terminate()
            return None
    except Exception as e:
        logger.info(f"❌ Failed to start server: {e}")
        return None

def stop_fastapi_server(process):
    try:
        process.terminate()
        process.wait(timeout=5)
        logger.info("✅ FastAPI server stopped")
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        logger.info("⚠️  FastAPI server killed (timeout)")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run FastAPI scheduler tests')
    parser.add_argument('test_num', nargs='?', type=int, help='Test number to run (1-5)')
    parser.add_argument('--load-test', action='store_true', help='Run tests without cleaning up between them (for load testing)')
    parser.add_argument('-p', '--parallel', action='store_true', help='Run all tests in parallel (only works when no test_num is specified)')
    
    args = parser.parse_args()
    logger.info("Cleaning up test files before running tests...")
    cleanup_test_files()
    success = run_pytest_tests(args.test_num, args.load_test, args.parallel)
    if not args.load_test:
        logger.info("Cleaning up test files after running tests...")
        cleanup_test_files()
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
