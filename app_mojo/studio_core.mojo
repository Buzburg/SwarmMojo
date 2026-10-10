"""
studio_core.mojo
Native Mojo SIMD and geometric kernel for cinematic camera rigs,
aspect-ratio safe-zone boundaries (SMPTE/EBU), 3D view frustums,
and color temperature (Kelvin to sRGB) conversion.
"""

from std.collections import List
from std.math import cos, sin, log

comptime PI: Float32 = 3.14159265359
comptime DEG_TO_RAD: Float32 = 0.01745329251


@fieldwise_init
struct SafeZoneRect(Copyable, Movable):
    var x: Int
    var y: Int
    var width: Int
    var height: Int


@fieldwise_init
struct FrameSafeZones(Copyable, Movable):
    var frame_width: Int
    var frame_height: Int
    var action_safe: SafeZoneRect  # 90%
    var title_safe: SafeZoneRect   # 80%


@fieldwise_init
struct Vector3(Copyable, Movable):
    var x: Float32
    var y: Float32
    var z: Float32


@fieldwise_init
struct CameraLookAt(Copyable, Movable):
    var position: Vector3
    var forward: Vector3
    var up: Vector3


def compute_safe_zones(width: Int, height: Int) -> FrameSafeZones:
    """Computes SMPTE standard 90% action safe and 80% title safe rectangles."""
    var action_w = Int(Float32(width) * 0.90)
    var action_h = Int(Float32(height) * 0.90)
    var action_x = (width - action_w) // 2
    var action_y = (height - action_h) // 2

    var title_w = Int(Float32(width) * 0.80)
    var title_h = Int(Float32(height) * 0.80)
    var title_x = (width - title_w) // 2
    var title_y = (height - title_h) // 2

    return FrameSafeZones(
        frame_width=width,
        frame_height=height,
        action_safe=SafeZoneRect(action_x, action_y, action_w, action_h),
        title_safe=SafeZoneRect(title_x, title_y, title_w, title_h),
    )


def compute_camera_forward(pitch_deg: Float32, yaw_deg: Float32) -> Vector3:
    """
    Computes unit forward vector from Euler pitch and yaw angles in degrees.
    """
    var pitch_rad = pitch_deg * DEG_TO_RAD
    var yaw_rad = yaw_deg * DEG_TO_RAD

    var cos_pitch = cos(pitch_rad)
    var x = cos_pitch * sin(yaw_rad)
    var y = sin(pitch_rad)
    var z = cos_pitch * cos(yaw_rad)

    return Vector3(x, y, z)


def kelvin_to_rgb(temperature_k: Float32) -> Vector3:
    """
    Converts color temperature in Kelvin [1000K - 40000K] to RGB [0.0 - 1.0].
    Based on Tanner Helland's photographic approximation algorithm.
    """
    var temp = temperature_k / Float32(100.0)
    var r = Float32(0.0)
    var g = Float32(0.0)
    var b = Float32(0.0)

    # Red
    if temp <= Float32(66.0):
        r = Float32(255.0)
    else:
        var red_calc = temp - Float32(60.0)
        r = Float32(329.698727446) * (red_calc ** Float32(-0.1332047592))
        if r < Float32(0.0):
            r = Float32(0.0)
        elif r > Float32(255.0):
            r = Float32(255.0)

    # Green
    if temp <= Float32(66.0):
        var green_calc = temp
        g = Float32(99.4708025861) * log(green_calc) - Float32(161.1195681661)
        if g < Float32(0.0):
            g = Float32(0.0)
        elif g > Float32(255.0):
            g = Float32(255.0)
    else:
        var green_calc = temp - Float32(60.0)
        g = Float32(288.1221695283) * (green_calc ** Float32(-0.0755148492))
        if g < Float32(0.0):
            g = Float32(0.0)
        elif g > Float32(255.0):
            g = Float32(255.0)

    # Blue
    if temp >= Float32(66.0):
        b = Float32(255.0)
    elif temp <= Float32(19.0):
        b = Float32(0.0)
    else:
        var blue_calc = temp - Float32(10.0)
        b = Float32(138.5177312231) * log(blue_calc) - Float32(305.0447927307)
        if b < Float32(0.0):
            b = Float32(0.0)
        elif b > Float32(255.0):
            b = Float32(255.0)

    return Vector3(
        x=r / Float32(255.0),
        y=g / Float32(255.0),
        z=b / Float32(255.0),
    )


def main():
    print("studio_core.mojo initialized.")
    var zones = compute_safe_zones(1920, 1080)
    print("1080p Action safe: ", zones.action_safe.width, "x", zones.action_safe.height)
    var golden_hour_rgb = kelvin_to_rgb(Float32(3200.0))
    print("3200K Golden hour RGB: ", golden_hour_rgb.x, ", ", golden_hour_rgb.y, ", ", golden_hour_rgb.z)
