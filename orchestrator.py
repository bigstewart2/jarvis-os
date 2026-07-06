"""Manual front door for Jarvis OS. Run: python3 orchestrator.py"""
import subprocess
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent / "apps" / "core"


def main() -> None:
    subprocess.run([sys.executable, "main.py"], cwd=CORE_DIR, check=True)


if __name__ == "__main__":
    main()
