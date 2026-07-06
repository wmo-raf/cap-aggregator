from django.apps import AppConfig


class IngestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "capaggregator.ingestion"
    label = "capagg_ingestion"

    def ready(self):
        from task_ferry.registry import job_type_registry

        from .job_types import CapBackfillJobType, QuarantineRevalidationJobType

        job_type_registry.register(CapBackfillJobType())
        job_type_registry.register(QuarantineRevalidationJobType())
