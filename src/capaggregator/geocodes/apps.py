from django.apps import AppConfig


class GeocodesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "capaggregator.geocodes"
    label = "capagg_geocodes"

    def ready(self):
        from task_ferry.registry import job_type_registry

        from .job_types import GeocodeImportJobType

        job_type_registry.register(GeocodeImportJobType())
