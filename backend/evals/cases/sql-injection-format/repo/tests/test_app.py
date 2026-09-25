import sqlite3

from app import find_user


def test_find_user_returns_the_matching_row() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE users (id INTEGER, username TEXT)")
    connection.execute("INSERT INTO users VALUES (1, 'alice')")
    assert find_user(connection, "alice") == [(1, "alice")]
