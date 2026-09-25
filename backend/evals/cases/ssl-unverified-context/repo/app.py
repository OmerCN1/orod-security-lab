import ssl


def build_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()
