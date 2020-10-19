#!/usr/bin/env python

"""
Calculate true winds from vessel speed, course and relative wind

These routines will compute meteorological true winds (direction from
which wind is blowing, relative to true north; and speed relative to
the fixed earth).

8/08/2017 : Converted from Matlab to python by David Pablo Cohn
            (david.cohn@gmail.com) using SMOP 0.1; verified on
            python 2.7-3.5

9/30/2014 : If the true wind has speed and its coming from the north
            then its direction should be 360deg. The problem was fixed
            in which the programss output showed 0deg instead of 360deg.

Created: 12/17/96
Developed by: Shawn R. Smith and Mark A. Bourassa
Programmed by: Mylene Remigio

Direct questions about algorithm to:  wocemet@coaps.fsu.edu
"""

import logging

from math import pi, cos, sin, atan2, sqrt

DEFAULT_ZRL = 0.0  # clockwise angle between bow and anemometer reference line
DEFAULT_MISSING_VALUES = [-1111.0,  # missing val for course_over_ground
                          -9999.0,  # missing val for speed_over_ground
                          1111.0,  # missing val for wind_dir
                          9999.0,  # missing val for wind_speed
                          5555.0,  # missing val for heading
                          ]


################################################################################
def truew(crse=None,
          cspd=None,
          hd=None,
          wdir=None,
          wspd=None,
          zlr=DEFAULT_ZRL,
          wmis=DEFAULT_MISSING_VALUES,
          ):
    """
    FUNCTION truew() - calculates true winds from vessel speed, course and
    relative wind

    INPUTS

    crse      real    Course TOWARD WHICH the vessel is moving over
                          the ground. Referenced to true north and the
                          fixed earth.
    cspd      real    Speed of vessel over the ground. Referenced
                          to the fixed earth.
    hd        real    Heading toward which bow of vessel is pointing.
                          Referenced to true north.
    zlr       real    Zero line reference -- angle between bow and
                          zero line on anemometer.  Direction is clockwise
                          from the bow.  (Use bow=0 degrees as default
                          when reference not known.)
    wdir      real    Wind direction measured by anemometer,
                          referenced to the ship.
    wspd      real    Wind speed measured by anemometer,referenced to
                          the vessel's frame of reference.
    wmis      real    Five element array containing missing values for
                          crse, cspd, wdir, wspd, and hd. In the output,
                          the missing value for tdir is identical to the
                          missing value specified in wmis for wdir.
                          Similarly, tspd uses the missing value assigned
                          to wmis for wspd.

    *** WDIR MUST BE METEOROLOGICAL (DIRECTION FROM)! CRSE AND CSPD MUST
        BE RELATIVE TO A FIXED EARTH! ***

    OUTPUT VALUES:

    tdir      real    True wind direction - referenced to true north
                          and the fixed earth with a direction from which
                          the wind is blowing (meteorological).
    tspd      real    True wind speed - referenced to the fixed earth.
    adir      real    Apparent wind direction (direction measured by
                          wind vane, relative to true north). IS
                          REFERENCED TO TRUE NORTH & IS DIRECTION FROM
                          WHICH THE WIND IS BLOWING. Apparent wind
                          direction is the sum of the ship relative wind
                          direction (measured by wind vane relative to the
                          bow), the ship's heading, and the zero-line
                          reference angle.  NOTE:  The apparent wind speed
                          has a magnitude equal to the wind speed measured
                          by the anemometer.

    """
    # INITIALIZE VARIABLES
    adir = 0
    dtor = pi / 180

    # Check course, ship speed, heading, wind direction, and
    # wind speed for valid values (i.e. neither missing nor
    # outside physically acceptable ranges).
    err_mesg = []
    if crse is None or crse < 0 or crse > 360 or crse == wmis[0]:
        err_mesg.append('Bad or missing course: %g' % crse)
    if cspd is None or cspd < 0 or cspd == wmis[1]:
        err_mesg.append('Bad or missing cspd: %g' % cspd)
    if wdir is None or wdir < 0 or wdir > 360 or wdir == wmis[2]:
        err_mesg.append('Bad or missing wind dir: %g' % wdir)
    if wspd is None or wspd < 0 or wspd == wmis[3]:
        err_mesg.append('Bad or missing wind speed: %g' % wspd)
    if hd is None or hd < 0 or hd > 360 or hd == wmis[4]:
        err_mesg.append('Bad or missing heading: %g' % hd)
    if zlr < 0.0 or zlr > 360.0:
        err_mesg.append('Bad or missing zero line reference: %g' % zlr)
        zlr = 0.0

    if err_mesg:
        logging.warning('TrueWinds: %s', '; '.join(err_mesg))
        return (None, None, None)

    # Convert from navigational coordinates to
    # angles commonly used in mathematics
    mcrse = 90 - crse
    # Keep the value between 0 and 360 degrees
    if (mcrse <= 0.0):
        mcrse = mcrse + 360.0
    # Calculate apparent wind direction
    adir = hd + wdir + zlr
    # Keep adir between 0 and 360 degrees
    while adir >= 360.0:
        adir = adir - 360.0

    # Convert from meteorological coordinates to angles
    # commonly used in mathematics
    mwdir = 270.0 - adir
    # Keep mdir between 0 and 360 degrees
    if (mwdir <= 0.0):
        mwdir = mwdir + 360.0
    if (mwdir > 360.0):
        mwdir = mwdir - 360.0
    # Determine the east-west vector component and the
    # north-south vector component of the true wind
    x = wspd * cos(mwdir * dtor) + cspd * cos(mcrse * dtor)
    y = wspd * sin(mwdir * dtor) + cspd * sin(mcrse * dtor)
    # Use the two vector components to calculate the true wind
    # speed
    tspd = sqrt(x * x + y * y)
    calm_flag = 1
    # Determine the angle for the true wind
    if (abs(x) > 1e-05):
        mtdir = (atan2(y, x)) / dtor
    else:
        if (abs(y) > 1e-05):
            mtdir = 180.0 - (90.0 * y) / abs(y)
        else:
            # The true wind speed is essentially zero: winds
            # are calm and direction is not well defined
            mtdir = 270.0
            calm_flag = 0
    # Convert from the common mathematical angle coordinate to
    # the meteorological wind direction
    tdir = 270.0 - mtdir
    # Make sure that the true wind angle is between
    # 0 and 360 degrees
    while tdir < 0.0:
        tdir = (tdir + 360.0) * calm_flag

    while tdir > 360.0:
        tdir = (tdir - 360.0) * calm_flag

    # Ensure wmo convention for tdir = 360 for win
    # from north and tspd > 0
    if (calm_flag == 1 and (tdir < 0.0001)):
        tdir = 360.0

    return (tdir, tspd, adir)


################################################################################
if __name__ == '__main__':
    pass
