"""Withheld register: two statuses, and the operator-facing name.

No backfill: `notified` and `resubmitted` have no rows, because nothing ever
wrote them. The table and model names are deliberately left alone so existing
links keep working.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('capagg_ingestion', '0004_quarantinedmessage_primary_category'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='quarantinedmessage',
            options={'ordering': ['-created'], 'verbose_name': 'withheld message', 'verbose_name_plural': 'withheld messages'},
        ),
        migrations.AlterField(
            model_name='quarantinedmessage',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending review'), ('dismissed', 'Dismissed')], default='pending', max_length=20),
        ),
    ]
