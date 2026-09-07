"""Native EVP compatibility, input validation, and ownership tests"""

import asyncio
import ctypes
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib import ecdh

from .ecdh_vectors import PUBLIC_KEYS


@pytest.mark.parametrize("scalar", PUBLIC_KEYS)
async def test_fixed_private_key(
    fixed_ecdh_key: Callable[[int], None], scalar: int
) -> None:
    fixed_ecdh_key(scalar)
    async with ecdh.key_exchange() as key:
        assert key.public_key == PUBLIC_KEYS[scalar]
        assert await key.exchange(PUBLIC_KEYS[1]) == PUBLIC_KEYS[scalar][:20]
    assert not key._key


@pytest.mark.parametrize("scalar", PUBLIC_KEYS)
async def test_fixed_peer_key(
    fixed_ecdh_key: Callable[[int], None], scalar: int
) -> None:
    fixed_ecdh_key(1)
    async with ecdh.key_exchange() as key:
        assert await key.exchange(PUBLIC_KEYS[scalar]) == PUBLIC_KEYS[scalar][:20]


async def test_fresh_keys_agree() -> None:
    async with ecdh.key_exchange() as alice, ecdh.key_exchange() as bob:
        assert alice.public_key != bob.public_key
        assert len(alice.public_key) == len(bob.public_key) == 40
        a_secret, b_secret = await asyncio.gather(
            alice.exchange(bob.public_key), bob.exchange(alice.public_key)
        )
        assert a_secret == b_secret
        assert len(a_secret) == 20
    assert not alice._key and not bob._key


@pytest.mark.parametrize("size", [0, 1, 20, 39, 41, 52, 56, 64, 65])
async def test_rejects_wrong_peer_width(size: int) -> None:
    async with ecdh.key_exchange() as key:
        with pytest.raises(ValueError, match="40 bytes"):
            await key.exchange(bytes(size))


@pytest.mark.parametrize(
    "point",
    [
        bytes(40),  # Not a point (the SEC1 infinity encoding is not a wire point).
        b"\xff" * 40,
        bytes.fromhex("ffffffffffffffffffffffffffffffff7fffffff") + PUBLIC_KEYS[1][20:],
        PUBLIC_KEYS[1][:20] + bytes.fromhex("ffffffffffffffffffffffffffffffff7fffffff"),
        PUBLIC_KEYS[1][:-1] + bytes([PUBLIC_KEYS[1][-1] ^ 1]),
    ],
)
async def test_rejects_invalid_peer(point: bytes) -> None:
    async with ecdh.key_exchange() as key:
        with pytest.raises(ecdh.ECDHError, match="peer"):
            await key.exchange(point)
    assert not key._key


def test_native_signatures(libcrypto: ctypes.CDLL) -> None:
    for name, (restype, argtypes) in ecdh._SIGNATURES.items():
        function = getattr(libcrypto, name)
        assert function.restype is restype
        assert function.argtypes == argtypes


def test_missing_library(mocker: MockerFixture) -> None:
    load = mocker.patch.object(
        ecdh.ctypes, "CDLL", side_effect=OSError("not installed")
    )
    with pytest.raises(ecdh.ECDHError, match="OpenSSL 3 libcrypto"):
        ecdh._load_libcrypto.__wrapped__()
    load.assert_called_once_with(ecdh._LIBCRYPTO)


def test_missing_symbol(mocker: MockerFixture) -> None:
    lib = mocker.Mock(spec=[n for n in ecdh._SIGNATURES if n != "EVP_PKEY_generate"])
    mocker.patch.object(ecdh.ctypes, "CDLL", return_value=lib)
    with pytest.raises(ecdh.ECDHError, match="OpenSSL 3 libcrypto"):
        ecdh._load_libcrypto.__wrapped__()


@pytest.mark.parametrize("version", [0x10101000, 0x40000000])
def test_wrong_openssl_version(mocker: MockerFixture, version: int) -> None:
    lib = mocker.Mock()
    lib.OpenSSL_version_num.return_value = version
    mocker.patch.object(ecdh.ctypes, "CDLL", return_value=lib)
    with pytest.raises(ecdh.ECDHError, match="requires OpenSSL 3"):
        ecdh._load_libcrypto.__wrapped__()


@pytest.mark.parametrize(
    ("symbol", "call_number", "result", "keys_freed", "contexts_freed"),
    [
        ("EVP_PKEY_CTX_new_from_name", 1, None, 0, 0),
        ("EVP_PKEY_keygen_init", 1, 0, 0, 1),
        ("EVP_PKEY_CTX_set_group_name", 1, -2, 0, 1),
        ("EVP_PKEY_generate", 1, 0, 0, 1),
        ("EVP_PKEY_get_octet_string_param", 1, 0, 1, 1),
        ("d2i_PUBKEY_ex", 1, None, 1, 1),
        ("EVP_PKEY_get0_provider", 1, None, 2, 1),
        ("EVP_PKEY_CTX_new_from_pkey", 1, None, 2, 1),
        ("EVP_PKEY_CTX_new_from_pkey", 2, None, 2, 2),
        ("EVP_PKEY_public_check", 1, 0, 2, 2),
        ("EVP_PKEY_derive_init", 1, 0, 2, 3),
        ("EVP_PKEY_CTX_set_ecdh_kdf_type", 1, 0, 2, 3),
        ("EVP_PKEY_derive_set_peer", 1, 0, 2, 3),
        ("EVP_PKEY_derive", 1, 0, 2, 3),
        ("EVP_PKEY_derive", 2, 0, 2, 3),
    ],
)
async def test_native_failure_cleanup(
    mocker: MockerFixture,
    libcrypto: ctypes.CDLL,
    symbol: str,
    call_number: int,
    result: int | None,
    keys_freed: int,
    contexts_freed: int,
) -> None:
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")
    free_context = mocker.spy(libcrypto, "EVP_PKEY_CTX_free")
    original = getattr(libcrypto, symbol)
    calls = 0

    def fail(*args: object) -> int | None:
        nonlocal calls
        calls += 1
        if calls == call_number:
            return result
        return original(*args)

    mocker.patch.object(libcrypto, symbol, side_effect=fail)
    with pytest.raises(ecdh.ECDHError, match="OpenSSL"):
        async with ecdh.key_exchange() as key:
            await key.exchange(PUBLIC_KEYS[1])
    assert free_key.call_count == keys_freed
    assert free_context.call_count == contexts_freed


async def test_keygen_failure_with_owned_output(
    mocker: MockerFixture, libcrypto: ctypes.CDLL
) -> None:
    original = libcrypto.EVP_PKEY_generate
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")

    def fail(*args: object) -> int:
        assert original(*args) == 1
        return 0

    mocker.patch.object(libcrypto, "EVP_PKEY_generate", side_effect=fail)
    with pytest.raises(ecdh.ECDHError, match="generate"):
        async with ecdh.key_exchange():
            pytest.fail("Key generation should fail")
    free_key.assert_called_once()


@pytest.mark.parametrize(("size", "prefix"), [(40, 4), (42, 4), (41, 2)])
async def test_invalid_public_export(
    mocker: MockerFixture, libcrypto: ctypes.CDLL, size: int, prefix: int
) -> None:
    original = libcrypto.EVP_PKEY_get_octet_string_param
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")

    def export(*args: object) -> int:
        assert original(*args) == 1
        ctypes.cast(args[4], ctypes.POINTER(ctypes.c_size_t))[0] = size
        args[2][0] = prefix
        return 1

    mocker.patch.object(
        libcrypto, "EVP_PKEY_get_octet_string_param", side_effect=export
    )
    with pytest.raises(ecdh.ECDHError, match="public key encoding"):
        async with ecdh.key_exchange():
            pytest.fail("The malformed public key should not be sent")
    free_key.assert_called_once()


@pytest.mark.parametrize(
    ("call_number", "size"), [(1, 0), (1, 19), (1, 21), (2, 19), (2, 21)]
)
async def test_invalid_secret_size(
    mocker: MockerFixture, libcrypto: ctypes.CDLL, call_number: int, size: int
) -> None:
    original = libcrypto.EVP_PKEY_derive
    calls = 0
    cleanse = mocker.spy(libcrypto, "OPENSSL_cleanse")

    def derive(*args: object) -> int:
        nonlocal calls
        calls += 1
        assert original(*args) == 1
        if calls == call_number:
            ctypes.cast(args[2], ctypes.POINTER(ctypes.c_size_t))[0] = size
        return 1

    mocker.patch.object(libcrypto, "EVP_PKEY_derive", side_effect=derive)
    with pytest.raises(ecdh.ECDHError, match="ECDH secret"):
        async with ecdh.key_exchange() as key:
            await key.exchange(PUBLIC_KEYS[1])
    assert not key._key
    if call_number == 2:
        cleanse.assert_called_once()
        assert bytes(cleanse.call_args.args[0]) == bytes(20)


async def test_close_is_idempotent(
    mocker: MockerFixture, libcrypto: ctypes.CDLL
) -> None:
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")
    async with ecdh.key_exchange() as key:
        key.close()
        key.close()
        with pytest.raises(ecdh.ECDHError, match="closed"):
            await key.exchange(PUBLIC_KEYS[1])
    free_key.assert_called_once()


async def test_null_keygen_output(
    mocker: MockerFixture, libcrypto: ctypes.CDLL
) -> None:
    mocker.patch.object(libcrypto, "EVP_PKEY_generate", return_value=1)
    with pytest.raises(ecdh.ECDHError, match="no EC key"):
        async with ecdh.key_exchange():
            pytest.fail("A null private key cannot be used")


async def test_partial_der_decode(
    mocker: MockerFixture, libcrypto: ctypes.CDLL
) -> None:
    original = libcrypto.d2i_PUBKEY_ex
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")

    def decode(*args: object) -> int:
        key = original(*args)
        assert key
        cursor = ctypes.cast(args[1], ctypes.POINTER(ecdh._BYTE_PTR))
        end = ctypes.cast(cursor[0], ctypes.c_void_p).value
        cursor[0] = ctypes.cast(end - 1, ecdh._BYTE_PTR)
        return key

    mocker.patch.object(libcrypto, "d2i_PUBKEY_ex", side_effect=decode)
    with pytest.raises(ecdh.ECDHError, match="import"):
        async with ecdh.key_exchange() as key:
            await key.exchange(PUBLIC_KEYS[1])
    assert free_key.call_count == 2


async def test_errors_are_drained_on_native_thread(
    mocker: MockerFixture, libcrypto: ctypes.CDLL
) -> None:
    original = libcrypto.ERR_get_error
    calls = []

    def get_error() -> int:
        code = original()
        calls.append((threading.get_ident(), code))
        return code

    mocker.patch.object(libcrypto, "ERR_get_error", side_effect=get_error)
    async with ecdh.key_exchange() as key:
        with pytest.raises(ecdh.ECDHError, match="peer"):
            await key.exchange(bytes(40))
    assert len(calls) > 1
    assert calls[-1][1] == 0
    assert all(thread != threading.get_ident() for thread, _ in calls)


@pytest.mark.parametrize("phase", ["load", "generate", "derive", "unlock"])
async def test_cancellation_during_native_work(
    mocker: MockerFixture, libcrypto: ctypes.CDLL, phase: str
) -> None:
    loop = asyncio.get_running_loop()
    paused = asyncio.Event()
    finished = asyncio.Event()
    resume = threading.Event()
    owner = ecdh._KeyExchange()
    mocker.patch.object(ecdh, "_KeyExchange", return_value=owner)
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")

    def pause() -> None:
        assert threading.get_ident() != loop_thread
        loop.call_soon_threadsafe(paused.set)
        assert resume.wait(5), "Test did not release the native worker"

    loop_thread = threading.get_ident()
    if phase == "unlock":
        # Pause just before releasing the operation lock, then cancel the task.
        # Any _closed check inside the lock runs before this cancellation. Cleanup
        # must still release the key.
        lock = owner._lock
        pausing_lock = mocker.MagicMock()
        pausing_lock.__enter__.side_effect = lock.acquire

        def unlock(*_args: object) -> None:
            try:
                pause()
            finally:
                lock.release()

        pausing_lock.__exit__.side_effect = unlock
        pausing_lock.acquire.side_effect = lock.acquire
        pausing_lock.release.side_effect = lock.release
        owner._lock = pausing_lock
    else:
        target, name = (
            (ecdh, "_load_libcrypto")
            if phase == "load"
            else (
                libcrypto,
                "EVP_PKEY_generate" if phase == "generate" else "EVP_PKEY_derive",
            )
        )
        original = getattr(target, name)

        def delayed(*args: object) -> object:
            result = original(*args)
            if phase != "derive" or args[1] is not None:
                pause()
            return result

        mocker.patch.object(target, name, side_effect=delayed)

    method = "_derive" if phase == "derive" else "generate"
    original_work = getattr(owner, method)

    def work(*args: object) -> object:
        try:
            return original_work(*args)
        finally:
            loop.call_soon_threadsafe(finished.set)

    mocker.patch.object(owner, method, side_effect=work)

    async def handshake() -> None:
        async with ecdh.key_exchange() as key:
            if phase == "derive":
                await key.exchange(PUBLIC_KEYS[1])
            await asyncio.Event().wait()

    task = asyncio.create_task(handshake())
    try:
        async with asyncio.timeout(5):
            await paused.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            # Cancellation must neither block the loop nor free a key in use.
            free_key.assert_not_called()
    finally:
        resume.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async with asyncio.timeout(5):
            await finished.wait()
    assert not owner._key
    assert free_key.call_count == (2 if phase == "derive" else 1)


def test_native_stress_in_subprocess() -> None:
    code = """
import asyncio
import runpy
runpy.run_path("tests/eflib/conftest.py", run_name="tests.eflib.conftest")
from custom_components.ef_ble.eflib.ecdh import ECDHError, key_exchange

async def main():
    for _ in range(100):
        async with key_exchange() as a, key_exchange() as b:
            assert await a.exchange(b.public_key) == await b.exchange(a.public_key)
            try:
                await a.exchange(bytes(40))
            except ECDHError:
                pass
            else:
                raise AssertionError("Invalid point accepted")
        assert not a._key and not b._key

asyncio.run(main())
"""
    _run_native_subprocess(code)


def test_inherited_fips_policy_is_not_overridden() -> None:
    code = """
import asyncio
import ctypes
import runpy
runpy.run_path("tests/eflib/conftest.py", run_name="tests.eflib.conftest")
from custom_components.ef_ble.eflib import ecdh

lib = ecdh._load_libcrypto()
set_properties = lib.EVP_set_default_properties
set_properties.restype = ctypes.c_int
set_properties.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
assert set_properties(None, b"fips=yes") == 1

async def main():
    try:
        async with ecdh.key_exchange():
            raise AssertionError("SECP160r1 must not bypass the FIPS property")
    except ecdh.ECDHError:
        pass

asyncio.run(main())
"""
    _run_native_subprocess(code)


def _run_native_subprocess(code: str) -> None:
    subprocess.run(
        [sys.executable, "-B", "-X", "faulthandler", "-c", code],
        cwd=Path(__file__).parents[2],
        check=True,
        timeout=60,
        capture_output=True,
    )
