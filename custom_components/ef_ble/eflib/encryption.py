from typing import cast

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.DH import key_agreement
from Crypto.Protocol.KDF import HKDF
from Crypto.PublicKey import ECC
from Crypto.Random import get_random_bytes

_PUBKEY = ECC.import_key(
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VuAyEAjyDKgWi1v2IO417ZsQC3VIa5U6bs8TzQQGxzlvCKWkM=\n"
    "-----END PUBLIC KEY-----"
)


def _counter_nonce(base: bytes, counter: int) -> bytes:
    n = bytearray(base)
    cb = counter.to_bytes(12)
    return bytes(a ^ b for a, b in zip(n, cb, strict=True))


class Session:
    def __init__(self) -> None:
        eph_priv = ECC.generate(curve="curve25519")
        eph_der = eph_priv.public_key().export_key(format="DER")

        shared = key_agreement(
            static_priv=eph_priv, static_pub=_PUBKEY, kdf=lambda z: z
        )
        self._aes_key = cast(
            "bytes",
            HKDF(shared, 32, b"", SHA256, context=b"ecies-curve25519-aes256gcm"),
        )
        self._base_nonce = get_random_bytes(12)
        self._counter = 0

        self.header = len(eph_der).to_bytes(2) + eph_der + self._base_nonce

    def encrypt(self, plaintext: bytes) -> bytes:
        counter = self._counter
        self._counter += 1
        nonce = _counter_nonce(self._base_nonce, counter)
        cipher = AES.new(self._aes_key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return counter.to_bytes(2) + ciphertext + tag
