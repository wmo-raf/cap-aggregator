"""Create the HomePage and point the default Site at it, so a fresh setup
serves the landing page instead of Wagtail's "Welcome" placeholder.

Skips databases that already have a HomePage (e.g. ones where it was created
by hand before this migration existed)."""

from django.db import migrations


def create_homepage(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Page = apps.get_model("wagtailcore", "Page")
    Site = apps.get_model("wagtailcore", "Site")
    Locale = apps.get_model("wagtailcore", "Locale")
    HomePage = apps.get_model("capagg_home", "HomePage")

    if HomePage.objects.exists():
        return

    # Wagtail's initial migrations create the placeholder page (id=2) and a
    # default Site rooted at it; the Site cascades away with the page.
    Page.objects.filter(id=2).delete()

    content_type, _ = ContentType.objects.get_or_create(app_label="capagg_home", model="homepage")
    locale, _ = Locale.objects.get_or_create(language_code="en")

    homepage = HomePage.objects.create(
        title="CAP Aggregator",
        draft_title="CAP Aggregator",
        slug="home",
        content_type=content_type,
        path="00010001",
        depth=2,
        numchild=0,
        url_path="/home/",
        live=True,
        locale=locale,
    )
    root = Page.objects.get(depth=1)
    root.numchild = Page.objects.filter(depth=2).count()
    root.save(update_fields=["numchild"])

    Site.objects.create(hostname="localhost", root_page=homepage, is_default_site=True)


def remove_homepage(apps, schema_editor):
    # Reverse: drop only the migration-created page (slug "home")
    HomePage = apps.get_model("capagg_home", "HomePage")
    HomePage.objects.filter(slug="home").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("capagg_home", "0001_initial"),
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
    ]

    operations = [
        migrations.RunPython(create_homepage, remove_homepage),
    ]
