"""Flash Camera — Dual UV Imaging System entry point."""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from PyQt6.QtWidgets import QApplication

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "default_config.yaml"


def _load_config(config_path: str | None = None) -> dict:
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    logging.warning("Config not found at %s — using defaults", path)
    return {}


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt)
    logging.getLogger("flash_camera").setLevel(level)


def main():
    parser = argparse.ArgumentParser(description="Flash Camera Dual UV Imaging System")
    parser.add_argument(
        "--config", "-c", type=str, default=None,
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--simulated", "-s", action="store_true",
        help="Use simulated cameras (no hardware required)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    _setup_logging(verbose=args.verbose)
    config = _load_config(args.config)

    app = QApplication(sys.argv)
    app.setApplicationName("Flash Camera")
    app.setOrganizationName("General Flash")

    from flash_camera.gui.main_window import MainWindow
    window = MainWindow(config=config, use_simulated=args.simulated)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
