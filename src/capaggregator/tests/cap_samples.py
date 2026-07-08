"""Reusable CAP v1.2 sample builders for the test suite.

Shared across Phase B slices: `cap_alert_xml(...)` returns a schema-valid CAP 1.2
message and lets callers vary the identity triple (sender/identifier/sent),
msgType, references, and body so the same helper produces the valid, bad-sender,
byte-duplicate, same-identity-different-bytes, and Alert→Update→Cancel cases.
"""

DEFAULT_SENDER = "sender@example.test"


def cap_alert_xml(
    *,
    identifier="TEST-0001",
    sender=DEFAULT_SENDER,
    sent="2026-07-07T12:00:00+00:00",
    msg_type="Alert",
    status="Actual",
    scope="Public",
    references="",
    headline="Severe flooding expected",
    description="Heavy rainfall is causing flooding.",
) -> str:
    """A schema-valid CAP 1.2 alert. Element order follows the CAP 1.2 sequence
    (note before references; effective before expires) so it passes XSD."""
    references_el = f"    <references>{references}</references>\n" if references else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">\n'
        f"    <identifier>{identifier}</identifier>\n"
        f"    <sender>{sender}</sender>\n"
        f"    <sent>{sent}</sent>\n"
        f"    <status>{status}</status>\n"
        f"    <msgType>{msg_type}</msgType>\n"
        f"    <scope>{scope}</scope>\n"
        f"{references_el}"
        "    <info>\n"
        "        <category>Met</category>\n"
        "        <event>Flood Warning</event>\n"
        "        <urgency>Immediate</urgency>\n"
        "        <severity>Severe</severity>\n"
        "        <certainty>Observed</certainty>\n"
        "        <effective>2026-07-07T12:00:00+00:00</effective>\n"
        "        <expires>2026-07-08T12:00:00+00:00</expires>\n"
        f"        <headline>{headline}</headline>\n"
        f"        <description>{description}</description>\n"
        "        <area>\n"
        "            <areaDesc>Nairobi</areaDesc>\n"
        "            <polygon>-1.30,36.80 -1.30,36.90 -1.20,36.90 -1.20,36.80 -1.30,36.80</polygon>\n"
        "        </area>\n"
        "    </info>\n"
        "</alert>\n"
    )


# WMO Register of Alerting Authorities (https://alertingauthority.wmo.int/rss.xml)
# sample — namespaces/element shapes copied from the live feed. Covers, in order:
# multi-language capAlertFeed (ar+en, English preferred), a non-English-only feed
# (pt), no capAlertFeed at all, an unmappable ISO alpha-3 country code (ANT —
# Netherlands Antilles, dissolved, not in django-countries), and a title with no
# "Country: " prefix to split on.
WMO_REGISTRY_SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:iso="http://www.itu.int/tML/tML-ISO-3166" xmlns:georss="http://www.georss.org/georss"
xmlns:cap="urn:oasis:names:tc:emergency:cap:1.1" xmlns:raa="http://www.oid-info.com/get/2.49.0">
<channel>
  <title>WMO Register of Alerting Authorities</title>
  <link>https://alertingauthority.wmo.int/rss.xml</link>
  <description>Sample</description>
<item>
    <title>Saudi Arabia: National Center for Meteorology</title>
    <iso:countrycode>SAU</iso:countrycode>
    <link>https://alertingauthority.wmo.int/authorities.php?recId=140</link>
    <guid>urn:oid:2.49.0.0.682.0</guid>
    <author>n.al-orfi@ncm.gov.sa</author>
    <raa:capAlertFeed xml:lang="ar">https://ncm.gov.sa/ar/cap-alerts</raa:capAlertFeed>
    <raa:capAlertFeed xml:lang="en">https://ncm.gov.sa/en/cap-alerts</raa:capAlertFeed>
    <raa:authorityAbbrev>ncm</raa:authorityAbbrev>
</item>
<item>
    <title>Mozambique: Instituto Nacional de Meteorologia</title>
    <iso:countrycode>MOZ</iso:countrycode>
    <link>https://alertingauthority.wmo.int/authorities.php?recId=106</link>
    <guid>urn:oid:2.49.0.0.508.0</guid>
    <author>mussa2503@gmail.com</author>
    <raa:capAlertFeed xml:lang="pt">https://cap-sources.s3.amazonaws.com/mz-inam-pt/rss.xml</raa:capAlertFeed>
    <raa:authorityAbbrev>inam</raa:authorityAbbrev>
</item>
<item>
    <title>Syrian Arab Republic: Ministry of Emergency and Disaster Management</title>
    <iso:countrycode>SYR</iso:countrycode>
    <link>https://alertingauthority.wmo.int/authorities.php?recId=231</link>
    <guid>urn:oid:2.49.0.0.760.0</guid>
    <author>mhd.diab@med.gov.sy</author>
    <raa:authorityAbbrev>mdmd</raa:authorityAbbrev>
</item>
<item>
    <title>Netherlands Antilles: Meteorological Department</title>
    <iso:countrycode>ANT</iso:countrycode>
    <link>https://alertingauthority.wmo.int/authorities.php?recId=999</link>
    <guid>urn:oid:2.49.0.0.999.0</guid>
    <author>info@example.test</author>
    <raa:capAlertFeed xml:lang="en">https://example.test/ant/rss.xml</raa:capAlertFeed>
    <raa:authorityAbbrev>mdant</raa:authorityAbbrev>
</item>
<item>
    <title>Testland Meteorological Service</title>
    <iso:countrycode>KEN</iso:countrycode>
    <link>https://alertingauthority.wmo.int/authorities.php?recId=555</link>
    <guid>urn:oid:2.49.0.0.555.0</guid>
    <author>info@testland.example.test</author>
    <raa:capAlertFeed xml:lang="en">https://testland.example.test/rss.xml</raa:capAlertFeed>
    <raa:authorityAbbrev>tms</raa:authorityAbbrev>
</item>
</channel>
</rss>
"""
