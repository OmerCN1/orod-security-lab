import sqlite3


def find_user(connection: sqlite3.Connection, username: str) -> list[tuple[object, ...]]:
    query = "SELECT id, username FROM users WHERE username = '%s'" % username
    return list(connection.execute(query))
