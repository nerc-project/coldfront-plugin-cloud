"""WSGI wrapper for tooling that expects a top-level application object"""

import logging

from . import app

APP = app.create_app()

if __name__ == "__main__":
    APP.run()
else:
    APP.logger = logging.getLogger("gunicorn.error")
    APP.logger.setLevel(logging.INFO)
