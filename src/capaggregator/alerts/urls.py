from django.urls import path

from capaggregator.alerts import views

urlpatterns = [
    path("<int:chain_id>/", views.alert_detail, name="alert_detail"),
    path("<int:chain_id>/xml/", views.alert_xml, name="alert_xml"),
    path("<int:chain_id>/messages/<int:alert_id>/", views.alert_version, name="alert_version"),
]
