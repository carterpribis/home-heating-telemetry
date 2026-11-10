# Home heating telemetry

A logger that records a house's thermostat, the outdoor temperature and the surface temperature of a wood stove to a Google Sheet, every five minutes.

I used the data to work out how much heat the house loses and what size of wood stove it needs. The full write-up is at [prib.is/stove.html](https://prib.is/stove.html).

## How it works

```
thermocouple on the stove
        |
   MAX31856 converter
        |
 Raspberry Pi Pico 2 W  --(HTTPS POST every 10 s)-->  Apps Script web app
                                                            |
                                              keeps the latest stove reading
                                                            |
Nest thermostat (Google SDM API) ----+                      |
National Weather Service station ----+--> 5-minute trigger --+--> one row in a weekly tab
```

- **The Pico** reads a Type K thermocouple through a MAX31856 converter and posts the reading, the cold-junction temperature and the sensor's fault code to a web app.
- **The web app** (`doPost` in `Code.gs`) checks a shared token and stores the latest reading.
- **A five-minute trigger** (`logNestRow`) reads the thermostat, finds the nearest National Weather Service station and reads its latest observation, picks up the latest stove reading, and appends one row to a tab named for the ISO week.
- **A side panel in the sheet** (`StoveWatch.html`) shows the live stove temperature, how fast it is rising or falling (a least-squares slope over the last five samples), an arrow for the direction, and a button to mark when wood was loaded. While it is open it also logs a reading every ten seconds to a `stove_watch` tab.

Each logged row has: `timestamp, date, hvac_status, mode, ambient_F, setpoint_F, humidity_%, outdoor_F, delta_in_out_F, heating_helper, stove_C, stove_F, stove_fault, stove_age_s`.

`stove_fault` and `stove_age_s` are logged with every reading, so faulty or stale stove values can be found and set aside when the data is analyzed.

## What's here

| Path | What it is |
|---|---|
| `pico/main.py` | The logger: connects to Wi-Fi, reads the sensor, posts every ten seconds |
| `pico/max31856.py` | A small MicroPython driver for the MAX31856 (register reads, fault, cold junction, thermocouple temperature) |
| `pico/urequests.py` | A minimal HTTPS POST for MicroPython |
| `pico/secrets_example.py` | Template for the Wi-Fi details, web app URL and token |
| `apps_script/Code.gs` | The web app, the Nest and weather logging, the weekly tabs, and the functions behind the side panel |
| `apps_script/StoveWatch.html` | The side panel |
| `apps_script/Debug.gs` | A helper that prints the latest stored stove reading |

## Hardware

- Raspberry Pi Pico 2 W running MicroPython
- Adafruit-style MAX31856 thermocouple converter
- Type K thermocouple on the stovetop

Wiring (SPI0): SCK to GP18, MOSI to GP19, MISO to GP16, CS to GP17.

## Setting it up

1. Create a Google Sheet and open **Extensions → Apps Script**. Add `Code.gs`, `Debug.gs` and `StoveWatch.html`.
2. Fill in the `CFG` block at the top of `Code.gs`: the sheet ID, your Google Device Access project ID and OAuth client for the Nest API, your latitude and longitude, and a long random token.
3. Authorize the Nest API once (`exchangeAuthCodeOnce`), then run `listNestDevices` and `setDeviceName`.
4. Deploy the script as a web app and copy its URL.
5. On the Pico, copy `secrets_example.py` to `secrets.py` and fill it in with the Wi-Fi details, the web app URL and the same token. Copy the four `pico/` files to the board.
6. In the sheet, use the **Stove Watch** menu to create the sheets and the five-minute trigger.

No keys, tokens, IDs or coordinates are stored in this repository. `secrets.py` is in `.gitignore`.

## What isn't here

- `pico/` is the first working version of the logger. A later version also drove a small display beside the stove. That code is not in this repository.
- The heat-loss analysis described in the write-up is not included.

## Who wrote what

AI models wrote the code: ChatGPT wrote the logger and the Apps Script. I built and wired the hardware, ran the diagnostics, ran it from January to May, and debugged it with them.
