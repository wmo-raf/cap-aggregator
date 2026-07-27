"""Read-only registers must not offer a bulk action their permission policy
forbids (#120). Wagtail registers Delete for every snippet model and checks the
Django model permission, so a superuser could delete rows the register declares
immutable — and, because the default "select all in the listing" means the whole
table, could do it to rows no filter ever showed them."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.ingestion.models import QuarantinedMessage, RawMessage, SourceEvent
from capaggregator.sources.models import SourceAuthority
from capaggregator.tests.factories import (
    create_quarantined_message,
    create_raw_message,
    create_source_authority,
    create_source_event,
)


def delete_url(model):
    return f"/admin/bulk/{model._meta.app_label}/{model._meta.model_name}/delete/"


class ReadOnlyRegisterDeleteTests(TestCase):
    """A superuser is the case that matters: the read-only policy denies them
    too, but the Django `delete_<model>` permission does not."""

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _registers(self):
        raw = create_raw_message(self.authority)
        return [
            (
                QuarantinedMessage,
                "wagtailsnippets_capagg_ingestion_quarantinedmessage:list",
                create_quarantined_message(authority=self.authority),
            ),
            (RawMessage, "wagtailsnippets_capagg_ingestion_rawmessage:list", raw),
            (
                SourceEvent,
                "wagtailsnippets_capagg_ingestion_sourceevent:list",
                create_source_event(authority=self.authority),
            ),
        ]

    def test_listings_offer_no_delete_button(self):
        for model, list_url_name, _obj in self._registers():
            with self.subTest(model=model.__name__):
                response = self.client.get(reverse(list_url_name))

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, delete_url(model))

    def test_posting_to_the_delete_action_deletes_nothing(self):
        for model, _list_url_name, obj in self._registers():
            with self.subTest(model=model.__name__):
                response = self.client.post(f"{delete_url(model)}?id={obj.pk}")

                self.assertEqual(response.status_code, 404)
                self.assertTrue(model.objects.filter(pk=obj.pk).exists())

    def test_select_all_in_the_listing_deletes_nothing(self):
        for model, _list_url_name, obj in self._registers():
            with self.subTest(model=model.__name__):
                self.client.post(f"{delete_url(model)}?id=all")

                self.assertTrue(model.objects.filter(pk=obj.pk).exists())

    def test_the_withheld_register_still_offers_dismiss(self):
        message = create_quarantined_message(authority=self.authority)
        dismiss_url = "/admin/bulk/capagg_ingestion/quarantinedmessage/dismiss/"

        response = self.client.get(reverse("wagtailsnippets_capagg_ingestion_quarantinedmessage:list"))
        self.assertContains(response, dismiss_url)

        self.client.post(f"{dismiss_url}?id={message.pk}")
        message.refresh_from_db()
        self.assertEqual(message.status, "dismissed")


class WritableRegisterDeleteTests(TestCase):
    """The rule is scoped to read-only registers — ordinary snippets keep the
    action Wagtail gives them."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_the_authority_register_still_offers_delete(self):
        create_source_authority(name="Kenya Met")

        response = self.client.get(reverse("wagtailsnippets_capagg_sources_sourceauthority:list"))

        self.assertContains(response, delete_url(SourceAuthority))
