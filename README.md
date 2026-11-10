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
| `analysis/load.py` | Reads the sheet's Excel export, joins the weekly tabs and marks which stove readings can be trusted |
| `analysis/stove_output.py` | Estimates the stove's heat output from its surface temperature |
| `analysis/run.py` | Runs the whole analysis and prints the results |

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

## The analysis

```
pip install pandas numpy openpyxl
cd analysis
python3 run.py path/to/sheet-export.xlsx
```

The input is the sheet downloaded as an Excel file. The data itself is not in this repository.

**Cleaning.** A stove reading is used only if the sensor reported no fault, the reading reached the sheet less than a minute before the row was logged, and the value is plausible. Anything older than a minute means the Pico was offline and the sheet was repeating its last value.

**Stove output.** The stove is treated as a painted cast-iron box that gives off heat by radiation and natural convection. Only the stovetop is measured, so the sides are assumed to run at 60 to 80 percent of the top's temperature rise above the room. Heat leaving through the flue is not counted. The figures are good to about plus or minus 25 percent.

**House heat loss.** For each full day, the share of the day the furnace ran is fitted against the indoor-outdoor temperature gap and the stove's average output. Each BTU per hour from the stove cancels some of the gap, so the ratio of the two coefficients is the house's heat loss per degree.

**Overnight.** For each night from 10 pm to 7 am: how much of the night the furnace ran, the indoor temperature at each end, and how long after the evening peak the stovetop fell below 300 and 200 degrees.

### Results for one winter

| Measure | Result |
|---|---|
| Rows logged, December 20 to May 14 | 31,758 |
| Rows with a stove reading | 27,609 |
| Usable after the checks | 22,347 (5,230 stale, 20 sensor faults) |
| Highest stovetop reading | 638 F |
| Time at or above 600 F | about 2.4 hours all season |
| Typical burn | median stovetop 319 F, about 15,600 to 17,600 BTU/hr |
| 24-hour average output, January and February | about 14,400 BTU/hr |
| Days used in the fit | 54, R² 0.79 |
| A day averaging 300 F on the stovetop | covers about 21 F of the indoor-outdoor gap |
| House heat loss | about 820 BTU/hr per degree F |
| At a 60 to 90 F gap | about 49,000 to 74,000 BTU/hr |
| Stovetop below 300 F | a median 1.9 hours after the evening peak |
| Stovetop below 200 F | a median 5.5 hours after the evening peak |

| Overnight outdoor temperature | Nights | Furnace running | Indoor at 10 pm | Indoor at 7 am | Lowest indoor |
|---|---|---|---|---|---|
| Below 0 F | 10 | 92% | 61.7 | 56.8 | 54 |
| 0 to 10 F | 10 | 81% | 62.0 | 58.9 | 55 |
| 10 to 20 F | 9 | 51% | 64.0 | 61.1 | 59 |
| 20 to 30 F | 14 | 16% | 66.3 | 61.9 | 60 |
| 30 F and up | 22 | 9% | 67.9 | 64.0 | 60 |

### Gaps in the data

- The stove sensor was out for more than a day four times: January 15 to 17, January 29 to 30, February 19 to 22, and April 1 to 6.
- From the second week of March, each weekly tab stops at 999 rows, so the second half of every week is missing. A new Google Sheets tab has 1,000 rows, and the logger looks for the next empty row without adding more. That is the likely cause, though I haven't confirmed it.
- February 16 and 17 are left out. The furnace ran nonstop in mild weather and the house stayed cold, which looks like a furnace problem.
- The thermostat measures one spot in the house.

## What isn't here

- `pico/` is the first working version of the logger. A later version also drove a small display beside the stove. That code is not in this repository.
- The logged data.

## Who wrote what

AI models wrote the code: ChatGPT wrote the logger and the Apps Script, and Claude wrote the analysis. I built and wired the hardware, ran the diagnostics, ran it from January to May, and debugged it with them.
