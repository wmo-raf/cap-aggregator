from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from capaggregator.alerts.models import ResolvedAlert


class ResolvedAlertSerializer(GeoFeatureModelSerializer):
    authority = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    identifier = serializers.CharField(source="latest_alert.identifier", read_only=True)

    class Meta:
        model = ResolvedAlert
        geo_field = "centroid"
        fields = [
            "id", "identifier", "authority", "event", "headline", "msg_type", "status",
            "severity", "urgency", "certainty", "categories", "countries", "languages",
            "onset", "effective", "expires", "is_cancelled",
        ]
