import logging
import os

DEBUG = True

def setup_logging():
    os.makedirs("logs", exist_ok=True)
    level = logging.DEBUG if DEBUG else logging.WARNING
    handler = logging.FileHandler("logs/project.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
