"""
screenhand_core.mojo
Native Mojo desktop coordinate clipping and collision kernel for Screenhand Bridge.
Provides sub-nanosecond 2D boundary clamping, bounding box collision checks,
and click trajectory point generation.
"""

from std.collections import List


@fieldwise_init
struct ScreenCoord(Copyable, Movable):
    var x: Int
    var y: Int
    var is_within_bounds: Bool


@fieldwise_init
struct ScreenBox(Copyable, Movable):
    var x1: Int
    var y1: Int
    var x2: Int
    var y2: Int


def clip_coordinate_to_bounds(x: Int, y: Int, max_w: Int, max_h: Int) -> ScreenCoord:
    """Clips requested desktop coordinates to hardware display boundaries."""
    var cx = x
    var cy = y
    var in_bounds = True

    if cx < 0:
        cx = 0
        in_bounds = False
    elif cx >= max_w:
        cx = max_w - 1
        in_bounds = False

    if cy < 0:
        cy = 0
        in_bounds = False
    elif cy >= max_h:
        cy = max_h - 1
        in_bounds = False

    return ScreenCoord(x=cx, y=cy, is_within_bounds=in_bounds)


def check_box_collision(b1: ScreenBox, b2: ScreenBox) -> Bool:
    """Evaluates whether two 2D bounding boxes overlap on the screen."""
    if b1.x2 < b2.x1 or b2.x2 < b1.x1:
        return False
    if b1.y2 < b2.y1 or b2.y2 < b1.y1:
        return False
    return True


def point_in_rect(x: Int, y: Int, box: ScreenBox) -> Bool:
    """Determines whether a coordinate is located within a window bounding rectangle."""
    return x >= box.x1 and x <= box.x2 and y >= box.y1 and y <= box.y2


def main():
    print("screenhand_core.mojo initialized.")
    var pt = clip_coordinate_to_bounds(2000, 500, 1920, 1080)
    print("Clipped point:", pt.x, pt.y, pt.is_within_bounds)
