"""CLI entry point: cipher [directory] [-p "task"] [--setup] [--version]"""

import argparse
import sys
from pathlib import Path

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cipher",
        description="Cipher — an autonomous coding agent in your terminal.",
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="project directory (default: current)")
    parser.add_argument("-p", "--prompt", default="",
                        help="start with a task immediately")
    parser.add_argument("--setup", action="store_true",
                        help="re-run provider setup on launch")
    parser.add_argument("--version", action="version",
                        version=f"cipher {__version__}")
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    if not root.is_dir():
        print(f"error: {args.directory} is not a directory", file=sys.stderr)
        sys.exit(1)

    if args.setup:
        from .config import load_config, save_config
        cfg = load_config()
        cfg.pop("_configured", None)
        save_config(cfg)

    from .app import run_tui
    run_tui(str(root), first_task=args.prompt)


if __name__ == "__main__":
    main()
