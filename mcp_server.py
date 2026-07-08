import subprocess
from fastmcp import FastMCP
from datetime import datetime
from config_loader import cfg, Utils, setup_logging

import logging
logger = logging.getLogger(__name__)
setup_logging()
mcp = FastMCP("My Super Server")

@mcp.tool()
def send_discord_msg(message: str, channel: str) -> str:
    """
    Send message to channel in discord server.
    Logs the parameters before triggering the utility notification sender.

    Args:
        message: The textual content to be broadcasted to the server. (e.g., 'Hello world!')
        channel: The specific name or unique identifier of the destination channel. (e.g., 'general')
    """
    logger.info(f'"{message}" "{channel}"')
    return Utils.send_discord_notification(message, channel=channel, files=None)

@mcp.tool()
def display(content: str) -> str:
    """
    Displays received message.
    Logs and echoes back the provided text content.

    Args:
        content: The text message or payload to display in the logs. (e.g., 'Hello world')
    """
    logger.info(content)
    return content

@mcp.tool()
def subtraction(a: int, b: int) -> int:
    """
    Calculates difference.
    Subtracts the second integer from the first integer.

    Args:
        a: The absolute or relative target filesystem path destination. (e.g., '10')
        b: The actual string payload content to write. (e.g., '3')
    """
    r = a - b
    logger.info(r)
    return r

@mcp.resource("config://app")
def get_config() -> str:
    """
    Get configuration version info.
    Returns the dynamic system static identity and active version string.
    """
    logger.info("get_config")
    return "Test | Version: 2.0.0"

@mcp.tool()
def write_file_task(file_path: str, message: str):
    """
    Task that writes to a file.
    Appends a timestamped log entries line directly into the specified file path.

    Args:
        file_path: The absolute or relative target filesystem path destination. (e.g., 'output.txt')
        message: The actual string payload content to write. (e.g., 'Task completed successfully')
    """
    with open(file_path, 'a') as f:
        f.write(f"[{datetime.now()}] {message}\n")
    logger.info(f"[{datetime.now()}] Wrote to {file_path}: {message}")

@mcp.tool()
def send_multiroom_command(content):
    cmd = [cfg.multiroom.python_bin, "-m", "tools.hub_messenger"]
    cmd.append(content.strip())
    subprocess.Popen(cmd, cwd=cfg.multiroom.working_dir)
    return cmd

if __name__ == "__main__":
    send_discord_msg("test", "notify-anime")
    mcp.run()
