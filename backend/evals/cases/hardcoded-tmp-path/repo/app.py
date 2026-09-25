LOG_PATH = "/tmp/orod-audit.log"


def append_audit(entry: str) -> str:
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(f"{entry}\n")
    return LOG_PATH
