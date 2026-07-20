import os

from fastapi.templating import Jinja2Templates

from app.config import settings

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["base"] = settings.base_path

_css_path = "app/static/css/forest.css"
try:
    templates.env.globals["asset_version"] = int(os.path.getmtime(_css_path))
except OSError:
    templates.env.globals["asset_version"] = 0
