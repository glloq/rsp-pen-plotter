"""User macro endpoints: list, create/update, delete, and run."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pen_plotter.auth import require_api_key
from pen_plotter.hardware.controller import controller
from pen_plotter.macros import delete_macro, get_macro, load_macros, save_macro
from pen_plotter.models import Macro

router = APIRouter()


@router.get("/macros")
async def list_macros() -> list[Macro]:
    """List the saved macros, sorted by name."""
    return load_macros()


@router.post("/macros")
async def create_or_update(macro: Macro) -> Macro:
    """Create or update a macro from a JSON body and persist it."""
    return save_macro(macro)


@router.delete("/macros/{name}")
async def delete_one(name: str) -> dict[str, str]:
    """Delete a macro by name.

    Raises:
        HTTPException: 404 if no macro with the name exists.
    """
    if delete_macro(name):
        return {"deleted": name}
    raise HTTPException(status_code=404, detail=f"Unknown macro: {name!r}")


@router.post("/macros/{name}/run", dependencies=[Depends(require_api_key)])
async def run_one(name: str) -> dict[str, str]:
    """Execute a macro's commands on the connected plotter.

    Raises:
        HTTPException: 404 if the macro is unknown; 409 if not connected or a
            job is running.
    """
    macro = get_macro(name)
    if macro is None:
        raise HTTPException(status_code=404, detail=f"Unknown macro: {name!r}")
    try:
        await controller.send_commands(macro.commands)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ran": name}
