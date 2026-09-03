from aliexpress_dashboard.authz import is_authorized


def test_is_authorized_matches_allowed_email():
    assert is_authorized("nic.crane@gmail.com", "nic.crane@gmail.com")


def test_is_authorized_is_case_insensitive():
    assert is_authorized("Nic.Crane@Gmail.com", "nic.crane@gmail.com")


def test_is_authorized_rejects_email_not_on_list():
    assert not is_authorized("someone-else@gmail.com", "nic.crane@gmail.com")


def test_is_authorized_supports_multiple_allowed_emails():
    allowed = "nic.crane@gmail.com, teammate@example.com"
    assert is_authorized("teammate@example.com", allowed)


def test_is_authorized_rejects_when_email_is_none():
    assert not is_authorized(None, "nic.crane@gmail.com")


def test_is_authorized_rejects_when_allowlist_is_empty():
    assert not is_authorized("nic.crane@gmail.com", "")
