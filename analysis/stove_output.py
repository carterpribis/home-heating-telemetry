"""Estimate the stove's heat output from its surface temperature.

The stove is treated as a painted cast-iron box that gives off heat by
radiation and natural convection. Only the stovetop temperature is measured;
the sides are assumed to run at a fraction of the top's temperature rise
above the room. Heat leaving through the flue is not counted.

Treat the results as good to about plus or minus 25 percent.
"""
SIGMA = 5.67e-8          # Stefan-Boltzmann constant, W/m^2/K^4
EMISSIVITY = 0.9         # painted cast iron
W_TO_BTU_HR = 3.412

# Outside dimensions of the stove body in metres (width, depth, height)
WIDTH, DEPTH, HEIGHT = 0.742, 0.806, 0.796
A_TOP = WIDTH * DEPTH
A_SIDES = 2 * DEPTH * HEIGHT
A_FRONT_BACK = 2 * WIDTH * HEIGHT
BACK_EXPOSED = 0.75      # the back faces masonry, so count three quarters of front + back

# Natural-convection coefficients, h = C * dT^(1/3), W/m^2/K
C_TOP = 1.52             # hot horizontal surface facing up
C_VERTICAL = 1.31


def _kelvin(temp_f):
    return (temp_f - 32) / 1.8 + 273.15


def _surface_watts(temp_k, room_k, area, c_conv):
    rise = max(temp_k - room_k, 0.0)
    radiation = EMISSIVITY * SIGMA * (temp_k ** 4 - room_k ** 4)
    convection = c_conv * rise ** (4 / 3)
    return area * (radiation + convection)


def output_btu_hr(stovetop_f, room_f=65.0, side_fraction=0.70):
    """Heat given off to the room, in BTU per hour, at one stovetop temperature."""
    room = _kelvin(room_f)
    top = _kelvin(stovetop_f)
    side = room + side_fraction * (top - room)
    watts = _surface_watts(top, room, A_TOP, C_TOP)
    watts += _surface_watts(side, room, A_SIDES + A_FRONT_BACK * BACK_EXPOSED, C_VERTICAL)
    return watts * W_TO_BTU_HR


if __name__ == "__main__":
    print("stovetop F   output BTU/hr with sides at 60 / 70 / 80 percent of the top's rise")
    for temp in (200, 300, 400, 500, 600, 638):
        row = [round(output_btu_hr(temp, side_fraction=f), -2) for f in (0.6, 0.7, 0.8)]
        print(f"{temp:>10}   {row[0]:>8,.0f} {row[1]:>8,.0f} {row[2]:>8,.0f}")
