from django.apps import AppConfig


class UtilsConfig(AppConfig):
    """No models — the app exists so shared admin wiring has a `ready()` to run
    in, the same place every other app registers into a registry."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "capaggregator.utils"
    label = "capagg_utils"

    def ready(self):
        from .admin import restrict_generic_bulk_actions_to_writable_registers

        restrict_generic_bulk_actions_to_writable_registers()
