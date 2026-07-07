"""Phase B/6: issuing MQTT credentials for an authority returns a one-time
plaintext password, stores only a mosquitto-compatible hash that verifies the
password, and never persists the plaintext."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.sources.models import SourceAuthority
from capaggregator.sources.mosquitto import render_auth_files, verify_password
from capaggregator.tests.factories import create_source_authority


class IssueCredentialsTests(TestCase):
    def test_issued_password_is_returned_and_only_a_verifying_hash_is_stored(self):
        authority = create_source_authority(name="Kenya Met")

        password = authority.issue_mqtt_credentials()

        authority.refresh_from_db()
        self.assertNotEqual(authority.mqtt_password_hash, password)
        self.assertTrue(verify_password(password, authority.mqtt_password_hash))
        self.assertFalse(verify_password("wrong-password", authority.mqtt_password_hash))

    def test_auth_files_include_the_issued_user_and_topic(self):
        authority = create_source_authority(name="Kenya Met")
        authority.issue_mqtt_credentials()

        passwd, acl = render_auth_files()

        self.assertIn(authority.mqtt_username, passwd)
        self.assertIn(authority.mqtt_topic, acl)

    def test_regenerating_overwrites_and_invalidates_the_old_password(self):
        authority = create_source_authority(name="Kenya Met")
        first = authority.issue_mqtt_credentials()

        second = authority.issue_mqtt_credentials()

        authority.refresh_from_db()
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(second, authority.mqtt_password_hash))
        self.assertFalse(verify_password(first, authority.mqtt_password_hash))

    def test_has_mqtt_credentials_reflects_issuance(self):
        authority = create_source_authority(name="Kenya Met")
        self.assertFalse(authority.has_mqtt_credentials)

        authority.issue_mqtt_credentials()

        self.assertTrue(authority.has_mqtt_credentials)

    @patch("capaggregator.sources.tasks.sync_mosquitto_auth")
    def test_issuing_credentials_triggers_the_broker_sync(self, sync_task):
        authority = create_source_authority(name="Kenya Met")

        with self.captureOnCommitCallbacks(execute=True):
            authority.issue_mqtt_credentials()

        self.assertTrue(sync_task.delay.called)


class IssueCredentialsViewTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _url(self):
        return reverse("capagg_sources_issue_mqtt", args=[self.authority.id])

    def test_posting_issues_credentials_and_shows_topic_and_broker_block(self):
        response = self.client.post(self._url())

        self.assertEqual(response.status_code, 200)
        self.authority.refresh_from_db()
        self.assertTrue(self.authority.has_mqtt_credentials)
        self.assertContains(response, self.authority.mqtt_topic)
        self.assertContains(response, "is_wis2box")

    def test_result_page_shows_the_one_time_plaintext_password(self):
        with patch.object(SourceAuthority, "issue_mqtt_credentials", return_value="KNOWN-PASSWORD-123"):
            response = self.client.post(self._url())

        self.assertContains(response, "KNOWN-PASSWORD-123")

    def test_issue_view_requires_login(self):
        self.client.logout()

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)
