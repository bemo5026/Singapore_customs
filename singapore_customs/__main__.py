"""Command line entry point: ``python -m singapore_customs --config config.yaml``."""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from singapore_customs.api import create_session
from singapore_customs.config import load_config
from singapore_customs.extract import run


def configure_logging(log_dir: Path, *, verbose: bool) -> Path:
    """Log to the console and to a timestamped file in ``log_dir``; return the file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{datetime.now(tz=UTC).astimezone():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    # urllib3 logs every retry at WARNING, which is what we want; its DEBUG output is noise.
    logging.getLogger("urllib3").setLevel(logging.INFO)
    return log_path


def main() -> None:
    """Parse the arguments and run the extraction."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="YAML config file")
    parser.add_argument("--log-dir", type=Path, default=Path("logs"), help="folder for log files")
    parser.add_argument("--verbose", action="store_true", help="log every downloaded page")
    args = parser.parse_args()

    log_path = configure_logging(args.log_dir, verbose=args.verbose)
    logger = logging.getLogger("singapore_customs")
    logger.info("config %s, log file %s", args.config.resolve(), log_path.resolve())
    config = load_config(args.config)
    try:
        run(config, create_session(config.http))
    except Exception:
        logger.exception("extraction failed")
        raise
    logger.info("extraction finished")


if __name__ == "__main__":
    main()
