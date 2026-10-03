"""Jinja2 environment shared by all HTML pages."""

from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import TEMPLATES_DIR, get_settings

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals.update(app_name=get_settings().app_name, app_version=__version__)
