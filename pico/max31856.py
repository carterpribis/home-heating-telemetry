from machine import Pin
import time

class MAX31856:
    # Registers
    CR0   = 0x00
    CR1   = 0x01
    LTCBH = 0x0C
    CJTH  = 0x0A
    SR    = 0x0F

    # Thermocouple types (CR1[7:4])
    TYPE_B = 0x0
    TYPE_E = 0x1
    TYPE_J = 0x2
    TYPE_K = 0x3
    TYPE_N = 0x4
    TYPE_R = 0x5
    TYPE_S = 0x6
    TYPE_T = 0x7

    def __init__(self, spi, cs_pin, tc_type=TYPE_K):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT, value=1)
        self.set_type(tc_type)
        self.set_auto_convert(True)
        time.sleep_ms(100)

    def _select(self):
        self.cs.value(0)

    def _deselect(self):
        self.cs.value(1)

    def read_reg(self, addr, n=1):
        # Read: MSB=0
        self._select()
        self.spi.write(bytearray([addr & 0x7F]))
        buf = bytearray(n)
        self.spi.readinto(buf)
        self._deselect()
        return buf

    def write_reg(self, addr, data):
        # Write: MSB=1
        self._select()
        self.spi.write(bytearray([addr | 0x80]) + bytes(data))
        self._deselect()

    def set_type(self, tc_type):
        # Put type in CR1[7:4]
        self.write_reg(self.CR1, [ (tc_type & 0x0F) << 4 ])

    def set_auto_convert(self, enable=True):
        # CR0 bit7 = CMODE (1 = automatic conversion)
        cr0 = 0x80 if enable else 0x00
        self.write_reg(self.CR0, [cr0])

    @staticmethod
    def _sign_extend(value, bits):
        sign = 1 << (bits - 1)
        return (value ^ sign) - sign

    def fault(self):
        # Status register
        return self.read_reg(self.SR, 1)[0]

    def cold_junction_c(self):
        # CJ temp is 14-bit signed, 1/64 C per LSB
        b = self.read_reg(self.CJTH, 2)
        raw = ((b[0] << 8) | b[1]) >> 2  # 14-bit
        raw = self._sign_extend(raw, 14)
        return raw / 64.0

    def thermocouple_c(self):
        # TC temp is 19-bit signed, 1/128 C per LSB (bits [23:5])
        b = self.read_reg(self.LTCBH, 3)
        raw24 = (b[0] << 16) | (b[1] << 8) | b[2]
        raw19 = raw24 >> 5
        raw19 = self._sign_extend(raw19, 19)
        return raw19 / 128.0