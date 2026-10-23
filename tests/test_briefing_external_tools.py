"""External briefing tools: RSS/Atom parsing, email filter, isolated feed failures, no API-key leaks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

httpx = pytest.importorskip("httpx")
ext = pytest.importorskip("agents.briefing_external_tools")

RSS = b"""<rss><channel>
<item><title>Post A</title><link>https://a.example</link></item>
<item><title>Post B</title><link>https://b.example</link></item>
</channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom 1</title><link href="https://x.example/1"/></entry>
</feed>"""


def test_parse_rss_and_atom():
    assert ext.parse_feed_items(RSS) == [("Post A", "https://a.example"), ("Post B", "https://b.example")]
    assert ext.parse_feed_items(ATOM) == [("Atom 1", "https://x.example/1")]


@pytest.mark.parametrize(("subject", "sender", "automated"), [
    ("Weekly digest", "news@site.com", True),
    ("Reunión mañana", "colega@empresa.com", False),
    ("Hola", "noreply@service.com", True),
])
def test_automated_email_filter(subject, sender, automated):
    assert ext._is_automated(subject, sender, "") is automated


def test_weather_error_does_not_leak_api_key(monkeypatch):
    secret = "SECRET-KEY-123"
    monkeypatch.setenv("OPENWEATHER_API_KEY", secret)

    def boom(url, params=None, **_):
        raise httpx.ConnectError(f"failed {url}?appid={params['appid']}")

    monkeypatch.setattr(ext._HTTP, "get", boom)
    out = ext.briefing_get_weather_briefing.invoke({})
    assert secret not in out and "ConnectError" in out


def test_rss_feed_failure_is_isolated(monkeypatch):
    def fake_get(url, **_):
        if "huggingface" in url:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, content=RSS, request=httpx.Request("GET", url))

    monkeypatch.setattr(ext._HTTP, "get", fake_get)
    out = ext.briefing_get_rss_news.invoke({})
    assert "Hugging Face Blog: Error de red" in out and "Post A" in out
