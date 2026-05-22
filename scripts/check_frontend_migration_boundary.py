#!/usr/bin/env python3
"""Check static frontend migration boundary coverage.

This checker is intentionally read-only and does not start Vite, Storybook, or
the backend. It treats route/surface/i18n/theme contract drift as a hard
failure, while raw page business strings remain an audit inventory unless
--strict-business-strings is used.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


FRONTEND_ROOT = Path("main/frontend-modern")

FILES = {
    "catalog": Path("src/app/platform/i18n/catalog.ts"),
    "frontend_kernel_app": Path("src/app/kernel/FrontendKernelApp.tsx"),
    "module_manifest": Path("src/app/kernel/moduleManifest.ts"),
    "kernel_types": Path("src/app/kernel/types.ts"),
    "page_placement": Path("src/app/topology/pagePlacementMatrix.ts"),
    "baseline_inventory": Path("src/app/topology/baselineInventory.ts"),
    "render_kernel_module_content": Path("src/app/kernel/renderKernelModuleContent.tsx"),
    "settings_page": Path("src/pages/SettingsPage.tsx"),
    "theme_tokens": Path("src/app/platform/theme/tokens.ts"),
    "theme_types": Path("src/app/platform/theme/types.ts"),
}

KERNEL_BUSINESS_STRING_FILES = [
    Path("src/app/kernel/AdminLayerShell.tsx"),
    Path("src/app/kernel/FrontendKernelApp.tsx"),
    Path("src/app/kernel/LayerSwitch.tsx"),
    Path("src/app/kernel/moduleChrome.ts"),
    Path("src/app/kernel/ModuleRenderer.tsx"),
    Path("src/app/kernel/renderKernelModuleContent.tsx"),
    Path("src/app/kernel/VisualizationLayerShell.tsx"),
    Path("src/app/kernel/WorkbenchLayerShell.tsx"),
]

EXPECTED_SURFACE_BY_LAYER = {
    "A": "workbench",
    "B": "visualization",
    "C": "management",
}

EXPECTED_ROUTE_PREFIX_BY_LAYER = {
    "A": "/workbench/",
    "B": "/visual/",
    "C": "/admin/",
}

EXPECTED_THEME_LEAVES = {
    "background": ["app", "subtle"],
    "surface": ["base", "raised"],
    "border": ["default", "strong"],
    "text": ["primary", "secondary"],
    "accent": ["primary", "contrast"],
    "status": ["success", "warning", "danger"],
    "interactive": ["hover", "focus", "active"],
}

ALLOWED_PRODUCT_ACRONYMS = {
    "API",
    "CODEX",
    "DB",
    "ES",
    "LLM",
    "MRW",
    "NEWS",
    "SEARCH",
}

TECHNICAL_PROPS = {
    "activeLayer",
    "className",
    "entryRoute",
    "key",
    "legacyHash",
    "navGroupKey",
    "projectKey",
    "routePath",
    "shellMode",
    "surfaceKind",
    "type",
    "value",
    "variant",
}

VISIBLE_PROPS = {"aria-label", "label", "placeholder", "title"}


@dataclass(frozen=True)
class ModuleEntry:
    module_key: str
    layer_id: str
    surface_kind: str
    entry_route: str
    legacy_hash: str
    nav_group_key: str

    @property
    def title_key(self) -> str:
        return f"shell.title.{self.module_key}"

    @property
    def nav_label_key(self) -> str:
        return f"navigation.item.{self.module_key}"


@dataclass(frozen=True)
class TextOccurrence:
    kind: str
    value: str
    start: int
    end: int
    line: int
    line_text: str


def read_text(root: Path, rel_path: Path) -> str:
    return (root / FRONTEND_ROOT / rel_path).read_text(encoding="utf-8")


def build_line_starts(source: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            starts.append(index + 1)
    return starts


def line_number_at(line_starts: list[int], index: int) -> int:
    low = 0
    high = len(line_starts) - 1
    while low <= high:
        mid = (low + high) // 2
        if line_starts[mid] <= index:
            low = mid + 1
        else:
            high = mid - 1
    return high + 1


def line_at(source: str, line_starts: list[int], index: int) -> str:
    start = line_starts[line_number_at(line_starts, index) - 1]
    end = source.find("\n", index)
    if end == -1:
        end = len(source)
    return source[start:end]


def balanced_block(source: str, start: int) -> str:
    opener = source[start]
    closer = {"{": "}", "[": "]", "(": ")"}[opener]
    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ValueError("unclosed block")


def initializer_block(source: str, variable_name: str, opener: str = "{") -> str:
    marker = re.search(rf"\b(?:const|export\s+const)\s+{re.escape(variable_name)}\b", source)
    if not marker:
        raise ValueError(f"could not find variable {variable_name}")
    assignment = source.find("=", marker.end())
    if assignment == -1:
        raise ValueError(f"could not find assignment for {variable_name}")
    start = source.find(opener, assignment)
    if start == -1:
        raise ValueError(f"could not find {opener} block for {variable_name}")
    return balanced_block(source, start)


def read_property_name(text: str, index: int) -> tuple[str, int]:
    while index < len(text) and text[index] in " \n\r\t,":
        index += 1
    if index >= len(text) or text[index] == "}":
        return "", index
    if text[index] in {"'", '"'}:
        quote = text[index]
        index += 1
        start = index
        while index < len(text) and text[index] != quote:
            if text[index] == "\\":
                index += 2
            else:
                index += 1
        return text[start:index], index + 1
    match = re.match(r"[A-Za-z0-9_$-]+", text[index:])
    if not match:
        return "", index
    return match.group(0), index + len(match.group(0))


def split_top_level_object_properties(block: str) -> list[tuple[str, str]]:
    if not block.strip().startswith("{"):
        return []
    text = block.strip()[1:-1]
    result: list[tuple[str, str]] = []
    index = 0
    while index < len(text):
        name, index = read_property_name(text, index)
        if not name:
            break
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] != ":":
            break
        index += 1
        while index < len(text) and text[index].isspace():
            index += 1
        value_start = index
        if index < len(text) and text[index] in "{[(":
            value = balanced_block(text, index)
            index += len(value)
        else:
            quote = ""
            escaped = False
            depth = 0
            while index < len(text):
                char = text[index]
                if quote:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == quote:
                        quote = ""
                    index += 1
                    continue
                if char in {"'", '"', "`"}:
                    quote = char
                    index += 1
                    continue
                if char in "{[(":
                    depth += 1
                elif char in "}])":
                    if depth == 0:
                        break
                    depth -= 1
                elif char == "," and depth == 0:
                    break
                index += 1
            value = text[value_start:index].strip()
        result.append((name, value.strip()))
        while index < len(text) and text[index] != ",":
            index += 1
        if index < len(text) and text[index] == ",":
            index += 1
    return result


def parse_string_literal(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] in {"'", '"'} and stripped[-1] == stripped[0]:
        return stripped[1:-1]
    return ""


def extract_const_string_array(source: str, variable_name: str) -> list[str]:
    try:
        block = initializer_block(source, variable_name, "[")
    except ValueError:
        return []
    return re.findall(r"'([^']+)'", block)


def extract_type_union(source: str, type_name: str) -> list[str]:
    match = re.search(rf"export\s+type\s+{re.escape(type_name)}\s*=([\s\S]*?)(?:\n\n|export\s+type)", source)
    if not match:
        return []
    return re.findall(r"\|\s*'([^']+)'", match.group(1))


def parse_module_manifest(source: str) -> list[ModuleEntry]:
    pattern = re.compile(
        r"defineModule\(\s*'([^']+)'\s*,\s*'([ABC])'\s*,\s*"
        r"'(workbench|visualization|management)'\s*,\s*'([^']+)'\s*,\s*"
        r"'([^']+)'\s*,\s*'([^']+)'",
        re.MULTILINE,
    )
    return [
        ModuleEntry(
            module_key=match.group(1),
            layer_id=match.group(2),
            surface_kind=match.group(3),
            entry_route=match.group(4),
            legacy_hash=match.group(5),
            nav_group_key=match.group(6),
        )
        for match in pattern.finditer(source)
    ]


def parse_lazy_imports(source: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    pattern = re.compile(r"const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*lazy\(\(\)\s*=>\s*import\('([^']+)'\)\)")
    for component, import_path in pattern.findall(source):
        rel = Path("src/app/kernel") / import_path
        normalized = Path(*rel.parts)
        normalized = Path(re.sub(r"(^|/)\./", r"\1", normalized.as_posix()))
        parts: list[str] = []
        for part in normalized.parts:
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        resolved = Path(*parts)
        if not resolved.suffix:
            resolved = resolved.with_suffix(".tsx")
        result[component] = resolved
    return result


def parse_renderer_bindings(source: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    matches = list(re.finditer(r"if\s*\(\s*moduleKey\s*===\s*'([^']+)'\s*\)", source))
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        body = source[body_start:body_end]
        component = re.search(r"return\s*<([A-Z][A-Za-z0-9_]*)", body)
        if component:
            bindings[match.group(1)] = component.group(1)
    return bindings


def parse_record_array(source: str, variable_name: str) -> list[dict[str, Any]]:
    try:
        block = initializer_block(source, variable_name, "[")
    except ValueError:
        return []
    records = []
    index = 1
    while index < len(block) - 1:
        if block[index] != "{":
            index += 1
            continue
        raw = balanced_block(block, index)
        nav_modes_match = re.search(r"navModes:\s*\[([^\]]*)\]", raw)
        records.append(
            {
                "page": _first_match(raw, r"page:\s*'([^']+)'"),
                "nav_modes": re.findall(r"'([^']+)'", nav_modes_match.group(1)) if nav_modes_match else [],
                "phase1_surface": _first_match(raw, r"phase1Surface:\s*'([^']+)'"),
                "default_surface": _first_match(raw, r"defaultSurface:\s*'([^']+)'"),
                "revisit": _first_match(raw, r"revisit:\s*(true|false)") == "true",
            }
        )
        index += len(raw)
    return records


def _first_match(source: str, pattern: str) -> str:
    match = re.search(pattern, source)
    return match.group(1) if match else ""


def parse_catalog(source: str, variable_name: str) -> dict[str, dict[str, str]]:
    block = initializer_block(source, variable_name, "{")
    catalog: dict[str, dict[str, str]] = {}
    for namespace, namespace_block in split_top_level_object_properties(block):
        messages: dict[str, str] = {}
        if namespace_block.startswith("{"):
            for key, value in split_top_level_object_properties(namespace_block):
                messages[key] = parse_string_literal(value)
        catalog[namespace] = messages
    return catalog


def has_catalog_key(catalog: dict[str, dict[str, str]], key: str) -> bool:
    namespace, _, message_key = key.partition(".")
    if not namespace or not message_key:
        return False
    return bool(catalog.get(namespace, {}).get(message_key, "").strip())


def catalog_key_exists(catalog: dict[str, dict[str, str]], key: str) -> bool:
    namespace, _, message_key = key.partition(".")
    if not namespace or not message_key:
        return False
    return message_key in catalog.get(namespace, {})


def parse_theme_tokens(source: str) -> dict[str, dict[str, dict[str, str]]]:
    block = initializer_block(source, "THEME_TOKENS", "{")
    themes: dict[str, dict[str, dict[str, str]]] = {}
    for theme_name, theme_block in split_top_level_object_properties(block):
        groups: dict[str, dict[str, str]] = {}
        if not theme_block.startswith("{"):
            continue
        for group_name, group_block in split_top_level_object_properties(theme_block):
            leaves: dict[str, str] = {}
            if group_block.startswith("{"):
                for leaf_name, value in split_top_level_object_properties(group_block):
                    leaves[leaf_name] = parse_string_literal(value)
            groups[group_name] = leaves
        themes[theme_name] = groups
    return themes


def assert_no_duplicates(label: str, values: Iterable[str], problems: list[str]) -> None:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    for value, count in sorted(counts.items()):
        if count > 1:
            problems.append(f"{label} duplicated {value} {count} times")


def compare_sets(label: str, expected: Iterable[str], actual: Iterable[str], problems: list[str]) -> None:
    expected_list = list(expected)
    actual_list = list(actual)
    expected_set = set(expected_list)
    actual_set = set(actual_list)
    missing = [item for item in expected_list if item not in actual_set]
    extra = [item for item in actual_list if item not in expected_set]
    if missing:
        problems.append(f"{label} missing: {', '.join(missing)}")
    if extra:
        problems.append(f"{label} extra: {', '.join(extra)}")


def extract_string_literals(source: str, line_starts: list[int]) -> list[TextOccurrence]:
    literals: list[TextOccurrence] = []
    index = 0
    while index < len(source):
        quote = source[index]
        if quote not in {"'", '"', "`"}:
            index += 1
            continue
        start = index
        value_chars: list[str] = []
        index += 1
        escaped = False
        while index < len(source):
            char = source[index]
            if escaped:
                value_chars.append(char)
                escaped = False
                index += 1
                continue
            if char == "\\":
                escaped = True
                index += 1
                continue
            if char == quote:
                break
            value_chars.append(char)
            index += 1
        end = min(index + 1, len(source))
        literals.append(
            TextOccurrence(
                kind="template" if quote == "`" else "string",
                value="".join(value_chars),
                start=start,
                end=end,
                line=line_number_at(line_starts, start),
                line_text=line_at(source, line_starts, start).strip(),
            )
        )
        index = end
    return literals


def extract_jsx_text(source: str, line_starts: list[int], literal_spans: list[TextOccurrence]) -> list[TextOccurrence]:
    chars = list(source)
    for span in literal_spans:
        for index in range(span.start, min(span.end, len(chars))):
            chars[index] = " "
    masked = "".join(chars)
    nodes: list[TextOccurrence] = []
    index = 0
    while index < len(masked):
        start = masked.find(">", index)
        if start == -1:
            break
        end = masked.find("<", start + 1)
        if end == -1:
            break
        index = end + 1
        body = masked[start + 1 : end]
        if "{" in body or "}" in body:
            continue
        raw = re.sub(r"\s+", " ", body).strip()
        if not raw or not re.search(r"[A-Za-z\u4e00-\u9fff]", raw):
            continue
        nodes.append(
            TextOccurrence(
                kind="jsx_text",
                value=raw,
                start=start + 1,
                end=end,
                line=line_number_at(line_starts, start + 1),
                line_text=line_at(source, line_starts, start + 1).strip(),
            )
        )
    return nodes


def prop_name_before_literal(before: str) -> str:
    match = re.search(r"([A-Za-z0-9_-]+)\s*=\s*\{?\s*$", before)
    if match:
        return match.group(1)
    match = re.search(r"([A-Za-z0-9_-]+)\s*:\s*$", before)
    if match:
        return match.group(1)
    return ""


def is_import_or_path_literal(value: str, before: str) -> bool:
    if re.search(r"(?:from\s*|import\s*\(|lazy\(\(\)\s*=>\s*import\()\s*$", before):
        return True
    if re.match(r"^(\.{1,2}/|/|#|https?://|about:)", value):
        return True
    return bool(re.search(r"\.(css|html|js|jsx|md|png|svg|ts|tsx)$", value))


def is_css_literal(value: str, before: str) -> bool:
    if re.search(r"className\s*=\s*(?:\{\s*)?$", before):
        return True
    if re.search(r"className\s*[:=][^'\"]*$", before):
        return True
    return bool(
        re.match(r"^[a-z0-9_-]+(?:\s+[a-z0-9_-]+)*$", value)
        and re.search(r"(__|--|is-|app-|card|chip|figma-|graph-|kernel-|node-|page|toolbar|writing-)", value)
    )


def is_catalog_key(value: str) -> bool:
    return bool(re.match(r"^(shell|navigation|settings|shared|agentChat)\.[A-Za-z0-9_.-]+$", value))


def is_technical_token(value: str, module_keys: set[str], routes: set[str], legacy_hashes: set[str]) -> bool:
    if value in module_keys or value in routes or value in legacy_hashes:
        return True
    if value in {"A", "B", "C", "workbench", "visualization", "management", "admin", "default", "legacy-shell"}:
        return True
    if re.match(r"^(true|false|null|undefined)$", value):
        return True
    if re.match(r"^#[0-9a-fA-F]{3,8}$", value):
        return True
    if re.match(r"^[0-9.:-]+$", value):
        return True
    if re.match(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)*$", value):
        return True
    if re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", value):
        return True
    return False


def looks_human_facing(value: str) -> bool:
    trimmed = value.strip()
    if not trimmed:
        return False
    if re.search(r"[\u4e00-\u9fff]", trimmed):
        return True
    if re.search(r"\s", trimmed) and re.search(r"[A-Za-z]", trimmed):
        return True
    if re.match(r"^[A-Z][a-z]+(?:[A-Z][a-z]+)*$", trimmed):
        return True
    if re.search(r"[.!?。？！:：；，]", trimmed) and re.search(r"[A-Za-z\u4e00-\u9fff]", trimmed):
        return True
    return False


def classify_occurrence(
    occurrence: TextOccurrence,
    source: str,
    rel_path: Path,
    module_keys: set[str],
    routes: set[str],
    legacy_hashes: set[str],
) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", occurrence.value).strip()
    before = source[max(0, occurrence.start - 160) : occurrence.start]
    prop_name = prop_name_before_literal(before)
    if not value:
        return "allowed", "empty"
    if rel_path == FILES["catalog"]:
        return "allowed", "localized_catalog"
    if value in ALLOWED_PRODUCT_ACRONYMS:
        return "allowed", "product_acronym"
    if is_import_or_path_literal(value, before):
        return "allowed", "import_path_or_route"
    if is_css_literal(value, before):
        return "allowed", "css_selector_or_class"
    if is_catalog_key(value):
        return "allowed", "i18n_catalog_key"
    if prop_name in TECHNICAL_PROPS:
        return "allowed", f"technical_prop:{prop_name}"
    if is_technical_token(value, module_keys, routes, legacy_hashes):
        return "allowed", "technical_token"
    visible_context = occurrence.kind == "jsx_text" or prop_name in VISIBLE_PROPS
    if visible_context and looks_human_facing(value):
        return "gap", f"visible_{prop_name or occurrence.kind}"
    if looks_human_facing(value):
        return "gap", "human_text_literal"
    return "allowed", "technical_literal"


def increment(counter: dict[str, int], key: str, count: int = 1) -> None:
    counter[key] = counter.get(key, 0) + count


def build_business_string_report(
    root: Path,
    module_entries: list[ModuleEntry],
    module_to_file: dict[str, Path],
) -> dict[str, Any]:
    module_keys = {entry.module_key for entry in module_entries}
    routes = {entry.entry_route for entry in module_entries}
    legacy_hashes = {entry.legacy_hash for entry in module_entries}
    surface_by_module = {entry.module_key: entry.surface_kind for entry in module_entries}

    file_to_modules: dict[Path, list[str]] = {}
    for module_key, rel_path in module_to_file.items():
        file_to_modules.setdefault(rel_path, []).append(module_key)

    audit_files = sorted(set(KERNEL_BUSINESS_STRING_FILES + list(file_to_modules)))
    remaining_by_file: dict[str, int] = {}
    remaining_by_category: dict[str, int] = {}
    remaining_by_surface: dict[str, int] = {}
    allowed_by_category: dict[str, int] = {}
    checked_files: list[str] = []
    examples: list[dict[str, Any]] = []

    for rel_path in audit_files:
        full_path = root / FRONTEND_ROOT / rel_path
        if not full_path.is_file():
            continue
        checked_files.append(rel_path.as_posix())
        source = full_path.read_text(encoding="utf-8")
        line_starts = build_line_starts(source)
        literals = extract_string_literals(source, line_starts)
        occurrences = literals + extract_jsx_text(source, line_starts, literals)
        modules = file_to_modules.get(rel_path, [])
        surfaces = sorted({surface_by_module[module_key] for module_key in modules if module_key in surface_by_module})
        surface_key = surfaces[0] if len(surfaces) == 1 else ("mixed" if surfaces else "kernel")
        for occurrence in occurrences:
            bucket, category = classify_occurrence(occurrence, source, rel_path, module_keys, routes, legacy_hashes)
            if bucket == "gap":
                path_key = rel_path.as_posix()
                increment(remaining_by_file, path_key)
                increment(remaining_by_category, category)
                increment(remaining_by_surface, surface_key)
                if len(examples) < 12:
                    examples.append(
                        {
                            "path": path_key,
                            "line": occurrence.line,
                            "category": category,
                            "value": re.sub(r"\s+", " ", occurrence.value).strip()[:120],
                        }
                    )
            else:
                increment(allowed_by_category, category)

    return {
        "checked_files": checked_files,
        "checked_files_total": len(checked_files),
        "gap_free_files": len([path for path in checked_files if path not in remaining_by_file]),
        "known_allowed_literals_total": sum(allowed_by_category.values()),
        "known_allowed_by_category": dict(sorted(allowed_by_category.items())),
        "remaining_migration_gaps_total": sum(remaining_by_file.values()),
        "remaining_gaps_by_file": dict(sorted(remaining_by_file.items(), key=lambda item: (-item[1], item[0]))),
        "remaining_gaps_by_category": dict(sorted(remaining_by_category.items())),
        "remaining_gaps_by_surface": dict(sorted(remaining_by_surface.items())),
        "examples": examples,
    }


def build_page_refactor_report(
    module_entries: list[ModuleEntry],
    module_to_file: dict[str, Path],
    placement_by_mode: dict[str, dict[str, Any]],
    baseline_by_mode: dict[str, dict[str, Any]],
    expected_i18n_keys: set[str],
    catalog_shape: dict[str, dict[str, str]],
    catalogs: dict[str, dict[str, dict[str, str]]],
    business_report: dict[str, Any],
) -> dict[str, Any]:
    module_by_key = {entry.module_key: entry for entry in module_entries}
    page_records: dict[str, dict[str, Any]] = {}
    remaining_by_file = business_report["remaining_gaps_by_file"]

    for module_key, rel_path in sorted(module_to_file.items(), key=lambda item: (item[1].as_posix(), item[0])):
        entry = module_by_key[module_key]
        page_name = rel_path.stem
        item = page_records.setdefault(
            page_name,
            {
                "page": page_name,
                "component_file": rel_path.as_posix(),
                "modules": [],
                "layers": [],
                "route_surface_kinds": [],
                "placement_surfaces": [],
                "revisit": False,
                "route_covered": True,
                "surface_covered": True,
                "i18n_covered": True,
                "business_string_gaps": remaining_by_file.get(rel_path.as_posix(), 0),
            },
        )
        item["modules"].append(module_key)
        item["layers"].append(entry.layer_id)
        item["route_surface_kinds"].append(entry.surface_kind)
        placement = placement_by_mode.get(module_key)
        baseline = baseline_by_mode.get(module_key)
        if placement:
            item["placement_surfaces"].append(placement["surface"])
            item["revisit"] = bool(item["revisit"] or placement.get("revisit"))
        else:
            item["surface_covered"] = False
        if not baseline:
            item["surface_covered"] = False
        keys = {entry.title_key, entry.nav_label_key, entry.nav_group_key}
        if not keys.issubset(expected_i18n_keys) or not all(catalog_key_exists(catalog_shape, key) for key in keys):
            item["i18n_covered"] = False
        for catalog in catalogs.values():
            if not all(has_catalog_key(catalog, key) for key in keys):
                item["i18n_covered"] = False

    for item in page_records.values():
        item["modules"] = sorted(set(item["modules"]))
        item["layers"] = sorted(set(item["layers"]))
        item["route_surface_kinds"] = sorted(set(item["route_surface_kinds"]))
        item["placement_surfaces"] = sorted(set(item["placement_surfaces"]))
        if not item["route_covered"] or not item["surface_covered"] or not item["i18n_covered"]:
            item["refactor_state"] = "open_contract_gap"
        elif item["business_string_gaps"] > 0:
            item["refactor_state"] = "structural_sealed_text_open"
        else:
            item["refactor_state"] = "locally_sealed"

    states: dict[str, int] = {}
    for item in page_records.values():
        increment(states, item["refactor_state"])

    return {
        "pages_total": len(page_records),
        "state_counts": dict(sorted(states.items())),
        "full_page_refactor_complete": states.get("open_contract_gap", 0) == 0
        and states.get("structural_sealed_text_open", 0) == 0,
        "pages": sorted(page_records.values(), key=lambda item: (-item["business_string_gaps"], item["page"])),
    }


def build_report(root: Path) -> dict[str, Any]:
    root = root.resolve()
    problems: list[str] = []

    required_files = sorted(FILES.values())
    for rel_path in required_files:
        if not (root / FRONTEND_ROOT / rel_path).is_file():
            problems.append(f"missing frontend file: {(FRONTEND_ROOT / rel_path).as_posix()}")
    if problems:
        return {"status": "failed", "hard_failures": problems}

    module_manifest_source = read_text(root, FILES["module_manifest"])
    kernel_types_source = read_text(root, FILES["kernel_types"])
    render_source = read_text(root, FILES["render_kernel_module_content"])
    page_placement_source = read_text(root, FILES["page_placement"])
    baseline_source = read_text(root, FILES["baseline_inventory"])
    catalog_source = read_text(root, FILES["catalog"])
    theme_tokens_source = read_text(root, FILES["theme_tokens"])
    theme_types_source = read_text(root, FILES["theme_types"])
    frontend_kernel_app_source = read_text(root, FILES["frontend_kernel_app"])
    settings_source = read_text(root, FILES["settings_page"])

    module_entries = parse_module_manifest(module_manifest_source)
    if not module_entries:
        problems.append("moduleManifest has no defineModule entries")
    module_keys = [entry.module_key for entry in module_entries]
    assert_no_duplicates("moduleManifest.moduleKey", module_keys, problems)
    assert_no_duplicates("moduleManifest.entryRoute", [entry.entry_route for entry in module_entries], problems)
    assert_no_duplicates("moduleManifest.legacyHash", [entry.legacy_hash for entry in module_entries], problems)

    type_module_keys = extract_type_union(kernel_types_source, "KernelModuleKey")
    compare_sets("KernelModuleKey union", module_keys, type_module_keys, problems)

    for entry in module_entries:
        expected_surface = EXPECTED_SURFACE_BY_LAYER[entry.layer_id]
        expected_prefix = EXPECTED_ROUTE_PREFIX_BY_LAYER[entry.layer_id]
        if entry.surface_kind != expected_surface:
            problems.append(f"{entry.module_key} layer {entry.layer_id} surface must be {expected_surface}")
        if not entry.entry_route.startswith(expected_prefix):
            problems.append(f"{entry.module_key} route {entry.entry_route} must start with {expected_prefix}")

    lazy_imports = parse_lazy_imports(render_source)
    renderer_bindings = parse_renderer_bindings(render_source)
    compare_sets("renderer module bindings", module_keys, renderer_bindings.keys(), problems)
    module_to_file: dict[str, Path] = {}
    for module_key, component in renderer_bindings.items():
        rel_path = lazy_imports.get(component)
        if not rel_path:
            problems.append(f"renderer component {component} for {module_key} has no lazy import")
            continue
        if not (root / FRONTEND_ROOT / rel_path).is_file():
            problems.append(f"renderer component file missing for {module_key}: {rel_path.as_posix()}")
        module_to_file[module_key] = rel_path

    page_placement_records = parse_record_array(page_placement_source, "PAGE_PLACEMENT_BASELINE")
    baseline_records = parse_record_array(baseline_source, "BASELINE_PAGE_INVENTORY")
    placement_by_mode: dict[str, dict[str, Any]] = {}
    baseline_by_mode: dict[str, dict[str, Any]] = {}
    for record in page_placement_records:
        for mode in record["nav_modes"]:
            placement_by_mode[mode] = {
                "page": record["page"],
                "surface": record["phase1_surface"],
                "revisit": record["revisit"],
            }
    for record in baseline_records:
        for mode in record["nav_modes"]:
            baseline_by_mode[mode] = {
                "page": record["page"],
                "surface": record["default_surface"],
            }
    compare_sets("PAGE_PLACEMENT_MATRIX navModes", module_keys, placement_by_mode.keys(), problems)
    compare_sets("BASELINE_PAGE_INVENTORY navModes", module_keys, baseline_by_mode.keys(), problems)

    catalog_shape = parse_catalog(catalog_source, "MESSAGE_KEY_SHAPE")
    catalogs = {
        "zh-CN": parse_catalog(catalog_source, "zhCNMessages"),
        "en-US": parse_catalog(catalog_source, "enUSMessages"),
    }
    app_locales = extract_const_string_array(read_text(root, Path("src/app/platform/i18n/types.ts")), "APP_LOCALES")
    expected_i18n_keys = {entry.title_key for entry in module_entries}
    expected_i18n_keys.update(entry.nav_label_key for entry in module_entries)
    expected_i18n_keys.update(entry.nav_group_key for entry in module_entries)
    expected_i18n_keys.update(f"settings.locale.{locale}" for locale in app_locales)
    expected_i18n_keys.update({"settings.locale.label", "settings.theme.label"})

    for key in sorted(expected_i18n_keys):
        if not catalog_key_exists(catalog_shape, key):
            problems.append(f"MESSAGE_KEY_SHAPE missing {key}")
        for locale, catalog in catalogs.items():
            if not has_catalog_key(catalog, key):
                problems.append(f"{locale} catalog missing {key}")

    app_themes = extract_const_string_array(theme_types_source, "APP_THEMES")
    expected_i18n_keys.update(f"settings.theme.{theme}" for theme in app_themes)
    for theme in app_themes:
        key = f"settings.theme.{theme}"
        if not catalog_key_exists(catalog_shape, key):
            problems.append(f"MESSAGE_KEY_SHAPE missing {key}")
        for locale, catalog in catalogs.items():
            if not has_catalog_key(catalog, key):
                problems.append(f"{locale} catalog missing {key}")

    theme_tokens = parse_theme_tokens(theme_tokens_source)
    compare_sets("APP_THEMES token coverage", app_themes, theme_tokens.keys(), problems)
    theme_leaf_total = 0
    theme_leaf_present = 0
    for theme in app_themes:
        groups = theme_tokens.get(theme, {})
        for group_name, leaves in EXPECTED_THEME_LEAVES.items():
            theme_leaf_total += len(leaves)
            if group_name not in groups:
                problems.append(f"THEME_TOKENS.{theme} missing group {group_name}")
                continue
            for leaf in leaves:
                value = groups[group_name].get(leaf, "")
                if not value:
                    problems.append(f"THEME_TOKENS.{theme}.{group_name}.{leaf} is missing")
                else:
                    theme_leaf_present += 1
    for group_name in EXPECTED_THEME_LEAVES:
        if f"applyTokenGroup(target, '{group_name}'" not in theme_tokens_source:
            problems.append(f"applyThemeTokens does not apply {group_name}")
    if "useAppTheme()" not in frontend_kernel_app_source:
        problems.append("FrontendKernelApp must read shared app theme")
    if "applyThemeTokens(appTheme)" not in frontend_kernel_app_source:
        problems.append("FrontendKernelApp must apply shared app theme tokens")
    for required in ["APP_THEMES.map", "setAppTheme", "settings.theme.label", "settings.locale.label"]:
        if required not in settings_source:
            problems.append(f"SettingsPage missing theme/i18n control marker {required}")

    business_report = build_business_string_report(root, module_entries, module_to_file)
    page_report = build_page_refactor_report(
        module_entries,
        module_to_file,
        placement_by_mode,
        baseline_by_mode,
        expected_i18n_keys,
        catalog_shape,
        catalogs,
        business_report,
    )

    layer_counts: dict[str, int] = {}
    surface_counts: dict[str, int] = {}
    for entry in module_entries:
        increment(layer_counts, entry.layer_id)
        increment(surface_counts, entry.surface_kind)

    route_covered = len([entry for entry in module_entries if entry.entry_route and entry.legacy_hash])
    surface_covered = len(
        [
            entry
            for entry in module_entries
            if entry.surface_kind == EXPECTED_SURFACE_BY_LAYER[entry.layer_id]
            and entry.module_key in placement_by_mode
            and entry.module_key in baseline_by_mode
        ]
    )
    expected_catalog_key_count = len(expected_i18n_keys)
    present_catalog_key_count = len(
        [
            key
            for key in expected_i18n_keys
            if catalog_key_exists(catalog_shape, key) and all(has_catalog_key(catalog, key) for catalog in catalogs.values())
        ]
    )

    report = {
        "status": "failed" if problems else "ok",
        "gate_type": "frontend_migration_boundary_static",
        "frontend_root": FRONTEND_ROOT.as_posix(),
        "hard_failures": problems,
        "route_coverage": {
            "modules_total": len(module_entries),
            "modules_with_layered_and_legacy_routes": route_covered,
            "typed_module_keys": len(type_module_keys),
            "renderer_bound_modules": len(module_to_file),
        },
        "surface_coverage": {
            "modules_total": len(module_entries),
            "modules_with_expected_layer_surface_and_inventory": surface_covered,
            "module_counts_by_layer": dict(sorted(layer_counts.items())),
            "module_counts_by_route_surface": dict(sorted(surface_counts.items())),
            "page_placement_modes": len(placement_by_mode),
            "baseline_inventory_modes": len(baseline_by_mode),
            "revisit_pages": sorted(
                {
                    record["page"]
                    for record in page_placement_records
                    if record["revisit"]
                }
            ),
        },
        "i18n_coverage": {
            "expected_catalog_keys": expected_catalog_key_count,
            "present_catalog_keys_in_shape_and_locales": present_catalog_key_count,
            "locales": app_locales,
            "catalogs": sorted(catalogs),
        },
        "theme_coverage": {
            "themes": app_themes,
            "expected_token_leaves": theme_leaf_total,
            "present_token_leaves": theme_leaf_present,
            "groups": sorted(EXPECTED_THEME_LEAVES),
            "settings_control_static_markers_present": all(
                required in settings_source
                for required in ["APP_THEMES.map", "setAppTheme", "settings.theme.label", "settings.locale.label"]
            ),
        },
        "business_string_migration": {
            **business_report,
            "full_business_string_migration_complete": business_report["remaining_migration_gaps_total"] == 0,
        },
        "full_page_refactor_boundary": page_report,
    }
    return report


def print_summary(report: dict[str, Any]) -> None:
    status = report.get("status", "failed")
    if status != "ok":
        for problem in report.get("hard_failures", []):
            print(f"FAIL frontend_migration_boundary: {problem}", file=sys.stderr)
        return
    route = report["route_coverage"]
    surface = report["surface_coverage"]
    i18n = report["i18n_coverage"]
    theme = report["theme_coverage"]
    business = report["business_string_migration"]
    page = report["full_page_refactor_boundary"]
    print(
        "OK frontend_migration_boundary=passed "
        f"routes={route['modules_with_layered_and_legacy_routes']}/{route['modules_total']} "
        f"renderers={route['renderer_bound_modules']}/{route['modules_total']} "
        f"surfaces={surface['modules_with_expected_layer_surface_and_inventory']}/{surface['modules_total']} "
        f"i18n={i18n['present_catalog_keys_in_shape_and_locales']}/{i18n['expected_catalog_keys']} "
        f"theme={theme['present_token_leaves']}/{theme['expected_token_leaves']} "
        f"business_gaps={business['remaining_migration_gaps_total']} "
        f"page_refactor_complete={str(page['full_page_refactor_complete']).lower()}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current working directory.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument(
        "--strict-business-strings",
        action="store_true",
        help="Return non-zero if any remaining business-string gaps are found.",
    )
    args = parser.parse_args()

    report = build_report(Path(args.root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_summary(report)

    if report.get("hard_failures"):
        return 1
    if args.strict_business_strings and report["business_string_migration"]["remaining_migration_gaps_total"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
