from __future__ import annotations

from pathlib import Path
from typing import Any


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    out: list[str] = []
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    normalized = value.replace("_", "")
    try:
        if normalized.lower().startswith("0x"):
            return int(normalized, 16)
        if "." in normalized:
            return float(normalized)
        return int(normalized)
    except ValueError:
        return value


def _parse_key_value(text: str) -> tuple[str, Any | None, bool]:
    if ":" not in text:
        raise ValueError(f"invalid yaml line: {text}")
    key, raw_value = text.split(":", 1)
    key = key.strip()
    raw_value = raw_value.strip()
    if raw_value == "":
        return key, None, True
    return key, _parse_scalar(raw_value), False


def _load_subset_yaml(text: str) -> Any:
    tokens: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        cleaned = _strip_comment(raw_line)
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        tokens.append((indent, cleaned.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens):
            return {}, index
        _, first = tokens[index]
        if first.startswith("- "):
            return parse_list(index, indent)
        return parse_map(index, indent)

    def parse_map(index: int, indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(tokens):
            current_indent, text = tokens[index]
            if current_indent < indent or text.startswith("- "):
                break
            if current_indent > indent:
                raise ValueError(f"unexpected indentation at line: {text}")
            key, value, needs_child = _parse_key_value(text)
            index += 1
            if needs_child:
                if index >= len(tokens) or tokens[index][0] <= current_indent:
                    result[key] = {}
                else:
                    child, index = parse_block(index, tokens[index][0])
                    result[key] = child
            else:
                result[key] = value
        return result, index

    def parse_list(index: int, indent: int) -> tuple[list[Any], int]:
        result: list[Any] = []
        while index < len(tokens):
            current_indent, text = tokens[index]
            if current_indent < indent or not text.startswith("- "):
                break
            if current_indent != indent:
                raise ValueError(f"unexpected list indentation at line: {text}")
            item_text = text[2:].strip()
            index += 1
            if not item_text:
                child, index = parse_block(index, indent + 2)
                result.append(child)
                continue
            if ":" in item_text:
                key, value, needs_child = _parse_key_value(item_text)
                item: dict[str, Any] = {}
                if needs_child:
                    if index < len(tokens) and tokens[index][0] > indent:
                        child, index = parse_block(index, tokens[index][0])
                        item[key] = child
                    else:
                        item[key] = {}
                else:
                    item[key] = value
                while index < len(tokens):
                    next_indent, next_text = tokens[index]
                    if next_indent <= indent:
                        break
                    if next_indent != indent + 2 or next_text.startswith("- "):
                        break
                    sub_key, sub_value, sub_child = _parse_key_value(next_text)
                    index += 1
                    if sub_child:
                        child, index = parse_block(index, indent + 4)
                        item[sub_key] = child
                    else:
                        item[sub_key] = sub_value
                result.append(item)
            else:
                result.append(_parse_scalar(item_text))
        return result, index

    parsed, _ = parse_block(0, tokens[0][0] if tokens else 0)
    return parsed


def load_yaml(path: str | Path) -> Any:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except Exception:
        return _load_subset_yaml(text)


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        if value == "" or any(ch in value for ch in [":", "#", "[", "]"]):
            return f'"{value}"'
        return value
    return str(value)


def _dump_yaml(value: Any, indent: int = 0) -> list[str]:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_dump_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_dump_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_dump_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}- {_dump_scalar(item)}")
        return lines
    return [f"{pad}{_dump_scalar(value)}"]


def dump_yaml(value: Any) -> str:
    try:
        import yaml  # type: ignore

        return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
    except Exception:
        return "\n".join(_dump_yaml(value)) + "\n"
