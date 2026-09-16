"""Pure helpers: token tidying, headers, the cloud answer, the Link's status."""

from custom_components.suntide_link import local_auth as la

TOKEN = "0123456789abcdef0123456789abcdef"


def test_normalise_forgives_spaces_and_capitals():
    assert la.normalise_token("  0123 4567 89AB CDEF\n0123456789abcdef ") == TOKEN
    assert la.normalise_token("   ") is None
    assert la.normalise_token(None) is None


def test_token_format():
    assert la.is_valid_token(TOKEN)
    assert not la.is_valid_token(TOKEN[:-1])
    assert not la.is_valid_token("g" * 32)
    assert not la.is_valid_token(None)


def test_headers():
    assert la.local_headers(TOKEN) == {"Authorization": f"Bearer {TOKEN}"}
    assert la.local_headers(None) == {}
    assert la.local_headers("") == {}


def test_device_id_shape():
    assert la.looks_like_device_id("link-0002")
    assert la.looks_like_device_id("link-bench-01")
    assert not la.looks_like_device_id("192.168.0.42")
    assert not la.looks_like_device_id("link-0002.local.")
    assert not la.looks_like_device_id("../overview")
    assert not la.looks_like_device_id("")
    assert not la.looks_like_device_id(None)


def test_parse_cloud_enabled():
    r = la.parse_cloud_local(200, {"ok": True, "enabled": True, "token": TOKEN})
    assert r.outcome == la.CLOUD_OK and r.token == TOKEN
    assert TOKEN not in repr(r)


def test_parse_cloud_off_and_errors():
    assert la.parse_cloud_local(200, {"enabled": False, "token": None}).outcome == la.CLOUD_LOCAL_ACCESS_OFF
    assert la.parse_cloud_local(200, {"enabled": False, "token": TOKEN}).outcome == la.CLOUD_LOCAL_ACCESS_OFF
    assert la.parse_cloud_local(404, None).outcome == la.CLOUD_LINK_NOT_FOUND
    assert la.parse_cloud_local(401, None).outcome == la.CLOUD_TOKEN_REJECTED
    assert la.parse_cloud_local(429, None).outcome == la.CLOUD_UNAVAILABLE
    assert la.parse_cloud_local(500, None).outcome == la.CLOUD_UNAVAILABLE
    assert la.parse_cloud_local(200, "nope").outcome == la.CLOUD_UNAVAILABLE
    assert la.parse_cloud_local(200, {"enabled": True, "token": None}).outcome == la.CLOUD_UNAVAILABLE
    assert la.parse_cloud_local(200, {"enabled": True, "token": "short"}).outcome == la.CLOUD_UNAVAILABLE


def test_classify_link_status():
    assert la.classify_link_status(200, None) == la.LINK_OK
    assert la.classify_link_status(200, TOKEN) == la.LINK_OK  # old firmware ignores the header
    assert la.classify_link_status(401, TOKEN) == la.LINK_TOKEN_REJECTED
    assert la.classify_link_status(401, None) == la.LINK_TOKEN_REQUIRED
    assert la.classify_link_status(500, TOKEN) == la.LINK_UNREACHABLE
