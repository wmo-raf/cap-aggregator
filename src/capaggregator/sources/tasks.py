import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, acks_late=True, max_retries=3, default_retry_delay=5)
def sync_mosquitto_auth(self):
    """Regenerate the Mosquitto passwd/ACL files in the shared mount.

    Triggered automatically on SourceAuthority save/delete (see signals in
    apps.py) — no manual `capagg sync_mosquitto` needed. The broker reloads
    itself: its entrypoint watches the auth files and SIGHUPs mosquitto when
    they change (deploy/mosquitto/entrypoint.sh).
    """
    from .mosquitto import write_auth_files

    try:
        passwd_path, acl_path = write_auth_files()
    except OSError as ex:
        logger.warning("Mosquitto auth sync failed (%s) — retrying", ex)
        raise self.retry(exc=ex)

    logger.info("Mosquitto auth files updated: %s, %s (broker reloads automatically)",
                passwd_path, acl_path)
