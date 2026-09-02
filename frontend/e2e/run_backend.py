import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import uvicorn

from app.core.config import Settings
from app.main import create_app

FRONTEND_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    settings = Settings(
        data_dir=data_dir,
        config_dir=data_dir / "config",
        spa_dist=FRONTEND_DIR / "dist",
        log_level="INFO",
    )
    app = create_app(settings)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
