from datetime import datetime, timezone
from typing import Dict, Any, Optional
import importlib
import logging
import json
import os
import sys
import copy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_ALL

from config_loader import cfg_agendata_task

import logging
logger = logging.getLogger(__name__)

def read_json(file_path):
    if not os.path.exists(file_path):
        logger.info(f"File {file_path} not found, creating with an empty array")
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"File read : {file_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Error : The file {file_path} is not a valid JSON. Error : {e}")
        return []

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Data saved in : {file_path}")
    except Exception as e:
        logger.error(f"Error during save : {e}")
        sys.exit(1)

class scheduler:
    """Scheduler Service Plugin
    
    Role: Manages task scheduling, execution, and removal using APScheduler integration.
    
    Methods:
        __init__(self) : Initialize the scheduler.
        _load_functions(self) : Load functions from function_docs.json.
        _check_task_exists(self, task_id) : Check if a task with the given ID already exists.
        _next_execution(self, task_id) : Get the next execution time of a task.
        _execute_task_wrapper(self, task) : Execute a task based on its status.
        _create_cron_trigger(self, cron_params) : Create a CronTrigger from cron parameters.
        _create_date_trigger(self, date_str) : Create a DateTrigger from date string.
        add_task(self, task) : Add a task to the scheduler.
        modify_task(self, task) : Modify an existing task.
        remove_task(self, task_id, save) : Remove a task from the scheduler.
        reschedule(self, task_id, new_cron_params, end_date) : Reschedule a task with new cron parameters and end date.
        reset_reschedule(self, task_id) : Reset a rescheduled task to its original cron parameters.
        _handle_reschedule(self, task) : Handle rescheduling logic for a task.
        add_skip(self, task_id, number) : Add a number to the skip_next list of a task.
        remove_skip(self, task_id, number) : Remove a number from the skip_next list of a task.
        _handle_skip_next(self, task) : Handle skip_next logic for a task.
        shutdown(self) : Shutdown the scheduler.
    """
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.tasks = read_json('tasks.json')
        self.functions = {}
        self._load_functions()
        if not isinstance(self.tasks, list):
            self.tasks = []
        self._load_existing_tasks()
        self.config_file = 'config.json'
        self.days_to_show = self._load_config().get('days_to_show', 7)
        self._init_internal_jobs()

    def _init_internal_jobs(self):
        try:
            self.scheduler.add_job(
                self._decrement_all_skips,
                trigger=CronTrigger(hour=23, minute=59, timezone='Europe/Paris'),
                id='internal_daily_skip_decrement',
                replace_existing=True
            )
            logger.info("Internal skip decrement job initialized at 23:59")
        except Exception as e:
            logger.error(f"Error during internal skip decrement job initialization: {e}")

    def _load_config(self) -> dict:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_config(self, days_to_show: int):
        self.days_to_show = days_to_show
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({'days_to_show': days_to_show}, f, indent=4)
        except Exception as e:
            logger.error(f"Error during configuration save: {e}")

    def _load_functions(self):
        self.functions = {}
        try:
            with open('function_docs.json', 'r', encoding='utf-8') as f:
                function_docs = json.load(f)
            
            for function_full_name, function_doc in function_docs.get('functions', {}).items():
                module_name = function_doc.get('module')
                module_path = function_doc.get('path')
                if module_name is None and '.' in function_full_name:
                    module_name = function_full_name.rsplit('.', 1)[0]
                
                if module_name is None:
                    logger.error(f"Module not specified for function {function_full_name}")
                    continue

                if '.' in function_full_name:
                    function_name = function_full_name.split('.')[-1]
                else:
                    function_name = function_full_name

                self.functions[function_full_name] = {
                    "module_name": module_name,
                    "module_path": module_path,
                    "function_name": function_name
                }
                if not module_name.startswith('mcp_server'):
                    logger.info(f"Function registered for subprocess: {function_full_name}")

        except FileNotFoundError:
            logger.error("The file function_docs.json was not found.")
        except json.JSONDecodeError as e:
            logger.error(f"Error reading the file function_docs.json: {e}")

    def _check_task_exists(self, task_id: str) -> bool:
        return self.scheduler.get_job(task_id) is not None

    def pause_task(self, task_id: str) -> bool:
        try:
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return False
            task = job.args[0] if job.args else {}
            task['status'] = 'pause'
            for t in self.tasks:
                if t.get('id') == task_id:
                    t['status'] = 'pause'
                    break
            job.modify(args=[task])
            save_json('tasks.json', self.tasks)
            logger.info(f"Task paused : {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error during pause of task {task_id}: {e}")
            return False

    def resume_task(self, task_id: str) -> bool:
        try:
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return False
            task = job.args[0] if job.args else {}
            task['status'] = 'active'
            for t in self.tasks:
                if t.get('id') == task_id:
                    t['status'] = 'active'
                    break
            job.modify(args=[task])
            save_json('tasks.json', self.tasks)
            logger.info(f"Task resumed : {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error during resume of task {task_id}: {e}")
            return False
      
    def reschedule(self, task_id: str, new_cron_params: Dict[str, str], end_date: str):
        try:
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return
            
            task = job.args[0] if job.args else {}
            
            if task.get('state') != 'rescheduled':
                original_cron_params = task.get('cron', {})
                task['cron_original'] = copy.deepcopy(original_cron_params)
                task['state'] = 'rescheduled'
            else:
                task['cron'] = {}
                
            task['cron'].clear()
            task['cron'].update(new_cron_params)
            task['end_date'] = end_date
            
            self.modify_task(task)
            logger.info(f"Task {task_id} rescheduled until {end_date}")
            self._check_and_reset_expired_reschedule(task_id, task)
            
        except Exception as e:
            logger.error(f"Error during reschedule of task {task_id}: {e}")

    def reset_reschedule(self, task_id: str):
        try:
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return
            
            task = job.args[0] if job.args else {}
            
            original_cron_params = task.get('cron_original', {})
            if not original_cron_params:
                logger.error(f"No original cron parameters found for task {task_id}")
                return
            
            task['cron'] = original_cron_params
            task['cron_original'] = {}
            task['state'] = 'active'
            task.pop('end_date', None)
            
            self.modify_task(task)
            logger.info(f"Task {task_id} reschedule reset")
            
        except Exception as e:
            logger.error(f"Error during reschedule reset of task {task_id}: {e}")

    def _next_execution(self, task_id: str) -> Optional[str]:
        try:
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return None
            
            next_run_time = job.next_run_time
            if next_run_time:
                return next_run_time.isoformat()
            return None
            
        except Exception as e:
            logger.error(f"Error during retrieval of next execution for task {task_id}: {e}")
            return None

    def _handle_reschedule(self, task: Dict[str, Any]):
        end_date_str = task.get('end_date', "")
        if not end_date_str:
            return
        
        try:
            end_date = datetime.fromisoformat(end_date_str)
            next_execution = self._next_execution(task.get('id'))
            if next_execution:
                next_execution_date = datetime.fromisoformat(next_execution)
                if next_execution_date >= end_date:
                    self.reset_reschedule(task.get('id'))
        except ValueError as e:
            logger.error(f"Invalid date format for end_date: {e}")
        except Exception as e:
            logger.error(f"Error during reschedule handling for task {task.get('id')}: {e}")

    def _execute_task_wrapper(self, task: Dict[str, Any]):
        task_id = task.get('id')
        if self._handle_skip_next(task):
            if task_id:
                self._check_and_reset_expired_reschedule(task_id, task)
            return

        function_full_name = task.get('function')
        args = task.get('args', [])
        kwargs = task.get('kwargs', {})

        if function_full_name not in self.functions:
            logger.error(f"Function {function_full_name} not found in registered functions.")
            return

        func_meta = self.functions[function_full_name]
        module_path = func_meta["module_path"]
        module_name = func_meta["module_name"]
        function_name = func_meta["function_name"]

        import subprocess
        import sys

        script_code = f"""
import sys
import os
import json

import logging
logger = logging.getLogger(__name__)

if '{module_path}':
    sys.path.insert(0, '{module_path}')
    os.chdir('{module_path}')

import {module_name}
func = getattr({module_name}, '{function_name}')

# Appel de la fonction avec les arguments
func(*{args}, **{kwargs})
"""

        try:
            logger.info(f"Executing job {task_id} ({function_full_name}) via isolated subprocess...")
            
            process = subprocess.run(
                [sys.executable, "-c", script_code],
                cwd=module_path if module_path else os.getcwd(),
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"✅ {function_full_name} executed successfully.")
            if process.stdout:
                logger.debug(f"Subprocess stdout: {process.stdout}")

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Error during isolated execution of {function_full_name}:")
            logger.error(e.stderr)

        if task_id:
            self._check_and_reset_expired_reschedule(task_id, task)

    def _create_cron_trigger(self, cron_params: Dict[str, str]) -> CronTrigger:
        try:
            cron_trigger_params = {
                'year': cron_params.get('year', '*'),
                'month': cron_params.get('month', '*'),
                'day': cron_params.get('day', '*'),
                'week': cron_params.get('week', '*'),
                'day_of_week': cron_params.get('day_of_week', '*'),
                'hour': cron_params.get('hour', '0'),
                'minute': cron_params.get('minute', '0'),
                'second': cron_params.get('second', '0'),
                'timezone': 'Europe/Paris'
            }
            
            return CronTrigger(**cron_trigger_params)
            
        except Exception as e:
            logger.error(f"Invalid cron parameters: {e}")
            raise

    def _create_date_trigger(self, date_str: str) -> DateTrigger:
        try:
            run_date = datetime.fromisoformat(date_str)
            return DateTrigger(run_date=run_date, timezone='Europe/Paris')
            
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            raise

    def add_task(self, task: Dict[str, Any], on_load: bool = False):
        task_id = task.get('id')
        trigger_type = task.get('trigger_type')
        
        function_full_name = task.get('function')
        task_args = task.get('args', [])
        task_kwargs = task.get('kwargs', {})

        if self._check_task_exists(task_id):
            logger.error(f"A task with ID {task_id} already exists in the scheduler.")
            raise ValueError(f"Task with ID {task_id} already exists in scheduler")
        
        if not on_load and any(t.get('id') == task_id for t in self.tasks):
            logger.error(f"A task with ID {task_id} already exists in the tasks list.")
            raise ValueError(f"Task with ID {task_id} already exists in tasks list")
        
        try:
            if trigger_type == 'cron':
                cron_params = task.get('cron', {})
                trigger = self._create_cron_trigger(cron_params)
            elif trigger_type == 'date':
                run_date = task.get('run_date')
                trigger = self._create_date_trigger(run_date)
            else:
                logger.error(f"Unsupported trigger type : {trigger_type}")
                raise ValueError(f"Unsupported trigger type: {trigger_type}")

            self.scheduler.add_job(
                self._execute_task_wrapper,
                trigger=trigger,
                id=task_id,
                args=[task],
                replace_existing=True
            )
            if not on_load:
                self.tasks.append(task)
                save_json('tasks.json', self.tasks)
            
            logger.info(f"Task added : {task_id} targeting {function_full_name}")
        except Exception as e:
            logger.error(f"Error during task addition for {task_id}: {e}")
            raise

    def modify_task(self, task: Dict[str, Any]):
        try:
            task_id = task.get('id')
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return
            
            self.remove_task(task_id, save=False)
            self.add_task(task)
            logger.info(f"Task modified : {task_id}")
        except Exception as e:
            logger.error(f"Error during task modification for {task_id}: {e}")

    def remove_task(self, task_id: str, save = True):
        try:
            self.scheduler.remove_job(task_id)
            for i, t in enumerate(self.tasks):
                if t.get('id') == task_id:
                    del self.tasks[i]
                    break
            if save:
                save_json('tasks.json', self.tasks)
            logger.info(f"Task removed : {task_id}")
        except Exception as e:
            logger.error(f"Error during task removal for {task_id}: {e}")

    def _decrement_all_skips(self):
        logger.info("Execution of global skip decrement job")
        modified = False
        
        for task in self.tasks:
            skip_table = task.get('skip_next', [])
            if skip_table:
                updated_table = [num - 1 for num in skip_table if (num - 1) > 0]
                task['skip_next'] = updated_table
                modified = True
                
                task_id = task.get('id')
                job = self.scheduler.get_job(task_id)
                if job:
                    try:
                        job_task = job.args[0] if job.args else {}
                        job_task['skip_next'] = updated_table
                        job.modify(args=[job_task])
                    except Exception as e:
                        logger.error(f"Error during scheduler job update for {task_id}: {e}")
                        
        if modified:
            save_json('tasks.json', self.tasks)
            logger.info("Data saved after global skip decrement")

    def add_skip(self, task_id: str, number: int):
        try:
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return
            
            task = next((t for t in self.tasks if t.get('id') == task_id), None)
            if task is None:
                logger.error(f"Task {task_id} not found in self.tasks list")
                return

            if 'skip_next' not in task:
                task['skip_next'] = []
                
            skip_table = task['skip_next']
            
            if number in skip_table:
                skip_table.remove(number)
                logger.info(f"Number {number} removed from skip_next for task {task_id}")
            else:
                skip_table.append(number)
                logger.info(f"Number {number} added to skip_next for task {task_id}")
                
            job.modify(args=[task])
            save_json('tasks.json', self.tasks)
            
        except Exception as e:
            logger.error(f"Error during skip modification for task {task_id}: {e}")

    def remove_skip(self, task_id: str, number: int):
        try:
            job = self.scheduler.get_job(task_id)
            if job is None:
                logger.error(f"Task not found : {task_id}")
                return
            
            task = job.args[0] if job.args else {}
            skip_table = task.get('skip_next', [])
            
            if number in skip_table:
                skip_table.remove(number)
                task['skip_next'] = skip_table
                job.modify(args=[task])
                save_json('tasks.json', self.tasks)
                logger.info(f"Number {number} removed from skip_next for task {task_id}")
            else:
                logger.error(f"Number {number} not found in skip_next for task {task_id}")
            
        except Exception as e:
            logger.error(f"Error during skip removal for task {task_id}: {e}")

    def _handle_skip_next(self, task: Dict[str, Any]) -> bool:
        skip_table = task.get('skip_next', [])
        if 0 in skip_table:
            logger.info(f"Task skipped (0 detected, execution blocked) : {task.get('id')}")
            return True
        return False
    
    def _check_and_reset_expired_reschedule(self, task_id: str, task: Dict[str, Any]):
        if task.get('state') == 'rescheduled' and task.get('end_date'):
            try:
                end_date_str = task.get('end_date')
                end_date = datetime.fromisoformat(end_date_str)
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
                
                job = self.scheduler.get_job(task_id)
                if job:
                    next_run_time = job.next_run_time
                    now = datetime.now().astimezone() if end_date.tzinfo else datetime.now()
                    if next_run_time is None or next_run_time >= end_date or now >= end_date:
                        logger.info(f"Rescheduled task {task_id} already expired, resetting")
                        self.reset_reschedule(task_id)
                        return True
            except Exception as e:
                logger.error(f"Error during expiration check for {task_id}: {e}")
        return False
    
    def _load_existing_tasks(self):
        for task in self.tasks:
            try:
                task_id = task.get('id')
                if task_id and not self._check_task_exists(task_id):
                    self.add_task(task, on_load=True)
                    self._check_and_reset_expired_reschedule(task_id, task)
                    
                    logger.info(f"Task loaded from tasks.json : {task_id}")
                    
            except Exception as e:
                logger.error(f"Error during loading of task {task.get('id')} from tasks.json: {e}")

    def shutdown(self):
        self.scheduler.shutdown()

current_scheduler = scheduler()
