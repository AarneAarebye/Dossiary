# Make Editor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dossiary's devices dialog makes a paired iPhone or iPad an editor on the Pi hub ("Make editor", after an inline confirmation) and a phone again ("Make phone again"), never showing that button on a Mac.

**Architecture:** The hub records `promoted` on a device it promotes and refuses to demote an editor without it. The Mac's local admin API gains `POST /admin/devices/:id/role`, passed on to the hub like `/name`. `dossiary.html` adds the buttons, the inline confirmation panel and the role labels.

**Spec:** `docs/superpowers/specs/2026-11-03-make-editor-design.md` (read it; it is binding).

**Tech Stack:** Swift (dossiary-sync: Hummingbird, `DeviceStore`, `AdminServer`), `dossiary.html` + Playwright (Python) tests.

## Global Constraints

- Wire format (exact):
  - Hub: `POST /v2/admin/devices/:id/role {"role": "editor"|"phone"}` (unchanged route). Promoting a phone sets `promoted: true`; demoting a promoted editor clears it; demoting an editor whose `promoted` isn't `true` → 409 `{"error": "not-promoted"}`, nothing changes. All existing answers stay (400 bad role or mirror/restore, 404 unknown device, 403 phone token, 401 no token, repeats are no-ops with 200).
  - Device JSON (`AdminDevice`, everywhere it is used): adds `"promoted": Bool`, always present, `false` when the stored value is absent.
  - Mac: `POST /admin/devices/:id/role {"role"}`: admin token (401), `Content-Type: application/json` (415), OPTIONS preflight; editor Mac → forwarded through `devicesCall` to `/devices/<id>/role` (hub answer passed through; 503 `hub-unreachable`, 502 `hub-unauthorized`); origin Mac → 404 `{"error": "needs-hub"}`, no change.
- `Device.promoted` is `Bool?`, encoded only when set; old `devices.json` decodes unchanged; `DeviceStoreError` gains `notPromoted(String)`.
- Dossiary: rows and texts exactly as the spec's table and "Dossiary (devices dialog)" section. Inline panel, no `confirm()`, no new modal layer. New UI text in all 7 `STRINGS` blocks (zh-Hant from zh-Hans via OpenCC s2t, `opencc-python-reimplemented` is installed; Armenian with the polite «ձեր»); `tests/test_i18n_coverage.py` passing; printed checks read `True` on pass; device names and service strings escaped. Header height unchanged; the toolbar untouched.
- Repos and branches: worktree `.worktrees/make-editor` (branch `feat/make-editor`) in dossiary-sync and in Dossiary, from `main`. Another session may be working on `main` in these repos: never commit to `main`, never push, don't bump versions (the controller does: dossiary-sync 0.15.0, Dossiary next minor).
- dossiary-sync: `swift test` green; `scripts/build-linux.sh` green. The existing `DeviceRoleTests` and `AdminEditorTests` stay green and are not loosened (a test that demotes an editor it paired as an editor directly must now expect 409; say so in the report if one does).

---

### Task 1: Hub remembers a promotion (dossiary-sync)

**Files:** `Sources/SyncServer/DeviceStore.swift` (`Device.promoted`, `setRole`, `DeviceStoreError.notPromoted`), `Sources/SyncServer/DeviceAdmin.swift` (`AdminDevice.promoted`, `changeRole` maps `notPromoted` to 409 `{"error": "not-promoted"}` in the JSON error shape the hub routes already use), `Tests/SyncServerTests/DeviceRoleTests.swift`, README (admin-API table row for the role route and the device list; a sentence on phones promoted before 0.15.0: Remove and pair again).

**Interfaces (produces):**
```swift
public var promoted: Bool?                     // Device; nil = never promoted
public func setRole(_ deviceId: String, to role: DeviceRole) throws -> Device
// .editor on a phone: role = .editor, promoted = true. .phone on an editor: requires promoted == true
// (else throws .notPromoted(id)), then role = .phone, promoted = nil. Same role: no-op, as today.
```
- [ ] Tests first: promote → answer and list have `promoted: true`, `devices.json` holds it; demote → `promoted: false` in the answer, `nil` stored; demote an editor paired as editor → 409 `not-promoted`, role still editor, its leases untouched; a phone, a mirror, a directly paired editor list `promoted: false`; a `devices.json` written without the key decodes; repeated promote/demote still 200 no-ops (existing test).
- [ ] Implement; `swift test`; Linux build; commit "Hub: remember a promoted phone and demote only promoted editors".

### Task 2: The Mac's role route (dossiary-sync)

**Files:** `Sources/SyncServer/AdminServer.swift` (route + preflight entry), `Tests/SyncServerTests/AdminEditorTests.swift` (forwarding), `Tests/SyncServerTests/AdminServerTests.swift` (origin Mac), README admin-API table.

**Interfaces (consumes):** Task 1's hub behaviour; `devicesCall(_:method:path:local:)` as `/admin/devices/:id/name` uses it.
- [ ] Tests first, editor Mac against the in-process hub (as `testRenameIsForwardedToTheHub`): promote the paired phone → 200, `role: "editor"`, `promoted: true`, the hub's store agrees; demote → 200 `role: "phone"`; demote the Mac's own device → 409 `not-promoted` passed through; unknown id → 404; bad role → 400; no token → 401; no JSON content type → 415; hub stopped → 503 `hub-unreachable`, nothing changes. Origin Mac (no editor): → 404 `{"error": "needs-hub"}`, its device store unchanged. OPTIONS preflight answered.
- [ ] Implement; `swift test`; Linux build; commit "Mac admin API: pass a device's role change on to the hub".

### Task 3: Buttons in the devices dialog (Dossiary)

**Files:** `dossiary.html` (`DEVICE_ROLE_LABEL_KEYS`/`deviceRoleLabel` with `editor` → "Mac" and promoted → "iPhone or iPad (editor)", `normalizeSyncDevice` keeps `promoted` as a boolean, `renderDevicesConnected` row markup and wiring, new `setDeviceRole(seq, deviceId, role)` and the panel helpers next to `startDeviceRename`, CSS for the panel reusing the dialog's existing classes, `STRINGS` ×7), `tests/test_devices_dialog.py` (fake: `/admin/devices/:id/role` with `S.roleFail` = status + error; new `scenario_make_editor`; add it to `SCENARIOS`), `tests/test_i18n_coverage.py` only if it needs the new keys listed.

New `STRINGS` keys (English; translate the rest): `devicesRoleEditor` "Mac", `devicesRolePromoted` "iPhone or iPad (editor)", `devicesMakeEditor` "Make editor", `devicesMakeEditorConfirm` "{name} will be able to change every library on this hub. It can also delete libraries for everyone, remove devices and make pairing codes.", `devicesCancel` "Cancel" (reuse an existing Cancel key if the dialog has one), `devicesMakePhone` "Make phone again", `devicesEditorNote` "Can change every library on this hub.", `devicesEditorPhoneNote` "As a phone it keeps only the libraries ticked for it.", `devicesNowEditor` "{name} is now an editor.", `devicesNowPhone` "{name} is a phone again.", `devicesNeedsHub` "Only a Raspberry Pi hub can make a phone an editor. This Mac isn't joined to one.", `devicesNotPromoted` "This device was paired as an editor, so it can't become a phone. Remove it and pair it again.".

- [ ] Tests first (`scenario_make_editor`; devices: a phone, a promoted editor, a plain editor "Studio iMac", a mirror): labels per row; "Make editor" only on the phone, "Make phone again" only on the promoted editor, no role button on the Mac or mirror; the promoted row shows both notes and no checkboxes; clicking Make editor opens one panel with the confirm text (name escaped: `HOSTILE` as a name sets no `window.__xss`); a second Make editor elsewhere would close the first (open, then open on another phone added for the check); Cancel and Escape close it, send nothing, dialog stays open; confirm sends exactly `POST /admin/devices/dev-1/role` with body `{"role":"editor"}` and JSON content type, then the row shows the promoted label and "Make phone again" and the status line `devicesNowEditor`; Make phone again sends `{"role":"phone"}` and the row is a phone row with checkboxes; `roleFail` 404 `needs-hub`, 409 `not-promoted`, 503 `hub-unreachable` → the right text under the row, row unchanged; 401 → Connect and token dropped; German: `devicesMakeEditor` is the German string; no page errors.
- [ ] Implement; run `tests/test_devices_dialog.py` and `tests/test_i18n_coverage.py` (both all `True`), plus `tests/test_i18n.py`; commit "Devices dialog: Make editor and Make phone again".

---

## After the tasks (controller)

1. Final whole-branch review; merge `feat/make-editor` into `main` in both repos (locally).
2. dossiary-sync 0.15.0 (`Version.swift`, README, `SettingsTests`); Dossiary next minor (`cutting-a-release` skill).
3. Armenian strings onto the review page; English into `~/Desktop/Dossiary make editor — English for Grammarly.txt`.
4. Push, tag, release, install (Mac, iMac, Pi) only after the user's OK.
