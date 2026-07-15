from django.apps import AppConfig


class HomeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "capaggregator.home"
    label = "capagg_home"
    verbose_name = "Public frontend"
