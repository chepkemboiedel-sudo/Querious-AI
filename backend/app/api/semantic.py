"""Read-only semantic-layer endpoint behind the terms list on screen 2 (Data overview).

Terms are defined only by a data steward, offline, in ``semantic_layer.yaml`` (POLICY
Section 1, US-12). This router has one ``GET`` route and no route that creates, changes
or deletes a term.
"""

from fastapi import APIRouter, HTTPException

from app.pipeline import loader

router = APIRouter(prefix="/semantic", tags=["semantic"])


@router.get("/terms")
def list_terms() -> dict:
    """Every term of the active dataset with its plain-English description, and the version."""
    try:
        layer = loader.active_semantic_layer()
    except loader.DatasetError as error:
        raise HTTPException(
            status_code=422, detail={"reason": error.reason, "message": str(error)}
        ) from None
    if layer is None:
        return {"semantic_layer": None}
    return {
        "semantic_layer": {
            "dataset_key": layer.dataset_key,
            "version": layer.version,
            "terms": [{"name": t.name, "description": t.description} for t in layer.section.terms],
        }
    }
