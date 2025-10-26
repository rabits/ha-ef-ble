def pround(precision: int = 2):
    def _round(val):
        return round(val, precision)

    return _round
