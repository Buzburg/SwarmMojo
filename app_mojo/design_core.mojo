"""
design_core.mojo
Native Mojo SIMD and mathematical kernel for Impeccable Design Token calculations,
WCAG 2.1 AAA contrast ratios, relative luminance, and modular typography scales.
"""

from std.collections import List
from std.math import pow


@fieldwise_init
struct RGBColor(Copyable, Movable):
    var r: Float32  # [0.0, 1.0]
    var g: Float32  # [0.0, 1.0]
    var b: Float32  # [0.0, 1.0]


@fieldwise_init
struct ContrastEvaluation(Copyable, Movable):
    var ratio: Float32
    var passes_aa_normal: Bool   # ratio >= 4.5
    var passes_aa_large: Bool    # ratio >= 3.0
    var passes_aaa_normal: Bool  # ratio >= 7.0
    var passes_aaa_large: Bool   # ratio >= 4.5


def srgb_channel_to_linear(c: Float32) -> Float32:
    """Converts an sRGB color channel [0.0, 1.0] to linear light for luminance."""
    if c <= Float32(0.04045):
        return c / Float32(12.92)
    var base = (c + Float32(0.055)) / Float32(1.055)
    return pow(base, Float32(2.4))


def calculate_relative_luminance(color: RGBColor) -> Float32:
    """
    Calculates WCAG 2.1 relative luminance:
    L = 0.2126 * R_lin + 0.7152 * G_lin + 0.0722 * B_lin
    """
    var r_lin = srgb_channel_to_linear(color.r)
    var g_lin = srgb_channel_to_linear(color.g)
    var b_lin = srgb_channel_to_linear(color.b)

    return (Float32(0.2126) * r_lin) + (Float32(0.7152) * g_lin) + (Float32(0.0722) * b_lin)


def calculate_contrast_ratio(color_a: RGBColor, color_b: RGBColor) -> ContrastEvaluation:
    """
    Calculates contrast ratio between two colors:
    (L1 + 0.05) / (L2 + 0.05) where L1 is the lighter luminance.
    """
    var lum_a = calculate_relative_luminance(color_a)
    var lum_b = calculate_relative_luminance(color_b)

    var l1 = lum_a
    var l2 = lum_b
    if lum_b > lum_a:
        l1 = lum_b
        l2 = lum_a

    var ratio = (l1 + Float32(0.05)) / (l2 + Float32(0.05))

    return ContrastEvaluation(
        ratio=ratio,
        passes_aa_normal=ratio >= Float32(4.5),
        passes_aa_large=ratio >= Float32(3.0),
        passes_aaa_normal=ratio >= Float32(7.0),
        passes_aaa_large=ratio >= Float32(4.5),
    )


def hex_to_rgb(hex_code: UInt32) -> RGBColor:
    """Extracts RGB channels from 24-bit 0xRRGGBB integer."""
    var r_byte = (hex_code >> 16) & UInt32(0xFF)
    var g_byte = (hex_code >> 8) & UInt32(0xFF)
    var b_byte = hex_code & UInt32(0xFF)

    return RGBColor(
        r=Float32(r_byte) / Float32(255.0),
        g=Float32(g_byte) / Float32(255.0),
        b=Float32(b_byte) / Float32(255.0),
    )


def generate_modular_scale(base_px: Float32, ratio: Float32, steps_up: Int, steps_down: Int) -> List[Float32]:
    """Generates a modular typography scale (e.g. Major Third 1.25, Perfect Fourth 1.333)."""
    var total_steps = steps_down + steps_up + 1
    var scale = List[Float32](capacity=total_steps)

    # Negative steps (smaller than base)
    for i in range(steps_down, 0, -1):
        var multiplier = pow(ratio, Float32(-i))
        scale.append(base_px * multiplier)

    # Base
    scale.append(base_px)

    # Positive steps (larger than base)
    for i in range(1, steps_up + 1):
        var multiplier = pow(ratio, Float32(i))
        scale.append(base_px * multiplier)

    return scale^


def main():
    print("design_core.mojo initialized.")
    # Test high contrast: white on slate void (#0B0F19 vs #F9FAFB)
    var bg = hex_to_rgb(UInt32(0x0B0F19))
    var text = hex_to_rgb(UInt32(0xF9FAFB))
    var eval = calculate_contrast_ratio(bg, text)
    print("Contrast ratio: ", eval.ratio, " AAA normal: ", eval.passes_aaa_normal)
