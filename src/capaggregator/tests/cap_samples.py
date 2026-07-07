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
