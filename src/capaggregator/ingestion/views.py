from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@csrf_exempt
@require_POST
def webhook_ingest(request, token: str):
    """Fallback push channel — a cap-composer webhook posting the CAP alert.

    The per-authority token in the URL authenticates the caller; the same
    validation pipeline (sender check etc.) still applies downstream.
    """
    from capaggregator.sources.models import SourceAuthority

    from .models import SourceEvent
    from .tasks import ingest_raw_message

    authority = SourceAuthority.objects.filter(webhook_token=token, active=True).first()
    if authority is None:
        SourceEvent.objects.create(authority=None, transport="webhook", ok=False, error="invalid or unknown token")
        return HttpResponse(status=403)

    body = request.body.decode("utf-8", errors="replace")
    if not body.strip():
        SourceEvent.objects.create(authority=authority, transport="webhook", ok=False, error="empty body")
        return JsonResponse({"detail": "empty body"}, status=400)

    ingest_raw_message.delay(transport="webhook", xml=body, authority_id=authority.id)
    return JsonResponse({"status": "accepted"}, status=202)
