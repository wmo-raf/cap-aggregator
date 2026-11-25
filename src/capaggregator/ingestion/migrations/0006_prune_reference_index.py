"""Drop the reference-index rows our registers wrote before they opted out (#137).

`wagtail_reference_index_ignore` stops new rows, but the backlog (2 GB in prod)
stays. A DELETE of that size would write gigabytes of WAL on a nearly-full disk
and free nothing until a VACUUM FULL. Instead, on PostgreSQL, copy the rows worth
keeping (pages, images, documents — a handful) aside, TRUNCATE, and put them
back: TRUNCATE hands the files back to the OS at commit and logs almost nothing.
All in the migration's one transaction, so a failure leaves the table as it was.

The table is locked *before* the copy: workers still on the old code keep
writing index rows until they restart, and a row written between the copy and
the TRUNCATE would be lost. `lock_timeout` makes a busy table fail the migration
loudly instead of queueing every reader behind a lock that app start waits on.
"""

from django.db import migrations

# The registers that opted out — their rows are the ones to drop.
IGNORED_MODELS = [
    ("capagg_alerts", "alert"),
    ("capagg_alerts", "alertdefect"),
    ("capagg_ingestion", "rawmessage"),
    ("capagg_ingestion", "sourceevent"),
]

REFERENCE_INDEX_TABLE = "wagtailcore_referenceindex"


def prune_reference_index(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ReferenceIndex = apps.get_model("wagtailcore", "ReferenceIndex")

    ignored_ids = [
        pk for pk, app_label, model in ContentType.objects.values_list("pk", "app_label", "model")
        if (app_label, model) in IGNORED_MODELS
    ]
    if not ignored_ids:
        return  # fresh database: nothing was ever indexed

    if not ReferenceIndex.objects.filter(base_content_type_id__in=ignored_ids).exists():
        return

    table = REFERENCE_INDEX_TABLE
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '30s'")
        cursor.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
        cursor.execute(
            f"CREATE TEMPORARY TABLE capagg_referenceindex_keep ON COMMIT DROP AS "
            f"SELECT * FROM {table} WHERE NOT (base_content_type_id = ANY(%s))",
            [ignored_ids],
        )
        cursor.execute(f"TRUNCATE {table}")
        cursor.execute(f"INSERT INTO {table} SELECT * FROM capagg_referenceindex_keep")


class Migration(migrations.Migration):
    dependencies = [
        ("capagg_ingestion", "0005_withheld_status_vocabulary"),
        ("capagg_alerts", "0006_alertdefect_capagg_aler_created_d88dbc_idx"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
    ]

    operations = [
        migrations.RunPython(prune_reference_index, migrations.RunPython.noop),
    ]
