"""Run the whole analysis on a sheet export and print the results.

    python3 run.py path/to/export.xlsx
"""
import sys

import numpy as np
import pandas as pd

from load import load, season
from stove_output import output_btu_hr

# Two days when the furnace ran nonstop in mild weather and the house stayed
# cold. That looks like a furnace problem, so they are left out of the fits.
EXCLUDED_DAYS = ["2026-02-16", "2026-02-17"]
STOVE_START = "2026-01-04"
FIT_END = "2026-04-30"


def daily_table(df):
    df = df.copy()
    df["day"] = df["timestamp"].dt.date
    df["gap_F"] = df["ambient_F"] - df["outdoor_F"]
    ok = df[df["stove_ok"]].copy()
    ok["output"] = ok["stove_F"].apply(lambda t: output_btu_hr(t) if t > 70 else 0.0)
    day = df.groupby("day").agg(
        rows=("heating", "size"), furnace=("heating", "mean"),
        gap_F=("gap_F", "mean"), outdoor_F=("outdoor_F", "mean"), indoor_F=("ambient_F", "mean"),
    )
    day["stove_rows"] = ok.groupby("day").size()
    day["stove_mean_F"] = ok.groupby("day")["stove_F"].mean()
    day["stove_output"] = ok.groupby("day")["output"].mean()
    return day


def data_quality(df):
    print("== Data ==")
    print(f"rows: {len(df):,}   from {df.timestamp.min():%Y-%m-%d} to {df.timestamp.max():%Y-%m-%d}")
    has = df["stove_F"].notna()
    print(f"rows with a stove reading: {has.sum():,}   usable after checks: {df.stove_ok.sum():,}")
    print(f"  dropped for sensor fault: {(has & (df.stove_fault != 0)).sum():,}")
    print(f"  dropped as stale (Pico offline): {(has & (df.stove_age_s.abs() > 60)).sum():,}")
    print(f"highest usable stovetop reading: {df.loc[df.stove_ok, 'stove_F'].max():.0f} F")
    over = df[df.stove_ok & (df.stove_F >= 600)]
    print(f"readings at or above 600 F: {len(over)} (about {len(over) * 5 / 60:.1f} hours)")
    # stretches of more than a day when the Pico was not reporting
    s = df[(df.timestamp >= STOVE_START) & (df.timestamp < "2026-04-12")]
    bad, ts = (~s.stove_ok).values, s.timestamp.values
    spans, i = [], 0
    while i < len(bad):
        if bad[i]:
            j = i
            while j + 1 < len(bad) and bad[j + 1]:
                j += 1
            if (ts[j] - ts[i]) / np.timedelta64(1, "h") > 24:
                spans.append(f"{pd.Timestamp(ts[i]):%b %d} to {pd.Timestamp(ts[j]):%b %d}")
            i = j + 1
        else:
            i += 1
    print("stove sensor out for more than a day:", "; ".join(spans) or "none")
    weeks = df.groupby(df.timestamp.dt.strftime("%G-%V")).size()
    short = weeks[(weeks == 999)]
    if len(short):
        print(f"weekly tabs that stop at 999 rows (second half of the week missing): {len(short)}, first is week {short.index[0]}")


def output_summary(df):
    print("\n== Stove heat output ==")
    for temp in (200, 320, 500, 600, 638):
        lo, mid, hi = (output_btu_hr(temp, side_fraction=f) for f in (0.6, 0.7, 0.8))
        print(f"stovetop {temp:>3} F: {mid:>7,.0f} BTU/hr  (range {lo:,.0f} to {hi:,.0f})")
    ok = df[df.stove_ok]
    burning = ok[ok.stove_F >= 150]
    q = burning.stove_F.apply(output_btu_hr)
    print(f"while burning (stovetop 150 F or more): median stovetop {burning.stove_F.median():.0f} F, "
          f"mean output {q.mean():,.0f}, median output {q.median():,.0f} BTU/hr")
    jan_feb = ok[(ok.timestamp >= STOVE_START) & (ok.timestamp < "2026-03-01")]
    q24 = jan_feb.stove_F.apply(lambda t: output_btu_hr(t) if t > 70 else 0.0)
    print(f"24-hour average, January and February, burn-downs included: {q24.mean():,.0f} BTU/hr")
    return q24.mean()


def daily_fit(df):
    print("\n== How much of the load the stove carried ==")
    day = daily_table(df)
    d = day[(day.index >= pd.Timestamp(STOVE_START).date()) & (day.index <= pd.Timestamp(FIT_END).date())
            & (day.rows >= 280) & (day.stove_rows >= 250)].copy()
    d = d[~d.index.isin([pd.Timestamp(x).date() for x in EXCLUDED_DAYS])]
    u = d[d.furnace < 0.95]                      # leave out days the furnace ran flat out
    print(f"days used: {len(u)}")

    def fit(x2):
        X = np.c_[u.gap_F, x2, np.ones(len(u))]
        coef, *_ = np.linalg.lstsq(X, u.furnace, rcond=None)
        pred = X @ coef
        r2 = 1 - ((u.furnace - pred) ** 2).sum() / ((u.furnace - u.furnace.mean()) ** 2).sum()
        return coef, r2

    # 1. Against stovetop temperature: how many degrees of gap does the stove cover?
    coef, r2 = fit((u.stove_mean_F - 65).clip(lower=0))
    print(f"furnace share of the day = {coef[0]:.4f} x gap - {-coef[1]:.5f} x (stovetop - 65) {coef[2]:+.3f}   R^2 = {r2:.2f}")
    print(f"a day with the stovetop averaging 300 F covers about {-coef[1] * (300 - 65) / coef[0]:.0f} F of the indoor-outdoor gap")

    # 2. Against the stove's estimated output: each BTU/hr from the stove cancels some gap,
    #    so the ratio of the two coefficients is the house's heat loss per degree.
    coef, r2 = fit(u.stove_output)
    ua = -coef[0] / coef[1]
    print(f"furnace share of the day = {coef[0]:.4f} x gap - {-coef[1]:.3e} x stove output {coef[2]:+.3f}   R^2 = {r2:.2f}")
    print(f"the house loses about {ua:,.0f} BTU/hr for each degree F of indoor-outdoor gap")
    for gap in (60, 75, 90):
        print(f"  at a {gap} F gap: about {ua * gap:,.0f} BTU/hr")
    band = pd.cut(d.outdoor_F, [-20, 5, 15, 25, 35, 50])
    print(d.groupby(band, observed=True).agg(days=("furnace", "size"), furnace=("furnace", "mean"),
                                             stove_mean_F=("stove_mean_F", "mean"), indoor_F=("indoor_F", "mean")).round(2).to_string())


def nights(df):
    print("\n== Overnight (10 pm to 7 am) ==")
    df = df[df.timestamp >= STOVE_START].copy()
    # a night belongs to the date it starts on
    shifted = df.timestamp - pd.Timedelta(hours=7)
    df["night"] = shifted.dt.date
    hour = df.timestamp.dt.hour
    n = df[(hour >= 22) | (hour < 7)]
    rows = []
    for night, g in n.groupby("night"):
        if len(g) < 100 or g.stove_ok.sum() < 90:        # need the whole night, with the stove sensor working
            continue
        if str(night) in ("2026-02-15", "2026-02-16", "2026-02-17"):
            continue
        evening = df[(df.night == night) & (df.timestamp.dt.hour >= 17) & df.stove_ok]
        whole = df[(df.night == night) & df.stove_ok & ((df.timestamp.dt.hour >= 17) | (df.timestamp.dt.hour < 7))]
        fade300 = fade200 = np.nan
        if len(evening):
            peak_time = evening.loc[evening.stove_F.idxmax(), "timestamp"]
            after = whole[whole.timestamp > peak_time]
            below300 = after[after.stove_F < 300]
            below200 = after[after.stove_F < 200]
            if evening.stove_F.max() >= 300 and len(below300):
                fade300 = (below300.timestamp.iloc[0] - peak_time).total_seconds() / 3600
            if evening.stove_F.max() >= 300 and len(below200):
                fade200 = (below200.timestamp.iloc[0] - peak_time).total_seconds() / 3600
        rows.append(dict(night=night, outdoor_F=g.outdoor_F.mean(), furnace=g.heating.mean(),
                         indoor_10pm=g.ambient_F.iloc[0], indoor_7am=g.ambient_F.iloc[-1],
                         indoor_low=g.ambient_F.min(), fade300=fade300, fade200=fade200))
    t = pd.DataFrame(rows)
    print(f"nights with full data: {len(t)}")
    print(f"stovetop below 300 F a median {t.fade300.median():.1f} hours after the evening peak; "
          f"below 200 F after {t.fade200.median():.1f} hours")
    band = pd.cut(t.outdoor_F, [-40, 0, 10, 20, 30, 80], labels=["below 0 F", "0 to 10 F", "10 to 20 F", "20 to 30 F", "30 F and up"])
    out = t.groupby(band, observed=True).agg(nights=("furnace", "size"), furnace_share=("furnace", "mean"),
                                             indoor_10pm=("indoor_10pm", "mean"), indoor_7am=("indoor_7am", "mean"),
                                             lowest_indoor=("indoor_low", "min"))
    out["furnace_share"] = (out.furnace_share * 100).round(0)
    print(out.round(1).to_string())


if __name__ == "__main__":
    data = season(load(sys.argv[1]))
    data_quality(data)
    output_summary(data)
    daily_fit(data)
    nights(data)
