"""A stand-in for the code the synthetic memory indexes."""


def list_unread_messages(account: str) -> list[str]:
    return []


def refresh_calendar_cache(minutes: int = 15) -> None:
    pass


def register_connector_tools(names: list[str]) -> int:
    return len(names)
