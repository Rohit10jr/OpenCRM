from django.contrib import admin
from django.urls import include, path, re_path

from frappe_core.file_views import private_file, public_file

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("frappe_core.urls")),
    # The bytes behind File rows, at the URLs ``File.file_url`` holds
    # (frappe_core/file_views.py). Outside ``api/`` because that is where upstream
    # serves them and where the frontend's <img> and <a> tags fetch them.
    re_path(r"^files/(?P<path>.+)$", public_file, name="public-file"),
    re_path(r"^private/files/(?P<path>.+)$", private_file, name="private-file"),
]
