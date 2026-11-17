"""Explicit access decisions for document resource ViewSets."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Access:
    """Record whether a resource is row-ruled or deliberately open."""

    kind: str
    reason: str = ""

    @classmethod
    def ruled(cls):
        return cls(kind="ruled")

    @classmethod
    def open(cls, *, reason: str):
        return cls(kind="open", reason=reason)
