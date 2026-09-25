"""Offline evaluation harness for the OROD remediation pipeline.

The harness replays a corpus of controlled vulnerability fixtures through the real
agent graph and scores detection, remediation and cost. It is a development tool and
is deliberately kept outside the shipped ``orod`` package.
"""

__all__ = ["__doc__"]
