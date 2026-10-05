"""Session-only administrator authorization for local configuration tools."""


ADMIN_PASSWORD = "lwb"


class AdminSession:
    """Keep admin authorization in memory for the current application session."""

    def __init__(self):
        self.is_active = False

    def authenticate(self, password: str) -> bool:
        self.is_active = password == ADMIN_PASSWORD
        return self.is_active

    def exit(self):
        self.is_active = False


__all__ = ["ADMIN_PASSWORD", "AdminSession"]
