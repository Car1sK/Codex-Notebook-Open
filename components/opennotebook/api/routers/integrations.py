"""External integration endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import ensure_user_owns, get_request_user
from open_notebook.auth_context import AuthenticatedUser
from open_notebook.domain.notebook import Notebook
from open_notebook.integrations.notebooklm import (
    BundleImportPreview,
    BundleImportResult,
    NotebookBundleImporter,
    NotebookBundlePayload,
    OpenNotebookBundleStore,
    export_open_notebook_bundle,
)

router = APIRouter()


@router.post(
    "/integrations/notebooklm/bundles/preview",
    response_model=BundleImportPreview,
)
async def preview_notebooklm_bundle(
    bundle: NotebookBundlePayload,
) -> BundleImportPreview:
    _require_notebooklm_origin(bundle)
    return await NotebookBundleImporter(OpenNotebookBundleStore()).preview(bundle)


@router.post(
    "/integrations/notebooklm/bundles/import",
    response_model=BundleImportResult,
)
async def import_notebooklm_bundle(
    bundle: NotebookBundlePayload,
    embed_sources: bool = Query(default=False),
    current_user: AuthenticatedUser = Depends(get_request_user),
) -> BundleImportResult:
    _require_notebooklm_origin(bundle)
    result = await NotebookBundleImporter(OpenNotebookBundleStore()).import_bundle(
        bundle, embed_sources=embed_sources
    )
    notebook = await Notebook.get(result.local_notebook_id)
    notebook.owner_id = current_user.owner_id
    await notebook.save()
    return result


@router.get(
    "/integrations/notebooklm/notebooks/{notebook_id}/bundle",
    response_model=NotebookBundlePayload,
)
async def export_notebooklm_bundle(
    notebook_id: str,
    current_user: AuthenticatedUser = Depends(get_request_user),
) -> NotebookBundlePayload:
    notebook = await Notebook.get(notebook_id)
    ensure_user_owns(notebook, current_user)
    return await export_open_notebook_bundle(notebook_id)


def _require_notebooklm_origin(bundle: NotebookBundlePayload) -> None:
    if bundle.origin != "google-notebooklm":
        raise HTTPException(
            status_code=422,
            detail=f"cannot import bundle with origin {bundle.origin!r}",
        )
