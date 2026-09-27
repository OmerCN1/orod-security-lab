import os

from tests.api_auth import TEST_API_TOKEN

# Settings read the environment, so every app the suite builds uses a known token and
# accepts TestClient's `testserver` host without writing a token file anywhere.
os.environ.setdefault("OROD_API_TOKEN", TEST_API_TOKEN)
os.environ.setdefault("OROD_ALLOWED_HOSTS", '["localhost", "127.0.0.1", "testserver"]')
