import logging

from ..devicebase import DeviceBase, BLEDevice, AdvertisementData
from ..packet import Packet
from ..pb import pd303_pb2_v4 as pd303_pb2

_LOGGER = logging.getLogger(__name__)

class Device(DeviceBase):
    '''Smart Home Panel 2'''
    SN_PREFIX = b'HD31'

    NUM_OF_CIRCUITS = 12
    NUM_OF_CHANNELS = 3

    @staticmethod
    def check(sn):
        return sn.startswith(Device.SN_PREFIX)

    def __init__(self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str) -> None:
        super().__init__(ble_dev, adv_data, sn)

        self._data_circuit_power = [None] * Device.NUM_OF_CIRCUITS
        self._data_circuit_current = [None] * Device.NUM_OF_CIRCUITS

        self._data_grid_power = None
        self._data_in_use_power = None

        self._data_channel_power = [None] * Device.NUM_OF_CHANNELS

        self._data_error_count = 0
        self._data_battery_level = None

    @property
    def battery_level(self) -> int | None:
        '''Battery level as a percentage.'''
        return self._data_battery_level

    @property
    def channel_power(self) -> list[int | None]:
        '''Backup channels wattage in W.'''
        return self._data_channel_power

    @property
    def circuit_power(self) -> list[int | None]:
        '''Circuit consuming wattage in W.'''
        return self._data_circuit_power

    @property
    def circuit_current(self) -> list[float | None]:
        '''Circuit consuming amperage in A.'''
        return self._data_circuit_current

    @property
    def grid_power(self) -> int | None:
        '''Grid intake wattage in W.'''
        return self._data_grid_power

    @property
    def in_use_power(self) -> int | None:
        '''In use wattage in W.'''
        return self._data_in_use_power

    @property
    def error_happened(self) -> bool:
        '''Will return true if error happened during the last update.'''
        return self._data_error_count > 0

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        updated = False
        if packet.src() == 0x0B and packet.cmdSet() == 0x0C:
            if packet.cmdId() == 0x01:  # master_info, load_info, backup_info, watt_info, master_ver_info
                p = pd303_pb2.ProtoTime()
                p.ParseFromString(packet.payload())
                _LOGGER.debug("%s: %s: Parsed data: %r", self.address, self.name, str(p))

                if p.HasField('load_info'):
                    for i, w in enumerate(p.load_info.hall1_watt):
                        if self._data_circuit_power[i] != w:
                            self._data_circuit_power[i] = w
                            updated = True
                    for i, a in enumerate(p.load_info.hall1_curr):
                        if self._data_circuit_current[i] != a:
                            self._data_circuit_current[i] = a
                            updated = True

                if p.HasField('watt_info'):
                    wi = p.watt_info
                    if wi.HasField('grid_watt'):
                        if self._data_grid_power != wi.grid_watt:
                            self._data_grid_power = wi.grid_watt
                            updated = True
                    elif self._data_grid_power != 0:
                        self._data_grid_power = 0
                        updated = True

                    for i, w in enumerate(wi.ch_watt):
                        if self._data_channel_power[i] != w:
                            self._data_channel_power[i] = w
                            updated = True

                    if wi.HasField('all_hall_watt'):
                        if self._data_in_use_power != wi.all_hall_watt:
                            self._data_in_use_power = wi.all_hall_watt
                            updated = True

                processed = True
            elif packet.cmdId() == 0x20:  # backup_incre_info
                p = pd303_pb2.ProtoPushAndSet()
                p.ParseFromString(packet.payload())
                _LOGGER.debug("%s: %s: Parsed data: %r", self.address, self.name, str(p))

                if not p.HasField('backup_incre_info'):
                    _LOGGER.warning("Unable to find expected field 'backup_incre_info': %r", str(p))
                    return processed

                info = p.backup_incre_info
                if info.HasField('errcode'):
                    errors = []
                    for e in info.errcode.err_code:
                        if e != b'\x00\x00\x00\x00\x00\x00\x00\x00':
                            errors.append(e)
                    if self._data_error_count != len(errors):
                        if len(errors) > self._data_error_count:
                            _LOGGER.warning("%s: %s: Error happened on device: %s", self.address, self.name, errors)
                        self._data_error_count = len(errors)
                        updated = True

                if info.HasField('backup_bat_per'):
                    if self.battery_level != info.backup_bat_per:
                        self._data_battery_level = info.backup_bat_per
                        updated = True

                processed = True

        if updated:
            for callback in self._callbacks:
                callback()

        return processed
