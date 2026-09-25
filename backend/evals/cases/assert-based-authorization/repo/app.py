def authorize(role: str) -> str:
    assert role == "admin", "administrator role required"
    return "granted"
