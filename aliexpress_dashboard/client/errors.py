class AliClientError(Exception):
    """Base class for errors raised by our client wrapper (not the underlying library)."""


class FixtureNotFoundError(AliClientError):
    """Raised in fixture mode when no recorded response exists for a request."""


class TokenMissingError(AliClientError):
    """Raised in live mode when a ds.* call is attempted with no access token
    on file -- the one-time authorize step hasn't been completed yet."""


class TokenExpiredError(AliClientError):
    """Raised when the stored refresh token has itself expired, meaning the
    only way forward is a fresh authorize step, not a refresh call."""
