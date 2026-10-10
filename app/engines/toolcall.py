"""
mojo-micro-toolcall — Python Bridge & CLI
Zero-shot tool-call parser, JSON repair, and schema coercion for local 7B-32B models.
"""

import os
import sys
import re
import json
import time
import argparse

def extract_outer_json(text: str) -> str:
    # 1. Strip markdown code fences if present
    fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if fence_match:
        text = fence_match.group(1)

    # 2. Find outermost balanced { and }
    start = text.find('{')
    if start == -1:
        return ""
    
    depth = 0
    end = -1
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

    if start != -1 and end != -1:
        return text[start:end+1]
    return ""

def repair_json_string(s: str) -> str:
    # Replace single quotes with double quotes around keys/values
    # Note: simple heuristic for unquoted or single quoted strings
    s = re.sub(r"'([^']*)'", r'"\1"', s)
    # Remove trailing commas
    s = re.sub(r',\s*([}\]])', r'\1', s)
    # Fix python literals
    s = re.sub(r'\bTrue\b', 'true', s)
    s = re.sub(r'\bFalse\b', 'false', s)
    s = re.sub(r'\bNone\b', 'null', s)
    return s

def coerce_argument_types(args: dict, schema: dict) -> dict:
    coerced = {}
    properties = schema.get("properties", {})
    
    for k, v in args.items():
        expected_type = properties.get(k, {}).get("type")
        if expected_type == "integer" and isinstance(v, str):
            try:
                coerced[k] = int(v)
                continue
            except ValueError:
                pass
        elif expected_type == "number" and isinstance(v, str):
            try:
                coerced[k] = float(v)
                continue
            except ValueError:
                pass
        elif expected_type == "boolean" and isinstance(v, str):
            if v.lower() in ("true", "1", "yes"):
                coerced[k] = True
                continue
            elif v.lower() in ("false", "0", "no"):
                coerced[k] = False
                continue
        coerced[k] = v

    # Fill default values for missing fields
    for prop_name, prop_meta in properties.items():
        if prop_name not in coerced and "default" in prop_meta:
            coerced[prop_name] = prop_meta["default"]

    return coerced

def parse_and_coerce_tool_call(raw_text: str, schemas: dict = None) -> dict:
    start = time.perf_counter()
    extracted = extract_outer_json(raw_text)
    if not extracted:
        return {"success": False, "error": "No JSON object found in text"}

    repaired = repair_json_string(extracted)
    try:
        parsed = json.loads(repaired)
    except Exception as e:
        return {"success": False, "error": f"JSON parse error: {e}", "raw": extracted}

    # Normalize tool structure
    tool_name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
    raw_args = parsed.get("arguments") or parsed.get("parameters") or parsed.get("args") or {}

    if not tool_name:
        # Fallback: if root has properties directly, check if keys match known tools
        return {"success": False, "error": "Missing tool name in parsed JSON"}

    # Apply type coercion if schema is provided
    if schemas and tool_name in schemas:
        raw_args = coerce_argument_types(raw_args, schemas[tool_name])

    duration_us = (time.perf_counter() - start) * 1_000_000

    return {
        "success": True,
        "name": tool_name,
        "arguments": raw_args,
        "standard_tool_call": {
            "id": f"call_{int(time.time()*1000)}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(raw_args)
            }
        },
        "latency_us": round(duration_us, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="mojo-micro-toolcall Parser & Coercer")
    parser.add_argument("text", nargs="?", help="Raw model output to parse")
    args = parser.parse_args()

    if not args.text and not sys.stdin.isatty():
        content = sys.stdin.read()
    elif args.text:
        content = args.text
    else:
        print("Usage: python toolcall.py 'Sure, here is the tool: ```json ... ```'")
        sys.exit(0)

    res = parse_and_coerce_tool_call(content)
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
