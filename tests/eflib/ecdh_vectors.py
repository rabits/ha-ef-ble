"""Synthetic SECP160r1 fixtures, not captured device or account credentials"""

# Cross-checked with python-ecdsa 0.19 and OpenSSL 3.6 EVP raw ECDH. For a
# private scalar of 1, the shared secret is the peer point's 20-byte X coordinate.
# Scalar 130 has leading zeros in both coordinates; n - 1 needs 161 bits.
PUBLIC_KEYS = {
    1: bytes.fromhex(
        "4a96b5688ef573284664698968c38bb913cbfc82"
        "23a628553168947d59dcc912042351377ac5fb32"
    ),
    2: bytes.fromhex(
        "02f997f33c5ed04c55d3edf8675d3e92e8f46686"
        "f083a323482993e9440e817e21cfb7737df8797b"
    ),
    130: bytes.fromhex(
        "007746d0467cae6e1d9e71ec04f993a7961c95d8"
        "0044580fc3f7ebf6f379ac3f568d48073505c1d5"
    ),
    0x100000000000000000001F4C8F927AED3CA752256: bytes.fromhex(
        "4a96b5688ef573284664698968c38bb913cbfc82"
        "dc59d7aace976b82a62336edfbdcaec8053a04cd"
    ),
}

# Fixed results from the original handshake with local scalar 130, peer scalar 1,
# sRand = bytes(range(16)), seed = 02 01, and the existing key table / AES framing.
PUBLIC_REQUEST = bytes.fromhex(
    "5a5a00012c000100007746d0467cae6e1d9e71ec04f993a7961c95d8"
    "0044580fc3f7ebf6f379ac3f568d48073505c1d54871"
)
INITIAL_KEY = bytes.fromhex("007746d0467cae6e1d9e71ec04f993a7")
IV = bytes.fromhex("57e383f27f30eac2c33935e213a73b76")
KEY_INFO_REPLY = bytes.fromhex(
    "5a5a000123000237ad4ef76d1d6fd8f31b283cba91715c242547452ed97b5d1dd72f6df559889909ab"
)
SESSION_KEY = bytes.fromhex("0fd4fa7e5a68909e37d5f2e1494256c0")
