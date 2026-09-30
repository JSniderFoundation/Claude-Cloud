"""Template rendering and flash messages shared by the routers."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from datetime import timezone
from zoneinfo import ZoneInfo

from .config import settings
from .services.pdf import longdate, money

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.filters["money"] = money
templates.env.filters["longdate"] = longdate
templates.env.filters["shortdate"] = lambda d: d.strftime("%m/%d/%Y") if d else ""


def stamp(d):
    if not d:
        return ""
    local = d.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone))
    return local.strftime("%m/%d/%Y %I:%M %p")


templates.env.filters["stamp"] = stamp


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append({"message": message, "kind": kind})


def render(request: Request, name: str, **context):
    context["request"] = request
    context["user"] = getattr(request.state, "user", None)
    context["flashes"] = request.session.pop("flash", [])
    context["active"] = context.get("active", name.split(".")[0])
    return templates.TemplateResponse(request, name, context)
