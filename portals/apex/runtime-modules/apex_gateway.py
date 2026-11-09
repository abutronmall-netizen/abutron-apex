"""APEX ASGI gateway. Preserve upstream original AgenticTrading, add /apex ops UI.

No modifications to the upstream application's source code.
"""
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import RedirectResponse
from dashboard.backend.app import app as original_lab
from apex_ui.app import app as apex_dashboard

def home(request):
    return RedirectResponse(url="/apex/", status_code=307)

app = Starlette(routes=[
    Route("/", home, methods=["GET"]),
    Mount("/apex", app=apex_dashboard),
    Mount("/", app=original_lab),
])
