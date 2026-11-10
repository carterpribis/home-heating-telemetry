import time
import json
import network
from machine import SPI, Pin
import max31856
from secrets import SSID, PASSWORD, LOG_URL, TOKEN

# ---- Wi-Fi ----
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

t0 = time.time()
while not wlan.isconnected():
    if time.time() - t0 > 20:
        raise RuntimeError("Wi-Fi connect timeout")
    time.sleep(0.2)

print("Wi-Fi OK:", wlan.ifconfig())

# ---- SPI / MAX31856 ----
spi = SPI(
    0,
    baudrate=1_000_000,
    polarity=0,
    phase=1,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16),
)
tc = max31856.MAX31856(spi, cs_pin=17, tc_type=max31856.MAX31856.TYPE_K)

# ---- HTTP ----
try:
    import urequests as requests
except ImportError:
    import urequests as requests  # if you created urequests.py

headers = {"Content-Type": "application/json"}

while True:
    fault = tc.fault()
    cj = tc.cold_junction_c()
    temp = tc.thermocouple_c()

    payload = {
        "token": TOKEN,
        "fault": int(fault),
        "cj": float(cj),
        "tc": float(temp),
    }

    try:
        requests.post(LOG_URL, data=json.dumps(payload), headers=headers)
        print("sent", fault, cj, temp)
    except Exception as e:
        print("POST failed:", e)

    time.sleep(10)