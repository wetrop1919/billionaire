"""Protocol version."""
from dataclasses import dataclass


@dataclass(slots=True)
class ProtocolVersion:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}" 