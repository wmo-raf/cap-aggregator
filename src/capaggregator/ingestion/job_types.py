"""Task-ferry job types for the ingestion app.

Started via JobHandler (e.g. from an admin action or API view):

    from task_ferry.handler import JobHandler
    JobHandler.create_and_start(user, "cap_backfill", authority_id=..., file_path=...)
    JobHandler.create_and_start(user, "quarantine_revalidation", authority_id=...)

Progress is pollable at GET /api/jobs/<id>/.
"""

import logging
import zipfile
from pathlib import Path

from task_ferry.registry import JobType

from .models import CapBackfillJob, QuarantineRevalidationJob

logger = logging.getLogger(__name__)


class CapBackfillJobType(JobType):
    type = "cap_backfill"
    model_class = CapBackfillJob
    max_count = 3

    def prepare_values(self, values: dict, user) -> dict:
        from capaggregator.sources.models import SourceAuthority

        authority_id = values.get("authority_id") or values.get("authority")
        file_path = values.get("file_path")
        if not authority_id:
            raise ValueError("'authority_id' is required for a backfill job.")
        if not file_path or not Path(file_path).is_file():
            raise ValueError(f"'file_path' missing or not a file: {file_path}")

        authority = SourceAuthority.objects.get(pk=authority_id)
        return {"authority": authority, "file_path": str(file_path)}

    def run(self, job: CapBackfillJob, progress) -> None:
        from capaggregator.ingestion.tasks import ingest_raw_message

        progress.increment(5, state="Reading input file…")
        documents = list(_iter_cap_documents(job.file_path))
        job.alerts_found = len(documents)
        job.save(update_fields=["alerts_found"])

        if not documents:
            progress.increment(95, state="No CAP documents found in file")
            return

        work = progress.create_child(represents=95, total=len(documents))
        for name, xml in documents:
            # Synchronous, in-job ingestion (not .delay) so progress is accurate
            # and the job result reflects real outcomes.
            result = ingest_raw_message(transport="manual", xml=xml, authority_id=job.authority_id)
            state = result.get("state")
            if state == "stored":
                job.alerts_stored += 1
            elif state == "duplicate":
                job.alerts_duplicate += 1
            elif state == "quarantined":
                job.alerts_quarantined += 1
            work.increment(state=f"Processed {name} ({state})")

        job.save(update_fields=["alerts_stored", "alerts_duplicate", "alerts_quarantined"])


class QuarantineRevalidationJobType(JobType):
    type = "quarantine_revalidation"
    model_class = QuarantineRevalidationJob
    max_count = 1  # concurrent revalidation sweeps make no sense

    def prepare_values(self, values: dict, user) -> dict:
        from capaggregator.sources.models import SourceAuthority

        authority_id = values.get("authority_id") or values.get("authority")
        authority = SourceAuthority.objects.get(pk=authority_id) if authority_id else None
        return {"authority": authority}

    def run(self, job: QuarantineRevalidationJob, progress) -> None:
        from capaggregator.ingestion.tasks import run_pipeline

        from .models import QuarantinedMessage

        qs = QuarantinedMessage.objects.filter(status__in=["pending", "notified"]) \
                                       .select_related("raw_message")
        if job.authority_id:
            qs = qs.filter(raw_message__authority_id=job.authority_id)

        quarantined = list(qs)
        job.messages_checked = len(quarantined)
        job.save(update_fields=["messages_checked"])

        if not quarantined:
            progress.increment(100, state="Nothing in quarantine")
            return

        work = progress.create_child(represents=100, total=len(quarantined))
        for q in quarantined:
            raw = q.raw_message
            # Clear the old verdict, then re-run the full pipeline; if the
            # message still fails, run_pipeline creates a fresh quarantine row
            # with an up-to-date report.
            q.delete()
            raw.state = "received"
            raw.save(update_fields=["state"])

            result = run_pipeline(raw)
            if result.get("state") in ("stored", "duplicate"):
                job.messages_stored += 1
            else:
                job.messages_still_quarantined += 1
            work.increment(state=f"Re-validated raw #{raw.id} ({result.get('state')})")

        job.save(update_fields=["messages_stored", "messages_still_quarantined"])


def _iter_cap_documents(file_path: str):
    """Yield (name, xml_text) for a single .xml file or every .xml inside a .zip."""
    path = Path(file_path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".xml"):
                    continue
                yield info.filename, archive.read(info).decode("utf-8", errors="replace")
    else:
        yield path.name, path.read_text(encoding="utf-8", errors="replace")
