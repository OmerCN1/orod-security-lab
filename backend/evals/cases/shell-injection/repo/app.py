import subprocess


def echo_value(value: str) -> str:
    result = subprocess.run(
        f"echo {value}",
        shell=True,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
