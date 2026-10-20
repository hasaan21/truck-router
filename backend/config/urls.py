from django.contrib import admin
from django.urls import include, path, re_path

from config.frontend import frontend

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
    path("", frontend, {"path": ""}),
    re_path(r"^(?P<path>.+)$", frontend),
]
