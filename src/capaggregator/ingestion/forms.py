from django import forms
from django.utils.translation import gettext_lazy as _

from capaggregator.sources.models import SourceAuthority


class BackfillUploadForm(forms.Form):
    """Upload a single CAP .xml or a .zip archive of alerts to backfill against a
    chosen authority. Every contained alert runs through the normal pipeline."""

    authority = forms.ModelChoiceField(
        queryset=SourceAuthority.objects.filter(active=True), label=_("Authority")
    )
    file = forms.FileField(
        label=_("CAP file (.xml or .zip)"),
        help_text=_("A single CAP 1.2 .xml, or a .zip archive of .xml alerts."),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        name = upload.name.lower()
        if not (name.endswith(".xml") or name.endswith(".zip")):
            raise forms.ValidationError(_("Upload a .xml or .zip file."))
        return upload
