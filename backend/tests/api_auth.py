"""The API token the test suite runs the application with, fresh for every session."""

import secrets

TEST_API_TOKEN = secrets.token_urlsafe(32)
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_TOKEN}"}
