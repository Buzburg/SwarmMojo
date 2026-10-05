"""ROMS Mojo entry point; propagate startup errors as process failures."""
from app_mojo.server import start_mojo_server

def main() raises:
    start_mojo_server()
