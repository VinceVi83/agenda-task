from fastmcp import FastMCP
from datetime import datetime

mcp = FastMCP("My Super Server")

@mcp.tool()
def display(content: str) -> str:
    """Displays received message"""
    print(content)
    return content

@mcp.tool()
def subtraction(a: int, b: int) -> int:
    """Calculates difference (a - b)."""
    r = a - b
    print(r)
    return r

@mcp.resource("config://app")
def get_config() -> str:
    """Get configuration version info"""
    print("get_config")
    return "Test | Version: 2.0.0"

def write_file_task(file_path: str, message: str):
    """Task that writes to a file"""
    with open(file_path, 'a') as f:
        f.write(f"[{datetime.now()}] {message}\n")
    print(f"[{datetime.now()}] Wrote to {file_path}: {message}")


if __name__ == "__main__":
    mcp.run()
