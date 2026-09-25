import subprocess


def echo_user(value: str) -> str:
    result = subprocess.run(
        ["echo", value],
        shell=True,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
