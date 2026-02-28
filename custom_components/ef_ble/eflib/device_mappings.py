from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .devicebase import DeviceBase

ADDON_BATTERY_MAP: dict[str, str] = {
    "Y712": "Delta Pro Ultra Battery",
    "D3E1": "DELTA 3 Max Extra Battery",
    "MR52": "DELTA Pro 3 Smart Extra Battery",
    "R361": "DELTA 2 Max Smart Extra Battery",
    "R341": "DELTA 2 Extra Battery",
    "P361": "DELTA 3 Smart Extra Battery",
    "R633": "RIVER 3 Plus Smart Extra Battery 600W",
    "R632": "RIVER 3 Plus Smart Extra Battery 300W",
    "M202": "Wave Add-On Battery",
    "D202": "Wave Add-On Battery",
    "H102": "Smart Extra Battery",
    "H105": "Smart Extra Battery",
    "E3": "DELTA Pro Smart Extra Battery",
    "E2": "DELTA Max Smart Extra Battery",
    "P3": "RIVER Pro Extra Battery",
    "P5": "RIVER Pro Extra Battery",
    "MK": "RIVER Extra Battery",
    "R9": "RIVER Plus Extra Battery",
}


def battery_name_from_sn(sn: str | None) -> str:
    if not sn:
        return "Extra Battery"

    for serial_num in [sn[:4], sn[:2]]:
        if name := ADDON_BATTERY_MAP.get(serial_num):
            return name
    return "Extra Battery"


def battery_name_from_device(device: "DeviceBase", index: int) -> str:
    return getattr(
        device,
        "extra_battery_name",
        battery_name_from_sn(getattr(device, f"battery_{index}_sn", None)),
    )


# fmt: off
ECOFLOW_DEVICE_LIST = {
    # =====================
    # DELTA SERIES
    # =====================
    "D8":  {"name": "EcoFlow DELTA (1000)", "packets": "v1"},
    "D5":  {"name": "EcoFlow DELTA (1300)", "packets": "v1"},
    "D1":  {"name": "EcoFlow DELTA (1300)", "packets": "v1"},
    "D2":  {"name": "EcoFlow DELTA (1300)", "packets": "v1"},
    "D3":  {"name": "EcoFlow DELTA (1300)", "packets": "v1"},
    "D4":  {"name": "EcoFlow DELTA (1300)", "packets": "v1"},

    "DB":  {"name": "EcoFlow DELTA mini", "packets": "v1"},

    "DA":  {"name": "EcoFlow DELTA Max (2000)", "packets": "v1"},
    "DD":  {"name": "EcoFlow DELTA Max (1600)", "packets": "v1"},

    "DCA": {"name": "EcoFlow DELTA Pro", "packets": "v1"},
    "DCF": {"name": "EcoFlow DELTA Pro", "packets": "v1"},
    "R511":{"name": "EcoFlow DELTA Pro", "packets": "v1"},
    "Z0":  {"name": "EcoFlow DELTA Pro DZ500", "packets": "v1"},

    # =====================
    # DELTA 2 FAMILY
    # =====================
    "R331":{"name": "EcoFlow DELTA 2", "packets": "v2"},
    "R335":{"name": "EcoFlow DELTA 2", "packets": "v2"},
    "R351":{"name": "EcoFlow DELTA 2 Max", "packets": "v2"},
    "R354":{"name": "EcoFlow DELTA 2 Max", "packets": "v2"},
    "P341":{"name": "EcoFlow DELTA 2 Max S", "packets": "v2"},

    # =====================
    # DELTA 3 FAMILY
    # =====================
    "P231":{"name": "EcoFlow DELTA 3", "packets": "v3"},
    "D361":{"name": "EcoFlow DELTA 3 (1500)", "packets": "v3"},
    "P351":{"name": "EcoFlow DELTA 3 Plus", "packets": "v3"},
    "D3N1":{"name": "EcoFlow DELTA 3 Classic", "packets": "v3"},
    "D3M1":{"name": "EcoFlow DELTA 3 Max", "packets": "v3"},
    "D3E1":{"name": "EcoFlow DELTA 3 Max Plus", "packets": "v3"},
    "D3U1":{"name": "EcoFlow DELTA 3 Ultra", "packets": "v3"},
    "D3UP":{"name": "EcoFlow DELTA 3 Ultra Plus", "packets": "v3"},
    "PR11":{"name": "EcoFlow DELTA 3 1000 Air", "packets": "v3"},
    "PR12":{"name": "EcoFlow DELTA 3 1000 Air (10ms UPS)", "packets": "v3"},
    "PR21":{"name": "EcoFlow DELTA 3 2000 Air", "packets": "v3"},

    "MR51":{"name": "EcoFlow DELTA Pro 3", "packets": "v3"},
    "MR53":{"name": "EcoFlow DELTA Pro 3E", "packets": "v3"},
    "Y711":{"name": "EcoFlow DELTA Pro Ultra", "packets": "v3"},

    # =====================
    # RIVER SERIES
    # =====================
    "R7":  {"name": "EcoFlow RIVER", "packets": "v1"},
    "R8":  {"name": "EcoFlow RIVER Plus", "packets": "v1"},
    "RA":  {"name": "EcoFlow RIVER Max Plus", "packets": "v1"},
    "M3":  {"name": "EcoFlow RIVER Max", "packets": "v1"},
    "P2":  {"name": "EcoFlow RIVER Pro", "packets": "v1"},
    "P4":  {"name": "EcoFlow RIVER Pro", "packets": "v1"},

    "R601":{"name": "EcoFlow RIVER 2", "packets": "v2"},
    "R603":{"name": "EcoFlow RIVER 2", "packets": "v2"},
    "R611":{"name": "EcoFlow RIVER 2 Max", "packets": "v2"},
    "R613":{"name": "EcoFlow RIVER 2 Max", "packets": "v2"},
    "R621":{"name": "EcoFlow RIVER 2 Pro", "packets": "v2"},
    "R623":{"name": "EcoFlow RIVER 2 Pro", "packets": "v2"},

    "R631":{"name": "EcoFlow RIVER 3 Plus", "packets": "v3"},
    "R634":{"name": "EcoFlow RIVER 3 Plus (270Wh)", "packets": "v3"},
    "R635":{"name": "EcoFlow RIVER 3 Plus (Wireless)", "packets": "v3"},
    "R651":{"name": "EcoFlow RIVER 3 (245Wh)", "packets": "v3"},
    "R653":{"name": "EcoFlow RIVER 3 (230Wh)", "packets": "v3"},
    "R654":{"name": "EcoFlow RIVER 3 UPS (230Wh)", "packets": "v3"},
    "R655":{"name": "EcoFlow RIVER 3 UPS (245Wh)", "packets": "v3"},

    # =====================
    # GENERATORS
    # =====================
    "DG21":{"name": "EcoFlow Smart Generator (Dual Fuel)", "packets": "v3"},
    "G351":{"name": "EcoFlow Smart Generator 4000 (Dual Fuel)", "packets": "v3"},
    "G371":{"name": "EcoFlow Smart Generator 3000 (Dual Fuel)", "packets": "v3"},

    # =====================
    # CLIMATE / APPLIANCES
    # =====================
    "M201":{"name": "EcoFlow WAVE", "packets": "?"},
    "KT21":{"name": "EcoFlow WAVE 2", "packets": "v2"},
    "AC71":{"name": "EcoFlow WAVE 3", "packets": "v3"},

    # =====================
    # GLACIER
    # =====================
    "BX11":{"name": "EcoFlow GLACIER", "packets": "v3"},
    "BX12":{"name": "EcoFlow GLACIER Plug-in Battery", "packets": "v3"},
    "RF43":{"name": "EcoFlow GLACIER Classic 35L", "packets": "v3"},
    "RF44":{"name": "EcoFlow GLACIER Classic 45L", "packets": "v3"},
    "RF45":{"name": "EcoFlow GLACIER Classic 55L", "packets": "v3"},

    # =====================
    # POWERSTREAM / STREAM
    # =====================
    "HW51":{"name": "EcoFlow PowerStream", "packets": "v3"},
    "HW52":{"name": "EcoFlow Smart Plug (PowerStream)", "packets": "v3"},

    "BK01":{"name": "EcoFlow STREAM Microinverter", "packets": "v3"},
    "BK02":{"name": "EcoFlow STREAM Microinverter", "packets": "v3"},
    "BK12":{"name": "EcoFlow STREAM Pro", "packets": "v3"},
    "BK31":{"name": "EcoFlow STREAM AC Pro", "packets": "v3"},
    "BK41":{"name": "EcoFlow STREAM Max", "packets": "v3"},
    "BK51":{"name": "EcoFlow STREAM AC", "packets": "v3"},
    "BK61":{"name": "EcoFlow STREAM Ultra X", "packets": "v3"},

    # =====================
    # SMART PANELS / GRID
    # =====================
    "SP10":{"name": "EcoFlow Smart Home Panel", "packets": "?"},
    "HD31":{"name": "EcoFlow Smart Home Panel 2", "packets": "v3"},
    "HR62":{"name": "EcoFlow Smart Home Panel 3", "packets": "v3"},
    "HR63":{"name": "EcoFlow Smart Home Panel 3", "packets": "v3"},
    "HR6C":{"name": "EcoFlow Smart Home Panel 3", "packets": "v3"},

    "HJ31":{"name": "EcoFlow PowerOcean", "packets": "?"},
    "HJ32":{"name": "EcoFlow PowerOcean Battery", "packets": "?"},
    "HJ35":{"name": "EcoFlow PowerOcean 6kW", "packets": "?"},
    "HJ36":{"name": "EcoFlow PowerOcean 8kW", "packets": "?"},
    "HJ37":{"name": "EcoFlow PowerOcean 12kW", "packets": "?"},

    # =====================
    # TRAIL
    # =====================
    "PR51":{"name": "EcoFlow TRAIL 200 DC", "packets": "?"},
    "PR61":{"name": "EcoFlow TRAIL 200 DC", "packets": "?"},
    "PR71":{"name": "EcoFlow TRAIL 300 DC", "packets": "?"},
    "PR81":{"name": "EcoFlow TRAIL Plus 300 DC", "packets": "?"},

    # =====================
    # POWERPULSE
    # =====================
    "C371":{"name": "EcoFlow PowerPulse 7KW", "packets": "?"},
    "C372":{"name": "EcoFlow PowerPulse 22KW", "packets": "?"},
    "C373":{"name": "EcoFlow PowerPulse 22KW Pro", "packets": "?"},
    "C374":{"name": "EcoFlow PowerPulse 22KW Meter", "packets": "?"},
    "C376":{"name": "EcoFlow PowerPulse 11KW Meter", "packets": "?"},
}
# fmt: on
