from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.DH import key_agreement
from Crypto.Protocol.KDF import HKDF
from Crypto.PublicKey import ECC
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad


@dataclass
class EncryptionStrategy(ABC):
    """Strategy for session-level AES-CBC encryption/decryption"""

    session_key: bytes
    iv: bytes

    @abstractmethod
    async def encrypt(self, plaintext: bytes) -> bytes: ...

    @abstractmethod
    async def decrypt(self, ciphertext: bytes) -> bytes: ...


class Type7Encryption(EncryptionStrategy):
    async def encrypt(self, plaintext: bytes) -> bytes:
        cipher = AES.new(self.session_key, AES.MODE_CBC, self.iv)
        return cipher.encrypt(plaintext=pad(plaintext, AES.block_size))

    async def decrypt(self, ciphertext: bytes) -> bytes:
        cipher = AES.new(self.session_key, AES.MODE_CBC, self.iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size)


class Type1Encryption(EncryptionStrategy):
    async def encrypt(self, plaintext: bytes) -> bytes:
        padded_len = (len(plaintext) + 15) // 16 * 16
        padded = plaintext + b"\x00" * (padded_len - len(plaintext))
        cipher = AES.new(self.session_key, AES.MODE_CBC, self.iv)
        return cipher.encrypt(padded)

    async def decrypt(self, ciphertext: bytes) -> bytes:
        cipher = AES.new(self.session_key, AES.MODE_CBC, self.iv)
        return cipher.decrypt(ciphertext)


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
