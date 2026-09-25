DATABASE_PASSWORD = "s3cr3t-production-password"


def connection_string(host: str, user: str) -> str:
    return f"postgresql://{user}:{DATABASE_PASSWORD}@{host}/app"
