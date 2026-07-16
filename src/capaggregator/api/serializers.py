from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from capaggregator.alerts.models import ResolvedAlert
from capaggregator.sources.models import SourceAuthority


class SourceAuthoritySerializer(serializers.ModelSerializer):
    """Public-safe authority representation. Fields are an explicit allowlist —
    transport/credential data (MQTT, webhook tokens, certificates, sender
    values, contacts) must never be serialized here."""

    country = serializers.CharField(source="country.code", read_only=True)
    country_name = serializers.CharField(source="country.name", read_only=True)
    active_alert_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SourceAuthority
        fields = ["name", "slug", "country", "country_name", "website", "active_alert_count"]


class ResolvedAlertSerializer(GeoFeatureModelSerializer):
    authority = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    authority_name = serializers.CharField(source="authority.name", read_only=True)
    authority_country = serializers.CharField(source="authority.country.code", read_only=True)
    authority_country_name = serializers.CharField(source="authority.country.name", read_only=True)
    identifier = serializers.CharField(source="latest_alert.identifier", read_only=True)

    class Meta:
        model = ResolvedAlert
        geo_field = "centroid"
        fields = [
            "id", "chain", "identifier", "authority", "authority_name", "authority_country",
            "authority_country_name", "event", "headline", "msg_type", "status",
            "severity", "urgency", "certainty", "categories", "countries", "languages",
            "onset", "effective", "expires", "is_cancelled",
        ]
