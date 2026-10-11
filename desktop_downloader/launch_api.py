from __future__ import annotations

from launch import _ensure_dependencies


def main() -> None:
    _ensure_dependencies()
    from api import main as run_api

    run_api()


if __name__ == "__main__":
    main()
