"""Manual front door for Jarvis OS. Run: python3 orchestrator.py"""
import subprocess
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent / "apps" / "core"


def main() -> None:
    venv_python = CORE_DIR / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        print(
            "No virtualenv found at apps/core/.venv — run: "
            "cd apps/core && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)
    subprocess.run([str(venv_python), "main.py"], cwd=CORE_DIR, check=True)


if __name__ == "__main__":
    main()
