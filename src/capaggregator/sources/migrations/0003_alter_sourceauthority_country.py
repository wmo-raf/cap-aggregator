import django_countries.fields
from django.db import migrations


def uppercase_country(apps, schema_editor):
    """django-countries stores ISO codes uppercase; existing rows were lowercase."""
    SourceAuthority = apps.get_model("capagg_sources", "SourceAuthority")
    for pk, country in SourceAuthority.objects.values_list("pk", "country"):
        upper = (country or "").upper()
        if upper != country:
            SourceAuthority.objects.filter(pk=pk).update(country=upper)


def lowercase_country(apps, schema_editor):
    SourceAuthority = apps.get_model("capagg_sources", "SourceAuthority")
    for pk, country in SourceAuthority.objects.values_list("pk", "country"):
        lower = (country or "").lower()
        if lower != country:
            SourceAuthority.objects.filter(pk=pk).update(country=lower)


class Migration(migrations.Migration):

    dependencies = [
        ("capagg_sources", "0002_remove_sourceauthority_feed_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sourceauthority",
            name="country",
            field=django_countries.fields.CountryField(
                help_text="Primary country of the authority.", max_length=2, verbose_name="Country"
            ),
        ),
        migrations.RunPython(uppercase_country, lowercase_country),
    ]
