"""Compatibility entry point for START-EKOSISTEM.bat and service management."""
from service_manager import entrypoint

if __name__ == '__main__':
    raise SystemExit(entrypoint())
