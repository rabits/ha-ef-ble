"""SECP160r1 key agreement through OpenSSL 3's public EVP API"""

import asyncio
import ctypes
import functools
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

# Distributions such as NixOS can replace this with an absolute library path.
_LIBCRYPTO = "libcrypto.so.3"
_PROPERTIES = b"provider=default"
_BYTE_PTR = ctypes.POINTER(ctypes.c_ubyte)
_SIZE_PTR = ctypes.POINTER(ctypes.c_size_t)
_KEY_PTR = ctypes.POINTER(ctypes.c_void_p)

# RFC 5480 SubjectPublicKeyInfo: id-ecPublicKey, secp160r1, then an uncompressed
# SEC1 point. The device sends only X[20] || Y[20], without the 04 prefix.
_SPKI_PREFIX = bytes.fromhex("303e301006072a8648ce3d020106052b81040008032a0004")

# Declare pointer argument and return types explicitly. ctypes defaults to a
# C int return value, which truncates pointers on 64-bit hosts. Do not bind
# variadic functions or macros.
_SIGNATURES = {
    "OpenSSL_version_num": (ctypes.c_ulong, []),
    "EVP_PKEY_CTX_new_from_name": (
        ctypes.c_void_p,
        [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p],
    ),
    "EVP_PKEY_keygen_init": (ctypes.c_int, [ctypes.c_void_p]),
    "EVP_PKEY_CTX_set_group_name": (
        ctypes.c_int,
        [ctypes.c_void_p, ctypes.c_char_p],
    ),
    "EVP_PKEY_generate": (ctypes.c_int, [ctypes.c_void_p, _KEY_PTR]),
    "EVP_PKEY_free": (None, [ctypes.c_void_p]),
    "EVP_PKEY_CTX_free": (None, [ctypes.c_void_p]),
    "EVP_PKEY_get_octet_string_param": (
        ctypes.c_int,
        [ctypes.c_void_p, ctypes.c_char_p, _BYTE_PTR, ctypes.c_size_t, _SIZE_PTR],
    ),
    "d2i_PUBKEY_ex": (
        ctypes.c_void_p,
        [
            _KEY_PTR,
            ctypes.POINTER(_BYTE_PTR),
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_char_p,
        ],
    ),
    "EVP_PKEY_get0_provider": (ctypes.c_void_p, [ctypes.c_void_p]),
    "EVP_PKEY_CTX_new_from_pkey": (
        ctypes.c_void_p,
        [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p],
    ),
    "EVP_PKEY_public_check": (ctypes.c_int, [ctypes.c_void_p]),
    "EVP_PKEY_derive_init": (ctypes.c_int, [ctypes.c_void_p]),
    "EVP_PKEY_CTX_set_ecdh_kdf_type": (
        ctypes.c_int,
        [ctypes.c_void_p, ctypes.c_int],
    ),
    "EVP_PKEY_derive_set_peer": (
        ctypes.c_int,
        [ctypes.c_void_p, ctypes.c_void_p],
    ),
    "EVP_PKEY_derive": (ctypes.c_int, [ctypes.c_void_p, _BYTE_PTR, _SIZE_PTR]),
    "ERR_clear_error": (None, []),
    "ERR_get_error": (ctypes.c_ulong, []),
    "ERR_error_string_n": (None, [ctypes.c_ulong, ctypes.c_char_p, ctypes.c_size_t]),
    "OPENSSL_cleanse": (None, [ctypes.c_void_p, ctypes.c_size_t]),
}


class ECDHError(RuntimeError):
    """The native backend could not perform the device's key agreement"""


@functools.cache
def _load_libcrypto() -> ctypes.CDLL:
    # Loading the library, configuration, or providers can read files. This runs
    # in a worker to keep that I/O off the event loop.
    try:
        lib = ctypes.CDLL(_LIBCRYPTO)
        for name, (restype, argtypes) in _SIGNATURES.items():
            function = getattr(lib, name)
            function.restype = restype
            function.argtypes = argtypes
    except (OSError, AttributeError) as error:
        raise ECDHError(
            "EcoFlow key agreement requires the OpenSSL 3 libcrypto shared library "
            "with SECP160r1 support"
        ) from error
    if lib.OpenSSL_version_num() >> 28 != 3:
        raise ECDHError("EcoFlow key agreement requires OpenSSL 3")
    return lib


def _error(lib: ctypes.CDLL, operation: str) -> ECDHError:
    # The error queue is thread-local: drain it here, before cleanup or returning
    # to asyncio. Error descriptions contain no key buffers or device data.
    errors = []
    while code := lib.ERR_get_error():
        buffer = ctypes.create_string_buffer(256)
        lib.ERR_error_string_n(code, buffer, len(buffer))
        errors.append(buffer.value.decode("ascii", errors="replace"))
    detail = "; ".join(errors) or "no OpenSSL error details"
    return ECDHError(f"OpenSSL could not {operation}: {detail}")


def _check(lib: ctypes.CDLL, result: int, operation: str) -> None:
    if result != 1:
        raise _error(lib, operation)


@contextmanager
def _context(
    lib: ctypes.CDLL, key: ctypes.c_void_p | int | None = None
) -> Iterator[int]:
    context = (
        lib.EVP_PKEY_CTX_new_from_name(None, b"EC", _PROPERTIES)
        if key is None
        else lib.EVP_PKEY_CTX_new_from_pkey(None, key, _PROPERTIES)
    )
    if not context:
        raise _error(lib, "create an EC context")
    try:
        yield context
    finally:
        lib.EVP_PKEY_CTX_free(context)


class _KeyExchange:
    def __init__(self) -> None:
        self.public_key = b""
        self._lib: ctypes.CDLL | None = None
        self._key = ctypes.c_void_p()
        self._lock = threading.Lock()
        self._closed = threading.Event()

    @contextmanager
    def _operation(self) -> Iterator[None]:
        try:
            with self._lock:
                if self._closed.is_set():
                    raise ECDHError("ECDH exchange is closed")
                yield
        finally:
            # Canceling to_thread leaves the worker running. Check _closed after
            # releasing the lock: close() can fail to acquire it just before release.
            if self._closed.is_set():
                self.close()

    def _free(self) -> None:
        if self._key:
            assert self._lib is not None
            self._lib.EVP_PKEY_free(self._key)
            self._key = ctypes.c_void_p()

    def close(self) -> None:
        self._closed.set()
        if self._lock.acquire(blocking=False):
            try:
                self._free()
            finally:
                self._lock.release()

    def generate(self) -> None:
        with self._operation():
            self._lib = lib = _load_libcrypto()
            lib.ERR_clear_error()
            with _context(lib) as context:
                _check(lib, lib.EVP_PKEY_keygen_init(context), "initialize EC keygen")
                _check(
                    lib,
                    lib.EVP_PKEY_CTX_set_group_name(context, b"secp160r1"),
                    "select SECP160r1",
                )
                _check(
                    lib,
                    lib.EVP_PKEY_generate(context, ctypes.byref(self._key)),
                    "generate an ephemeral EC key",
                )
            if not self._key:
                raise ECDHError("OpenSSL returned no EC key")
            point = (ctypes.c_ubyte * 41)()
            size = ctypes.c_size_t()
            _check(
                lib,
                lib.EVP_PKEY_get_octet_string_param(
                    self._key, b"encoded-pub-key", point, len(point), ctypes.byref(size)
                ),
                "export the EC public key",
            )
            if size.value != len(point) or point[0] != 4:
                raise ECDHError("OpenSSL returned an unexpected EC public key encoding")
            self.public_key = bytes(point)[1:]

    async def exchange(self, peer_public_key: bytes) -> bytes:
        return await asyncio.to_thread(self._derive, peer_public_key)

    def _derive(self, peer_public_key: bytes) -> bytes:
        with self._operation():
            if len(peer_public_key) != 40:
                raise ValueError("SECP160r1 peer public keys must contain 40 bytes")
            lib = self._lib
            assert lib is not None
            lib.ERR_clear_error()
            encoded = _SPKI_PREFIX + peer_public_key
            buffer = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
            cursor = ctypes.cast(buffer, _BYTE_PTR)
            peer = lib.d2i_PUBKEY_ex(
                None, ctypes.byref(cursor), len(buffer), None, _PROPERTIES
            )
            if not peer:
                raise _error(lib, "decode the SECP160r1 peer public key")
            try:
                consumed = ctypes.cast(cursor, ctypes.c_void_p).value
                end = ctypes.addressof(buffer) + len(buffer)
                if consumed != end or not lib.EVP_PKEY_get0_provider(peer):
                    raise ECDHError("OpenSSL did not import a provider-backed EC key")
                with _context(lib, peer) as context:
                    _check(
                        lib, lib.EVP_PKEY_public_check(context), "validate the EC peer"
                    )
                with _context(lib, self._key) as context:
                    _check(lib, lib.EVP_PKEY_derive_init(context), "initialize ECDH")
                    # EVP_PKEY_ECDH_KDF_NONE is 1. The caller hashes and truncates
                    # the raw 20-byte X coordinate after key agreement.
                    _check(
                        lib,
                        lib.EVP_PKEY_CTX_set_ecdh_kdf_type(context, 1),
                        "select raw ECDH",
                    )
                    _check(
                        lib, lib.EVP_PKEY_derive_set_peer(context, peer), "set EC peer"
                    )
                    size = ctypes.c_size_t()
                    _check(
                        lib,
                        lib.EVP_PKEY_derive(context, None, ctypes.byref(size)),
                        "size the ECDH secret",
                    )
                    if size.value != 20:
                        raise ECDHError(
                            "OpenSSL returned an unexpected ECDH secret size"
                        )
                    secret = (ctypes.c_ubyte * 20)()
                    try:
                        _check(
                            lib,
                            lib.EVP_PKEY_derive(context, secret, ctypes.byref(size)),
                            "derive the ECDH secret",
                        )
                        if size.value != len(secret):
                            raise ECDHError("OpenSSL returned a truncated ECDH secret")
                        return bytes(secret)
                    finally:
                        # This clears only the native scratch buffer, not the
                        # returned Python bytes or the caller's symmetric key.
                        lib.OPENSSL_cleanse(secret, len(secret))
            finally:
                lib.EVP_PKEY_free(peer)


@asynccontextmanager
async def key_exchange() -> AsyncIterator[_KeyExchange]:
    """Own one ephemeral key, including during cancellation of native work"""
    key = _KeyExchange()
    try:
        await asyncio.to_thread(key.generate)
        yield key
    finally:
        key.close()
