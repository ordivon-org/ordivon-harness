"""Private, versioned source-level compatibility boundary to Ordivon Host.

Only modules in this package may import ``ordivon_host`` directly. Harness remains
Host-native: this boundary centralizes the exact API dependency without pretending
there is a second Host implementation or a generic remote plugin protocol.
"""

HOST_REQUIRED_SOURCE_REVISION = "1a4027bb26d77a2e051ca933bf664578f071a5a9"
PROTOCOL_REQUIRED_SOURCE_REVISION = "420dc356cb664d75db0f34f356156baebe5843db"

__all__ = [
    "HOST_REQUIRED_SOURCE_REVISION",
    "PROTOCOL_REQUIRED_SOURCE_REVISION",
]
