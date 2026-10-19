"""Shared Jinja2 templates instance.

All routers used to instantiate their own `Jinja2Templates` and register globals
on each one separately. That's a footgun: if you add a new global in `main.py`
and forget to add it to one of the routers, the page blows up with an
UndefinedError at runtime.

This module is the single source of truth. It builds one templates object with
all globals pre-registered, and routers import this instead of building their
own.
"""
from __future__ import annotations

from fastapi.templating import Jinja2Templates

from .config import BASE_DIR
from .drive import is_configured as _drive_is_configured
from .permissions import can
from .deps import pop_flash


templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Register every global every page might need, once.
templates.env.globals["sidebar_drive_ready"] = _drive_is_configured
templates.env.globals["can"] = can
templates.env.globals["pop_flash"] = pop_flash
