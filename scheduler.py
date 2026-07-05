from datetime import datetime, timezone
from typing import Dict, Any, Optional
import ast
import logging
import json
import os
import sys
import subprocess
import copy
import asyncio
import nest_asyncio
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_ALL
from mcp import ClientSession
from mcp.client.sse import sse_client
from datetime import datetime, timezone, timedelta
from config_loader import cfg

import logging
logger = logging.getLogger(__name__)

class MCPManager:
    def __init__(self):
        self.sessions = {}
        self.static_files = getattr(cfg.system, 'scripts', [])
        self.lock = asyncio.Lock()
        self.ready = asyncio.Event()
        self.functions_cache = self._parse_static_files()
        self.mcp_known_servers = []
        for item in getattr(cfg.system, 'mcp_servers', []):
            if hasattr(item, '__dict__'):
                self.mcp_known_servers.extend(item.__dict__.keys())

    async def start(self):
        await self.initialize_all_functions()

    async def wait_until_ready(self):
        """À appeler par le scheduler si besoin"""
        if not self._init_done.is_set():
            await self._init_done.wait()

    def is_mcp_function(self, function_full_name: str) -> bool:
        module_name = function_full_name.split('.')[0]
        return module_name in self.mcp_known_servers

    def _parse_static_files(self):
        all_funcs = {}
        ast_files = getattr(cfg.system, 'scripts', [])
        for filepath in ast_files:
            if not os.path.exists(filepath) or not filepath.endswith('.py'):
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    source_code = f.read()
                tree = ast.parse(source_code)
                module_name = os.path.splitext(os.path.basename(filepath))[0]
                module_dir = os.path.dirname(os.path.abspath(filepath))
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                        full_name = f"{module_name}.{node.name}"
                        doc = ast.get_docstring(node)
                        description = doc.strip() if doc else ''
                        args_list = []
                        for arg in node.args.args:
                            if arg.arg == 'self':
                                continue
                            args_list.append({'name': arg.arg, 'example': f"'{arg.arg}_value'"})

                        kwargs_list = []
                        for arg in node.args.kwonlyargs:
                            kwargs_list.append({'name': arg.arg, 'example': f"'{arg.arg}_value'"})

                        all_funcs[full_name] = {
                            'description': description,
                            'args': args_list,
                            'kwargs': kwargs_list,
                            'module': module_name,
                            'module_name': module_name,
                            'module_path': module_dir,
                            'path': module_dir,
                            'function_name': node.name,
                            'is_mcp_server': False
                        }
            except Exception as e:
                logger.error(f"Erreur lors de l'analyse du fichier {filepath}: {e}")

        self.functions = all_funcs
        return all_funcs

    async def _fetch_tools_from_server(self, identifier, config):
        try:
            url = f"http://{config.get('host', '127.0.0.1')}:{config.get('port', '8001')}/sse"
            ctx = sse_client(url)
            async with ctx as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    extracted = {}
                    for tool in tools_result.tools:
                        schema = getattr(tool, 'inputSchema', {})
                        properties = schema.get('properties', {})
                        required_fields = schema.get('required', [])
                        args = []
                        kwargs = []
                        for param_name in properties.keys():
                            arg_info = {'name': param_name, 'example': f"'{param_name}_value'"}
                            if param_name in required_fields:
                                args.append(arg_info)
                            else:
                                kwargs.append(arg_info)
                        extracted[f"{identifier}.{tool.name}"] = {
                            'description': tool.description or "MCP Tool",
                            'args': args,
                            'kwargs': kwargs,
                            'module': identifier,
                            'is_mcp_server': True
                        }
                    return extracted
        except Exception as e:
            logger.error(f"Erreur extraction outils {identifier}: {e}")
            return {}

    async def initialize_all_functions(self):
        try:
            functions = self._parse_static_files()
            logger.info(f"Statiques chargés : {len(functions)} fonctions.")
            mcp_servers = getattr(cfg.system, 'mcp_servers', [])
            for server_entry in mcp_servers:
                server_dict = vars(server_entry) if hasattr(server_entry, '__dict__') else server_entry
                for identifier, config_obj in server_dict.items():
                    config = vars(config_obj) if hasattr(config_obj, '__dict__') else config_obj
                    host = config.get('host', '127.0.0.1')
                    port = config.get('port', '8001')
                    sse_url = f"http://{host}:{port}/sse"
                    logger.info(f"Scan dynamique MCP : {identifier} sur {sse_url}")
                    tools = await self._fetch_tools_from_server(identifier, config)
                    if tools:
                        functions.update(tools)
                        logger.info(f"Fusion de {len(tools)} outils pour {identifier}")
                    else:
                        logger.warning(f"Aucun outil trouvé pour {identifier} ou serveur injoignable.")
            with open('function_docs.json', 'w', encoding='utf-8') as f:
                json.dump({'functions': functions}, f, indent=4, ensure_ascii=False)
            self.functions_cache = functions
            self.ready.set()
            logger.info(f"FIN initialize_all_functions : Total {len(functions)} fonctions enregistrées.")
            
        except Exception as e:
            logger.error(f"CRASH FATAL dans initialize_all_functions : {e}", exc_info=True)

    async def refresh_docs(self):
        def json_serial(obj):
            if isinstance(obj, set):
                return list(obj)
            raise TypeError(f"Type {type(obj)} non serializable")

        async with self.lock:
            if os.path.exists('function_docs.json'):
                with open('function_docs.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    functions = data.get('functions', {})
            else:
                functions = self._parse_static_files()
            for ident, data in self.sessions.items():
                tools = await data["session"].list_tools()
                for tool in tools.tools:
                    functions[f"{ident}.{tool.name}"] = {
                        'description': tool.description,
                        'module': ident,
                        'is_mcp_server': True
                    }
            with open('function_docs.json', 'w', encoding='utf-8') as f:
                json.dump({'functions': functions}, f, indent=4, default=json_serial)
            self.functions_cache = functions

    async def ensure_connection(self, identifier):
        if identifier in self.sessions:
            try:
                await self.sessions[identifier]["session"].list_tools()
                return True
            except:
                self.sessions.pop(identifier, None)
        servers = getattr(cfg.system, 'mcp_servers', [])
        conf = next((vars(s)[identifier] for s in servers if identifier in vars(s)), None)
        if not conf: return False
        try:
            host = getattr(conf, 'host', '127.0.0.1')
            port = getattr(conf, 'port', '8001')
            url = f"http://{host}:{port}/sse"
            ctx = sse_client(url)
            read, write = await ctx.__aenter__()
            session = await ClientSession(read, write).__aenter__()
            await session.initialize()
            self.sessions[identifier] = {"session": session, "client_ctx": ctx, "config": conf}
            await self.refresh_docs() 
            return True
        except Exception as e:
            logger.error(f"Connexion échouée {identifier}: {e}")
            return False

    async def call_tool(self, tool_path, arguments):
        if not self.ready.is_set():
            logger.warning("MCPManager pas encore prêt, attente...")
            await self.ready.wait()

        ident = tool_path.split('.')[0]
        tool_name = tool_path.split('.')[-1]
        is_connected = await self.ensure_connection(ident)
        if not is_connected:
            raise ConnectionError(f"Serveur MCP '{ident}' injoignable.")
        return await self.sessions[ident]["session"].call_tool(tool_name, arguments=arguments)

    def load_functions(self):
        functions = self.functions_cache.copy()
        for ident, data in self.sessions.items():
            pass 

        if os.path.exists('function_docs.json'):
            try:
                with open('function_docs.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    functions.update(data.get('functions', {}))
            except: pass
        return functions

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
    def __init__(self, mcp_manager):
        self.local_tz = datetime.now().astimezone().tzinfo
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.loop = None
        self.tasks = read_json('tasks.json')
        self.functions = {}
        self.manager = mcp_manager
        if not self.manager.functions_cache:
            logger.info("Attente de la fin de l'initialisation MCP...")
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.manager.ready.wait())
            except Exception as e:
                logger.error(f"Erreur attente init MCP: {e}")

        self._load_functions()
        if not isinstance(self.tasks, list):
            self.tasks = []
        self._load_existing_tasks()
        self.config_file = 'config.json'
        self.days_to_show = self._load_config().get('days_to_show', 7)
        self._init_internal_jobs()
        if not self.manager.functions_cache:
            logger.info("En attente de la fin de l'initialisation MCP...")
            loop = asyncio.get_event_loop()

    def set_event_loop(self, loop):
        self.loop = loop

    def _handle_task_success(self, task: dict, result: Any):
        logger.info(f"Task {task.get('id')} réussie: {result}")

    def _handle_task_failure(self, task: dict, error_msg: str):
        logger.error(f"Task {task.get('id')} a échoué: {error_msg}")

    def _init_internal_jobs(self):
        try:
            self.scheduler.add_job(
                self._decrement_all_skips,
                trigger=CronTrigger(hour=23, minute=59, timezone=self.local_tz),
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
        if not self.manager.functions_cache:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.manager.wait_until_ready())
            except: pass
        self.functions = self.manager.load_functions()

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

    async def _execute_mcp_task_via_sse(self, task: dict):
        function_full_name = task.get("function")
        args = task.get("kwargs", {})
        try:
            await asyncio.wait_for(self.manager.ready.wait(), timeout=10.0)
            result = await self.manager.call_tool(function_full_name, args)
            self._handle_task_success(task, result)
        except asyncio.TimeoutError:
            logger.error(f"Timeout: MCPManager non prêt pour {function_full_name}")
            self._handle_task_failure(task, "MCPManager timeout")
        except Exception as e:
            logger.error(f"Erreur exécution: {e}")
            self._handle_task_failure(task, str(e))

    def _execute_task_wrapper_simple(self, task: dict):
        function_full_name = task.get("function")
        args = task.get("args", [])
        kwargs = task.get("kwargs", {})
        task_id = task.get("id")
        func_meta = self.functions.get(function_full_name)
        if func_meta and not func_meta.get("is_mcp_server") and func_meta.get("module_path"):
            module_path = func_meta["module_path"]
            module_name = func_meta["module_name"]
            function_name = func_meta["function_name"]
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
                logger.info(f"{function_full_name} executed successfully.")
                if process.stdout:
                    logger.debug(f"Subprocess stdout: {process.stdout}")
                self._handle_task_success(task, process.stdout)
                return
            except subprocess.CalledProcessError as e:
                logger.error(f"Error during isolated execution of {function_full_name}:")
                self._handle_task_failure(task, e.stderr)
                return

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
                'timezone': self.local_tz
            }
            return CronTrigger(**cron_trigger_params)
        except Exception as e:
            logger.error(f"Invalid cron parameters: {e}")
            raise

    def _execute_task_wrapper(self, task: dict):
        logger.info(f"Début exécution wrapper pour {task.get('id')}")
        if task.get('status') == 'pause':
            logger.info(f"Task {task.get('id')} est en pause. Skipping.")
            return

        def run_async_task(coro):
            return asyncio.run(coro)

        try:
            if hasattr(self, 'manager') and not self.manager.ready.is_set():
                logger.info("En attente de ready...")
                run_async_task(self.manager.ready.wait())

            if task.get('status') == 'pause':
                return

            function_full_name = task.get("function", "")
            if function_full_name in self.functions and not self.functions[function_full_name].get("is_mcp_server"):
                logger.error('_execute_task_wrapper_simple')
                self._execute_task_wrapper_simple(task)
            else:
                logger.info(f"Fonction {function_full_name} routage vers MCP...")
                run_async_task(self._execute_mcp_task_via_sse(task))
            self._cleanup_task(task)
            logger.info(f"Fin exécution {task.get('id')}")
        except Exception as e:
            logger.error(f"Erreur fatale exécution: {e}", exc_info=True)

    def _cleanup_task(self, task: dict):
        logger.error("fin _cleanup_task")
        task_id = task.get('id')
        if not task_id:
            return
        self._check_and_reset_expired_reschedule(task_id, task)
        if task.get('trigger_type') == 'date':
            self.tasks = [t for t in self.tasks if t.get('id') != task_id]
            save_json('tasks.json', self.tasks)

    def _create_date_trigger(self, date_str: str) -> DateTrigger:
        try:
            if 'T' in date_str:
                date_part, time_part = date_str.split('T')
                time_segments = time_part.split(':')
                padded_time = ':'.join(seg.zfill(2) for seg in time_segments)
                date_str = f"{date_part}T{padded_time}"
            run_date = datetime.fromisoformat(date_str)
            return DateTrigger(run_date=run_date, timezone=self.local_tz)
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
                now_localized = datetime.now(trigger.run_date.tzinfo)
                if trigger.run_date < now_localized:
                    err_msg = f"Cannot create task {task_id}: the execution date {run_date} is already in the past."
                    logger.error(err_msg)
                    raise ValueError(err_msg)
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
        tasks_to_remove = []
        for task in self.tasks:
            try:
                task_id = task.get('id')
                if task_id and not self._check_task_exists(task_id):
                    if task.get('trigger_type') == 'date':
                        run_date_str = task.get('run_date')
                        if run_date_str:
                            run_date = datetime.fromisoformat(run_date_str)
                            now = datetime.now().astimezone() if run_date.tzinfo else datetime.now()
                            if run_date < now:
                                logger.info(f"One-shot task {task_id} has a past execution date ({run_date_str}), cleaning up.")
                                tasks_to_remove.append(task_id)
                                continue
                    self.add_task(task, on_load=True)
                    self._check_and_reset_expired_reschedule(task_id, task)
                    logger.info(f"Task loaded from tasks.json : {task_id}")
            except Exception as e:
                logger.error(f"Error during loading of task {task.get('id')} from tasks.json: {e}")
        if tasks_to_remove:
            self.tasks = [t for t in self.tasks if t.get('id') not in tasks_to_remove]
            save_json('tasks.json', self.tasks)
