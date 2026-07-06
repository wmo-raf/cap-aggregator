from django.apps import AppConfig


class SourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "capaggregator.sources"
    label = "capagg_sources"

    def ready(self):
        from django.db import transaction
        from django.db.models.signals import post_delete, post_save

        from .models import SourceAuthority

        def schedule_sync(sender, instance, **kwargs):
            # Only rewrite broker auth when MQTT is actually in play
            if not (instance.mqtt_username or kwargs.get("signal") is post_delete):
                return

            def enqueue():
                from .tasks import sync_mosquitto_auth

                sync_mosquitto_auth.delay()

            transaction.on_commit(enqueue)

        post_save.connect(schedule_sync, sender=SourceAuthority, dispatch_uid="capagg_mosquitto_sync_save")
        post_delete.connect(schedule_sync, sender=SourceAuthority, dispatch_uid="capagg_mosquitto_sync_delete")
