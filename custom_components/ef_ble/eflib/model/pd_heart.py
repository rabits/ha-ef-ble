import struct
from typing import ClassVar

from .base import RawData


class BasePdHeart(RawData):
    STRUCT_FORMAT: ClassVar[str] = (
        "<"  # little-endian
        "B"  # model
        "4s"  # errorCode
        "4s"  # sysVer
        "4s"  # wifiVer
        "B"  # wifiAutoRecovery
        "B"  # soc
        "H"  # wattsOutSum
        "H"  # wattsInSum
        "l"  # remainTime
        "B"  # quietMode
        "B"  # dcOutState
        "B"  # usb1Watt
        "B"  # usb2Watt
        "B"  # qcUsb1Watt
        "B"  # qcUsb2Watt
        "B"  # typeC1Watts
        "B"  # typeC2Watts
        "B"  # typeC1Temp
        "B"  # typeC2Temp
        "B"  # carState
        "B"  # carWatts
        "B"  # carTemp
        "H"  # standbyMin
        "H"  # lcdOffSec
        "B"  # lcdBrightness
        "l"  # dcChgPower
        "l"  # sunChgPower
        "l"  # acChgPower
        "l"  # dcDsgPower
        "l"  # acDsgPower
        "l"  # usbUsedTime
        "l"  # usbQcUsedTime
        "l"  # typeCUsedTime
        "l"  # carUsedTime
        "l"  # invUsedTime
        "l"  # dcInUsedTime
        "l"  # mpptUsedTime
    )

    model: int
    error_code: bytes
    sys_ver: bytes
    wifi_ver: bytes
    wifi_auto_recovery: int
    soc: int
    watts_out_sum: int
    watts_in_sum: int
    remain_time: bytes
    quiet_mode: int
    dc_out_state: int
    usb1_watt: int
    usb2_watt: int
    qc_usb1_watt: int
    qc_usb2_watt: int
    typec1_watts: int
    typec2_watts: int
    typec1_temp: int
    typec2_temp: int
    car_state: int
    car_watts: int
    car_temp: int
    standby_min: int
    lcd_off_sec: int
    lcd_brightness: int
    dc_chg_power: int
    sun_chg_power: int
    ac_chg_power: int
    dc_dsg_power: int
    ac_dsg_power: int
    usb_used_time: int
    usb_qc_used_time: int
    typec_used_time: int
    car_used_time: int
    inv_used_time: int
    dc_in_used_time: int
    mppt_used_time: int

    @classmethod
    def from_bytes(cls, data: bytes) -> "BasePdHeart":
        unpacked = struct.unpack(cls.STRUCT_FORMAT, data[:89])
        return cls(*unpacked)
