from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("capagg_sources", "0007_fast_poll_default_one_minute"),
    ]

    operations = [
        migrations.AddField(
            model_name="sourceauthority",
            name="feed_consecutive_failures",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
    ]
