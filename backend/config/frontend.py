"""Serve the built React app from the same origin as the API."""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404

mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")


def frontend(request, path=""):
    dist = Path(settings.FRONTEND_DIST).resolve()
    if path:
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate.open("rb"))
        if "." in Path(path).name:
            raise Http404()
    index = dist / "index.html"
    if not index.is_file():
        raise Http404("The frontend build is missing.")
    return FileResponse(index.open("rb"))
