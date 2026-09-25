import requests


def fetch(url: str, timeout: int = 10) -> str:
    response = requests.get(url, timeout=timeout, verify=False)
    response.raise_for_status()
    return response.text
