#!/usr/bin/env python3
"""Focused tests for the frontend migration boundary checker."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_frontend_migration_boundary.py"
SPEC = importlib.util.spec_from_file_location("check_frontend_migration_boundary", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


MODULES = [
    ("overviewTasks", "C", "management", "/admin/process", "#process-management.html", "navigation.group.overview", "ProcessPage"),
    ("dataDashboard", "B", "visualization", "/visual/dashboard", "#dashboard.html", "navigation.group.dataFacets", "DashboardPage"),
    ("flowWriting", "A", "workbench", "/workbench/writing", "#writing-workbench.html", "navigation.group.flow", "WritingWorkbenchPage"),
]

THEME_GROUPS = {
    "background": ["app", "subtle"],
    "surface": ["base", "raised"],
    "border": ["default", "strong"],
    "text": ["primary", "secondary"],
    "accent": ["primary", "contrast"],
    "status": ["success", "warning", "danger"],
    "interactive": ["hover", "focus", "active"],
}


def write(root: Path, rel_path: str, text: str) -> None:
    path = root / checker.FRONTEND_ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_manifest() -> str:
    rows = []
    for module_key, layer, surface, route, legacy_hash, group, _component in MODULES:
        rows.append(
            "  defineModule("
            f"'{module_key}', '{layer}', '{surface}', '{route}', '{legacy_hash}', "
            f"'{group}', [], false),"
        )
    return "\n".join(
        [
            "import type { KernelModuleKey, ModuleManifestEntry } from './types'",
            "function defineModule(",
            "  moduleKey: KernelModuleKey,",
            "  layerId: ModuleManifestEntry['layerId'],",
            "  surfaceKind: ModuleManifestEntry['surfaceKind'],",
            "  entryRoute: ModuleManifestEntry['entryRoute'],",
            "  legacyHash: string,",
            "  navGroupKey: ModuleManifestEntry['navGroupKey'],",
            "  keepLoops: readonly string[],",
            "  supportsInfoCard: boolean,",
            "): ModuleManifestEntry {",
            "  return { moduleKey, layerId, surfaceKind, entryRoute, legacyHashes: [legacyHash],",
            "    titleKey: `shell.title.${moduleKey}`, navLabelKey: `navigation.item.${moduleKey}`,",
            "    navGroupKey, storybookGroup: 'Workbench', requiredContext: ['project_key'], keepLoops,",
            "    supportsInfoCard, visibleInNav: true, enabled: true, designSourceRefs: [] }",
            "}",
            "export const moduleManifest: readonly ModuleManifestEntry[] = [",
            *rows,
            "] as const",
        ]
    )


def build_kernel_types() -> str:
    module_union = "\n".join(f"  | '{module_key}'" for module_key, *_rest in MODULES)
    return "\n".join(
        [
            "export const MODULE_NAV_GROUP_KEYS = [",
            "  'navigation.group.overview',",
            "  'navigation.group.dataFacets',",
            "  'navigation.group.flow',",
            "] as const",
            "export type ModuleNavGroupKey = (typeof MODULE_NAV_GROUP_KEYS)[number]",
            "export type LayerId = 'A' | 'B' | 'C'",
            "export type SurfaceKind = 'workbench' | 'visualization' | 'management'",
            "export type KernelModuleKey =",
            module_union,
            "export type NavMode = KernelModuleKey",
            "export type ModuleManifestEntry = {",
            "  moduleKey: KernelModuleKey",
            "  layerId: LayerId",
            "  surfaceKind: SurfaceKind",
            "  entryRoute: `/${string}`",
            "  legacyHashes: readonly string[]",
            "  titleKey: `shell.title.${KernelModuleKey}`",
            "  navLabelKey: `navigation.item.${KernelModuleKey}`",
            "  navGroupKey: ModuleNavGroupKey",
            "  storybookGroup: string",
            "  requiredContext: readonly string[]",
            "  keepLoops: readonly string[]",
            "  supportsInfoCard: boolean",
            "  visibleInNav: boolean",
            "  enabled: boolean",
            "  designSourceRefs: readonly string[]",
            "}",
        ]
    )


def build_renderer() -> str:
    imports = []
    branches = []
    for module_key, *_rest, component in MODULES:
        imports.append(f"const {component} = lazy(() => import('../../pages/{component}'))")
        branches.append(f"  if (moduleKey === '{module_key}') return <{component} />")
    return "\n".join(
        [
            "import { lazy } from 'react'",
            *imports,
            "export function renderKernelModuleContent({ moduleKey }) {",
            *branches,
            "  return null",
            "}",
        ]
    )


def build_record_array(variable_name: str, surface_field: str) -> str:
    rows = []
    surface_by_module = {
        "overviewTasks": "management",
        "dataDashboard": "management",
        "flowWriting": "workbench",
    }
    for module_key, _layer, _surface, _route, _legacy_hash, _group, component in MODULES:
        rows.append(
            "  { "
            f"page: '{component}', navModes: ['{module_key}'], "
            f"{surface_field}: '{surface_by_module[module_key]}', "
            "reason: 'fixture', revisit: false, rubricSignals: {} },"
        )
    return f"const {variable_name}: readonly unknown[] = [\n" + "\n".join(rows) + "\n] as const\n"


def catalog_text(*, missing_en_key: str | None = None) -> str:
    keys = {
        "shell": [f"title.{module_key}" for module_key, *_rest in MODULES],
        "navigation": [
            "group.overview",
            "group.dataFacets",
            "group.flow",
            *[f"item.{module_key}" for module_key, *_rest in MODULES],
        ],
        "settings": [
            "locale.label",
            "locale.zh-CN",
            "locale.en-US",
            "theme.label",
            "theme.light",
            "theme.dark",
            "theme.brand",
        ],
        "shared": ["loading"],
    }

    def render_catalog(variable_name: str, actual: bool) -> str:
        namespaces = []
        for namespace, namespace_keys in keys.items():
            rows = []
            for key in namespace_keys:
                value = "" if not actual else f"{namespace}.{key}"
                if variable_name == "enUSMessages" and missing_en_key == f"{namespace}.{key}":
                    value = ""
                rows.append(f"    '{key}': '{value}',")
            namespaces.append(f"  {namespace}: {{\n" + "\n".join(rows) + "\n  },")
        return f"const {variable_name} = {{\n" + "\n".join(namespaces) + "\n} as const\n"

    return "\n".join(
        [
            "import { DEFAULT_APP_LOCALE, type AppLocale } from './types'",
            render_catalog("MESSAGE_KEY_SHAPE", actual=False),
            render_catalog("zhCNMessages", actual=True),
            render_catalog("enUSMessages", actual=True),
            "export const MESSAGE_CATALOGS: Record<AppLocale, typeof zhCNMessages> = {",
            "  'zh-CN': zhCNMessages,",
            "  'en-US': enUSMessages,",
            "}",
        ]
    )


def theme_tokens_text() -> str:
    themes = []
    for theme in ["light", "dark", "brand"]:
        groups = []
        for group, leaves in THEME_GROUPS.items():
            leaf_rows = [f"      {leaf}: '#123456'," for leaf in leaves]
            groups.append(f"    {group}: {{\n" + "\n".join(leaf_rows) + "\n    },")
        themes.append(f"  {theme}: {{\n" + "\n".join(groups) + "\n  },")
    apply_rows = [f"  applyTokenGroup(target, '{group}', tokens.{group})" for group in THEME_GROUPS]
    return "\n".join(
        [
            "export const THEME_TOKENS = {",
            *themes,
            "} as const",
            "export function applyThemeTokens(theme, target = document.documentElement) {",
            "  const tokens = THEME_TOKENS[theme]",
            *apply_rows,
            "}",
            "function applyTokenGroup() {}",
        ]
    )


class FrontendMigrationBoundaryCheckerTestCase(unittest.TestCase):
    def make_repo(self, *, missing_en_key: str | None = None) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        write(root, "src/app/kernel/moduleManifest.ts", build_manifest())
        write(root, "src/app/kernel/types.ts", build_kernel_types())
        write(root, "src/app/kernel/renderKernelModuleContent.tsx", build_renderer())
        write(root, "src/app/topology/pagePlacementMatrix.ts", build_record_array("PAGE_PLACEMENT_BASELINE", "phase1Surface"))
        write(root, "src/app/topology/baselineInventory.ts", build_record_array("BASELINE_PAGE_INVENTORY", "defaultSurface"))
        write(root, "src/app/platform/i18n/types.ts", "export const APP_LOCALES = ['zh-CN', 'en-US'] as const\nexport const DEFAULT_APP_LOCALE = 'zh-CN'\n")
        write(root, "src/app/platform/i18n/catalog.ts", catalog_text(missing_en_key=missing_en_key))
        write(root, "src/app/platform/theme/types.ts", "export const APP_THEMES = ['light', 'dark', 'brand'] as const\nexport const DEFAULT_APP_THEME = 'dark'\n")
        write(root, "src/app/platform/theme/tokens.ts", theme_tokens_text())
        write(root, "src/app/kernel/FrontendKernelApp.tsx", "export default function App(){ const appTheme = useAppTheme(); applyThemeTokens(appTheme); return null }\n")
        write(root, "src/pages/SettingsPage.tsx", "APP_THEMES.map((theme) => theme); setAppTheme('dark'); 'settings.theme.label'; 'settings.locale.label'\n")

        for _module_key, _layer, _surface, _route, _legacy_hash, _group, component in MODULES:
            body = "<h1>Hard coded Workbench</h1>" if component == "WritingWorkbenchPage" else "<section />"
            write(root, f"src/pages/{component}.tsx", f"export default function {component}() {{ return {body} }}\n")

        return root

    def test_checker_accepts_static_contracts_and_reports_open_page_text(self) -> None:
        report = checker.build_report(self.make_repo())

        self.assertEqual(report["status"], "ok", report["hard_failures"])
        self.assertEqual(report["route_coverage"]["modules_total"], 3)
        self.assertEqual(report["route_coverage"]["renderer_bound_modules"], 3)
        self.assertEqual(report["surface_coverage"]["modules_with_expected_layer_surface_and_inventory"], 3)
        self.assertEqual(
            report["i18n_coverage"]["present_catalog_keys_in_shape_and_locales"],
            report["i18n_coverage"]["expected_catalog_keys"],
        )
        self.assertGreater(report["business_string_migration"]["remaining_migration_gaps_total"], 0)
        self.assertFalse(report["full_page_refactor_boundary"]["full_page_refactor_complete"])
        self.assertEqual(report["full_page_refactor_boundary"]["state_counts"]["structural_sealed_text_open"], 1)

    def test_checker_rejects_missing_i18n_message_value(self) -> None:
        report = checker.build_report(self.make_repo(missing_en_key="shell.title.flowWriting"))

        self.assertEqual(report["status"], "failed")
        self.assertTrue(
            any("en-US catalog missing shell.title.flowWriting" in item for item in report["hard_failures"]),
            report["hard_failures"],
        )


if __name__ == "__main__":
    unittest.main()
