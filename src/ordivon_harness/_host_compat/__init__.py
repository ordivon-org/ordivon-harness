"""Private, versioned source-level compatibility boundary to Ordivon Host.

Only modules in this package may import ``ordivon_host`` directly. Harness remains
Host-native: this boundary centralizes the exact API dependency without pretending
there is a second Host implementation or a generic remote plugin protocol.
"""

HOST_REQUIRED_SOURCE_REVISION = "428a6f2f90b4050535507c9be078c450552177e5"
PROTOCOL_REQUIRED_SOURCE_REVISION = "420dc356cb664d75db0f34f356156baebe5843db"

__all__ = [
    "HOST_REQUIRED_SOURCE_REVISION",
    "PROTOCOL_REQUIRED_SOURCE_REVISION",
]
