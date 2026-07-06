from django.core.management.base import BaseCommand

from capaggregator.sources.mosquitto import write_auth_files


class Command(BaseCommand):
    help = (
        "Regenerate Mosquitto passwd/ACL files from registered authorities. "
        "NOTE: this runs automatically on SourceAuthority save (signal → Celery task, "
        "broker self-reloads via its entrypoint watcher) — use this command only for "
        "bootstrap or repair."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=None, help="Output directory (default: settings.MOSQUITTO_AUTH_DIR)")

    def handle(self, *args, **options):
        passwd_path, acl_path = write_auth_files(options["dir"])
        self.stdout.write(self.style.SUCCESS(f"Wrote {passwd_path} and {acl_path}"))
        self.stdout.write("The broker picks this up automatically within a few seconds.")
