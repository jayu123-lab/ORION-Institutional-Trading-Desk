"""CLI entrypoint: python -m core.memory.init_db"""

from core.logging import setup_logging
from core.memory.database import get_engine, init_db


def main() -> None:
    setup_logging()
    eng = get_engine()
    init_db(eng)
    print(f"database ready at {eng.url}")


if __name__ == "__main__":
    main()
