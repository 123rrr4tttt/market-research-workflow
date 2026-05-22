# Wave8-4 i18n/theme contract evidence

Date: 2026-05-22

Scope: shell-level i18n/theme closure evidence for `main/frontend-modern`.

## Result

Wave8-4 turns the previous i18n/theme platform evidence into a stricter executable contract.

The static gate now verifies:

- `APP_LOCALES` and `MESSAGE_CATALOGS` expose the same locale set.
- `zh-CN` and `en-US` exactly match `MESSAGE_KEY_SHAPE`, including non-empty values.
- `DEFAULT_APP_LOCALE` is included in `APP_LOCALES`.
- `DEFAULT_APP_THEME` is included in `APP_THEMES`.
- `APP_STORAGE_KEYS` includes the locale and theme keys used by the persisted stores.
- `SettingsPage` still wires user controls to `setAppLocale` and `setAppTheme`.
- `SettingsPage` renders options from `APP_LOCALES` and `APP_THEMES`, not hardcoded local lists.
- Every theme exposes the same token groups and leaf keys.

## Evidence

Command:

```bash
npm --prefix main/frontend-modern run -s check:topology-platform
```

Observed summary:

```json
{
  "status": "ok",
  "i18n_locales": ["zh-CN", "en-US"],
  "themes": ["light", "dark", "brand"],
  "theme_token_groups": ["background", "surface", "border", "text", "accent", "status", "interactive"]
}
```

The stronger gate is implemented in `main/frontend-modern/scripts/check_topology_platform_contract.mjs`.

## Boundary

This remains a platform contract slice. It does not claim full business-content localization, and it does not change page styling.
