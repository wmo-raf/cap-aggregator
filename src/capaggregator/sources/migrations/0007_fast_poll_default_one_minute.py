from django.db import migrations, models


def old_default_to_new(apps, schema_editor):
    """Authorities still on the old 5-minute default move to the new 1-minute
    default; explicitly tuned values (anything other than 5) are kept."""
    SourceAuthority = apps.get_model("capagg_sources", "SourceAuthority")
    SourceAuthority.objects.filter(feed_poll_interval_minutes=5).update(feed_poll_interval_minutes=1)


def new_default_to_old(apps, schema_editor):
    SourceAuthority = apps.get_model("capagg_sources", "SourceAuthority")
    SourceAuthority.objects.filter(feed_poll_interval_minutes=1).update(feed_poll_interval_minutes=5)


class Migration(migrations.Migration):
    dependencies = [
        ("capagg_sources", "0006_sourceauthority_website"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sourceauthority",
            name="feed_poll_interval_minutes",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Used when no push transport is configured or push has gone quiet",
                verbose_name="Fast poll interval (min)",
            ),
        ),
        migrations.RunPython(old_default_to_new, new_default_to_old),
    ]
