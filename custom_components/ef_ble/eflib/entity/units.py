import enum


class Unit(enum.StrEnum):
    pass


class Power(Unit):
    WATT = "W"


class Temperature(Unit):
    C = "C"
    F = "F"


class Current(Unit):
    AMPERE = "A"


class Voltage(Unit):
    VOLT = "V"
