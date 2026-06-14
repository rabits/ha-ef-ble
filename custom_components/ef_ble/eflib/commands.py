import logging
import struct
import time
from dataclasses import dataclass, field

from .devicebase import DeviceBase
from .packet import Packet
from .pb import utc_sys_pb2

_LOGGER = logging.getLogger(__name__)

# Some devices re-request the time in a tight loop when they don't accept the response,
# which would have us flood the link with time-sync packets. The device only needs the
# time set occasionally, so collapse repeated requests within this window into a single
# send.
_MIN_RESEND_INTERVAL = 30.0


@dataclass
class TimeCommands:
    device: DeviceBase
    _last_sent: float | None = field(default=None, init=False)

    async def sendUtcTime(self):
        """Send UTC time as unix timestamp seconds through PB"""
        _LOGGER.debug("%s: sendUtcTime", self.device.address)

        utcs = utc_sys_pb2.SysUTCSync()
        utcs.sys_utc_time = int(time.time())
        payload = utcs.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x01, 0x55, payload, 0x01, 0x01, 0x13)

        await self.device._conn.sendPacket(packet)

    async def sendRTCRespond(self):
        """Send RTC timestamp seconds and TZ as respond to device's request"""
        _LOGGER.debug("%s: sendRTCRespond", self.device.address)

        # Building payload
        tz_offset = (
            (time.timezone if (time.localtime().tm_isdst == 0) else time.altzone)
            / 60
            / 60
            * -1
        )
        tz_maj = int(tz_offset)
        tz_min = int((tz_offset - tz_maj) * 100)
        time_sec = int(time.time())
        payload = (
            struct.pack("<L", time_sec)
            + struct.pack("<b", tz_maj)
            + struct.pack("<b", tz_min)
        )

        # Forming packet
        packet = Packet(
            0x21,
            0x35,
            0x01,
            Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME,
            payload,
            0x01,
            0x01,
            0x03,
        )

        await self.device._conn.sendPacket(packet)

    async def sendRTCCheck(self):
        """Send command to check RTC of the device"""
        _LOGGER.debug("%s: sendRTCCheck", self.device.address)

        # Building payload
        tz_offset = (
            (time.timezone if (time.localtime().tm_isdst == 0) else time.altzone)
            / 60
            / 60
            * -1
        )
        tz_maj = int(tz_offset)
        tz_min = int((tz_offset - tz_maj) * 100)
        time_sec = int(time.time())
        payload = (
            struct.pack("<L", time_sec)
            + struct.pack("<b", tz_maj)
            + struct.pack("<b", tz_min)
        )

        # Forming packet
        packet = Packet(
            0x21,
            0x35,
            0x01,
            Packet.NET_BLE_COMMAND_CMD_CHECK_RET_TIME,
            payload,
            0x01,
            0x01,
            0x03,
        )

        await self.device._conn.sendPacket(packet)

    def async_send_all(self):
        now = time.monotonic()
        if self._last_sent is not None and now - self._last_sent < _MIN_RESEND_INTERVAL:
            _LOGGER.debug(
                "%s: throttling repeated time-sync request (last sent %.1fs ago)",
                self.device.address,
                now - self._last_sent,
            )
            return
        self._last_sent = now
        self.device._conn._add_task(self.sendUtcTime())
        self.device._conn._add_task(self.sendRTCRespond())
        self.device._conn._add_task(self.sendRTCCheck())
