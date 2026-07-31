"""PyInstaller entry point — frozen binary calls into the CLI."""
from studyscout.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
