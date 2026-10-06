"""Local stdio entry point for the shared ROMS project-memory tools."""
from fastmcp import FastMCP
from app.memory_tools import register_memory_tools


def main() -> None:
    server = FastMCP('ROMS-Memory')
    register_memory_tools(server)
    server.run(transport='stdio', show_banner=False)


if __name__ == '__main__':
    main()
