"""Admin list filters for the ingestion app.

The withheld register's filterset is declared explicitly rather than generated
from `list_filter`, because bulk dismiss has to answer the same question the
list does — *which rows is the operator looking at?* — from the same code.
"""

from wagtail.admin.filters import WagtailFilterSet

from .models import QuarantinedMessage

class WithheldFilterSet(WagtailFilterSet):
    class Meta:
        model = QuarantinedMessage
        fields = ["primary_category", "status", "raw_message__authority"]
