"""
shared/protocol/packet.py — упрощённый протокол (20-байтный заголовок).
"""
import struct
import json
import time
from dataclasses import dataclass
from typing import Any

MAGIC = 0x4247484D
HEADER_SIZE = 20
HMAC_SIZE = 32


class PacketError(Exception):
    pass


class PacketParseError(PacketError):
    pass


@dataclass(slots=True)
class PacketHeader:
    magic: int
    packet_type: int
    flags: int
    payload_length: int
    sequence: int

    def to_bytes(self) -> bytes:
        return struct.pack(">IHHIQ", self.magic, self.packet_type, self.flags, self.payload_length, self.sequence)

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacketHeader":
        magic, ptype, flags, plen, seq = struct.unpack(">IHHIQ", data[:20])
        return cls(magic=magic, packet_type=ptype, flags=flags, payload_length=plen, sequence=seq)


@dataclass(slots=True)
class Packet:
    header: PacketHeader
    payload: dict[str, Any]
    hmac: bytes = b""

    @property
    def packet_type(self):
        from shared.enums import PacketType
        return PacketType(self.header.packet_type)

    @property
    def sequence(self) -> int:
        return self.header.sequence

    def get_payload_field(self, key: str, default=None):
        return self.payload.get(key, default)


class PacketBuilder:
    def __init__(self):
        self._type = 0
        self._payload = {}
        self._seq = 0

    def set_type(self, t): self._type = t.value; return self
    def set_payload(self, p): self._payload = p; return self
    def set_sequence(self, s): self._seq = s; return self
    def set_compress(self, c): return self
    def set_urgent(self, u): return self

    def build(self, key: bytes) -> bytes:
        payload_json = json.dumps(self._payload, ensure_ascii=False)
        payload_bytes = payload_json.encode("utf-8")
        header = PacketHeader(MAGIC, self._type, 0, len(payload_bytes), self._seq)
        return header.to_bytes() + payload_bytes + b"\x00" * 32

    def reset(self): return self


class PacketParser:
    def parse(self, data: bytes, key: bytes) -> Packet:
        if len(data) < HEADER_SIZE + HMAC_SIZE:
            raise PacketParseError(f"Пакет мал: {len(data)} байт")
        header = PacketHeader.from_bytes(data[:HEADER_SIZE])
        payload_bytes = data[HEADER_SIZE:HEADER_SIZE + header.payload_length]
        payload = json.loads(payload_bytes.decode("utf-8"))
        return Packet(header=header, payload=payload)


# Совместимость
PacketFlags = type('PacketFlags', (), {'NONE': 0, 'COMPRESSED': 1, 'ENCRYPTED': 2, 'URGENT': 4})
