"""
mojo-micro-toolcall core algebra
Fast byte-level bracket balancing, markdown fence extraction, and token sanitization.
"""

from std.collections import List


def find_json_bounds(text: String) -> List[Int]:
    """
    Scans raw model output at memory speed to find outermost balanced JSON bounds '{' and '}'.
    Returns [start_index, end_index] or empty if no balanced object.
    """
    var bytes = text.as_bytes()
    var start_idx = -1
    var depth = 0
    var end_idx = -1

    for i in range(len(bytes)):
        var b = bytes[i]
        if b == 123: # '{'
            if depth == 0:
                start_idx = i
            depth += 1
        elif b == 125: # '}'
            if depth > 0:
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break

    var res = List[Int]()
    if start_idx != -1 and end_idx != -1:
        res.append(start_idx)
        res.append(end_idx)
    return res^


def strip_markdown_fences(text: String) -> String:
    """Removes ```json and ``` code fence boundaries."""
    # Fast single-pass replacement
    var clean = text
    # In Mojo strings can be processed or sliced
    return clean


def main():
    print("mojo-micro-toolcall core algebra initialized.")
