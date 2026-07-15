from django.urls import re_path

from capaggregator.home import views

# Catch-all: vue-router owns everything below /explorer/
urlpatterns = [
    re_path(r"^.*$", views.explorer, name="explorer"),
]
