import sys
import yaml
import shutil
import threading
import requests
import time
import socket
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import logging
logger = logging.getLogger(__name__)

class Utils:
    """Utility Functions for File Operations and Data Formatting

    Role: Provides helper methods for data formatting, sending messages to discord (dllb),
          and registering automated tasks in the Orchestrator API.

    Methods:
        format_result(result) : Format dict or other result as string.
        send_discord_notification(...) : Sends asynchronous notifications.
        add_cron_task(...) : Adds a recurring cron task via the Scheduler API.
        add_oneshot_task(...) : Adds a one-time task (ISO date or timestamp) via the Scheduler API.
    """
    @staticmethod
    def format_result(result):
        if isinstance(result, dict):
            try:
                formatted_items = []
                for k, v in result.items():
                    formatted_items.append(f"{k}:{v}")
                return ",".join(formatted_items)
            except Exception:
                return str(result)
        return str(result)

    @staticmethod
    def get_server_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    @staticmethod
    def send_discord_notification(message, channel=None, files=None):
        if getattr(cfg, 'discord', None) is None:
            logger.info("Discord not configured")
            return
        def post_request():
            try:
                if channel is not None:
                    channel_name = channel
                else:
                    channel_name = cfg.discord.channel
                payload = {
                    "channel_name": channel_name,
                    "msg": message,
                    "attachments": files if files else []
                }
                server_ip = Utils.get_server_ip()
                requests.post(f"http://{server_ip}:{cfg.discord.port}/send",
                              json=payload,
                              timeout=5)
            except Exception as e:
                pass
        threading.Thread(target=post_request, daemon=False).start()

    @staticmethod
    def add_oneshot_task(task_id: str, function: str, date_or_timestamp, description: str = "", args: list = None, hidden: str = "yes"):
        try:
            if isinstance(date_or_timestamp, (int, float)):
                run_date_str = datetime.fromtimestamp(date_or_timestamp).strftime('%Y-%m-%dT%H:%M:%S')
            else:
                try:
                    if 'T' in str(date_or_timestamp):
                        date_part, time_part = str(date_or_timestamp).split('T')
                        time_segments = time_part.split(':')
                        padded_time = ':'.join(seg.zfill(2) for seg in time_segments)
                        dt = datetime.fromisoformat(f"{date_part}T{padded_time}")
                    else:
                        dt = datetime.fromisoformat(str(date_or_timestamp))
                    run_date_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    run_date_str = str(date_or_timestamp)

            port = getattr(cfg.system, 'port', 8888)
            server_ip = Utils.get_server_ip()
            url = f"http://{server_ip}:{port}/tasks"

            payload = {
                "id": task_id,
                "function": function,
                "trigger_type": "date",
                "description": description,
                "cron": None,
                "run_date": run_date_str,
                "args": args if args else [],
                "status": "active",
                "state": "active",
                "skip_next": [],
                "hidden": hidden
            }

            response = requests.post(url, json=payload, timeout=5)
            return response.json()
        except Exception as e:
            logger.error(f"Failed to add oneshot task {task_id}: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def add_oneshot_task(task_id: str, function: str, date_or_timestamp, description: str = "", args: list = None, hidden: str = "yes"):
        """
        Enregistre une tâche à exécution unique (date) alignée sur le modèle valide.
        :param date_or_timestamp: Chaîne au format ISO ou timestamp Unix (int/float)
        """
        try:
            if isinstance(date_or_timestamp, (int, float)):
                run_date_str = datetime.fromtimestamp(date_or_timestamp).isoformat()
            else:
                run_date_str = str(date_or_timestamp)

            port = getattr(cfg.system, 'port', 8888)
            server_ip = Utils.get_server_ip()
            url = f"http://{server_ip}:{port}/tasks"

            payload = {
                "id": task_id,
                "function": function,
                "trigger_type": "date",
                "description": description,
                "cron": None,
                "run_date": run_date_str,
                "args": args if args else [],
                "status": "active",
                "state": "active",
                "skip_next": [],
                "hidden": hidden
            }

            response = requests.post(url, json=payload, timeout=5)
            return response.json()
        except Exception as e:
            logger.error(f"Failed to add oneshot task {task_id}: {str(e)}")
            return {"success": False, "message": str(e)}

class LocalFilesFilter(logging.Filter):
    
    def __init__(self):
        super().__init__()
        self.local_files = set()
        root_dir = cfg.root if hasattr(cfg, 'root') else Path(__file__).resolve().parent
        for path in root_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for part in path.parts:
                if part.startswith('.'):
                    break
                else:
                    self.local_files.add(path.name)

    def filter(self, record):
        return record.filename in self.local_files


def setup_logging():
    log_dir = cfg.config_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    date_format = "%y%m%d:%H:%M:%S"
    
    if getattr(cfg, 'verbose', False):
        log_format = "[%(asctime)s][%(filename)s][%(funcName)s](%(levelname)s): %(message)s"
    else:
        log_format = "[%(asctime)s][%(funcName)s](%(levelname)s): %(message)s"
    
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
    local_filter = LocalFilesFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(local_filter)

    file_handler = logging.FileHandler(log_dir / "debug.log", mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(local_filter)

    root_logger = logging.getLogger()
    if getattr(cfg, 'debug', False):
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)

    root_logger.handlers = []
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("uvicorn").setLevel(logging.WARNING)


class CfgConfig(SimpleNamespace):

    def __repr__(self):
        return self._format_object(self)

    def _format_object(self, obj, indent_level=0):

        spacing = "  " * indent_level
        if isinstance(obj, (SimpleNamespace, CfgConfig)):
            items = vars(obj).items()
            if not items:
                return "{}"
            lines = ["{"]
            for k, v in items:
                formatted_value = self._format_object(v, indent_level + 1)
                lines.append(spacing + "  " + '"' + k + '": ' + formatted_value + ',')
            lines[-1] = lines[-1].rstrip(',')
            lines.append(spacing + "}")
            return "\n".join(lines)
        if isinstance(obj, str):
            return '"' + obj + '"'
        return str(obj)

    def to_dict(self):

        result = {}
        for k, v in vars(self).items():
            if isinstance(v, CfgConfig):
                result[k] = v.to_dict()
            else:
                result[k] = v
        return result


class AgendaTaskConfig:
    def __init__(self):
        self.BASE_DIR = Path.home() / "Documents" / "agenda-task"
        self.CONFIG_FILE = self.BASE_DIR / "config.yaml"
        self.AGENTS_DIR = self.BASE_DIR / "agents"
        self.AGENTS_DIR_COMMON = Path(__file__).parent / "agents"
        self._setup_files()
        self.cfg = self._dict_to_namespace(self._load_yaml())
        self.cfg.agents = self._load_agents()
        self.cfg.config_dir = self.BASE_DIR

    def _setup_files(self):
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)
        self.AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        if not self.CONFIG_FILE.exists():
            example = Path(__file__).parent / "config_example.yaml"
            if example.exists():
                shutil.copy(example, self.CONFIG_FILE)
                logger.info("Configuration initialized in " + str(self.CONFIG_FILE))
            else:
                logger.info("config_example.yaml not found in " + str(Path(__file__).parent))

    def _load_yaml(self):
        with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def _load_agents(self):
        agents = CfgConfig()
        self._load_markdown_agents(self.AGENTS_DIR, agents)
        self._load_markdown_agents(self.AGENTS_DIR_COMMON, agents)
        return agents

    def _load_markdown_agents(self, agents_dir, agents):
        for md_file in agents_dir.glob("*.md"):
            with open(md_file, "r", encoding='utf-8') as f:
                content = f.read().strip()
                setattr(agents, md_file.stem, content)

    def _dict_to_namespace(self, data):
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                converted_value = self._dict_to_namespace(v)
                result[k] = converted_value
            return CfgConfig(**result)
        if isinstance(data, list):
            converted_list = []
            for item in data:
                converted_item = self._dict_to_namespace(item)
                converted_list.append(converted_item)
            return converted_list
        return data


cfg = AgendaTaskConfig().cfg

