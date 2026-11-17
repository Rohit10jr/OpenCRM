from django.urls import re_path

from core.views import DoctypeSearchView


urlpatterns = [
    re_path(r"^doctypes/search/?$", DoctypeSearchView.as_view()),
]
