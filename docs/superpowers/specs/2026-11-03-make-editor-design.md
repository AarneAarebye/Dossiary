# "Make editor" in Dossiary's devices dialog — design

Date: 2026-11-03. Repos: dossiary-sync (hub and the Mac's admin API), Dossiary (`dossiary.html`, the devices dialog).
Follows `dossiary-ios/docs/superpowers/specs/2026-11-01-share-local-library-design.md` (section "Dossiary (Mac app,
devices dialog)" and "As built"), which left this button unbuilt.

## Problem

An iPhone or iPad can share a library it made with the Pi hub only when the hub has made it an editor. Today that
takes a `curl` to the Pi's `POST /v2/admin/devices/:id/role` with an editor's token. The devices dialog should do it.

Second problem: the hub lists a promoted phone and a joined Mac the same way (`role: "editor"`). A "Make phone again"
button keyed on the role alone would also appear on a Mac's row, and demoting a Mac breaks its sync.

## Decisions

- **The hub remembers a promotion.** `Device` gains an optional `promoted: Bool?`. `DeviceStore.setRole(_, to: .editor)`
  on a phone sets it to `true`; `setRole(_, to: .phone)` clears it (`nil`). The device list (`AdminDevice`) always
  reports `promoted` as a boolean (`false` when absent). Older `devices.json` files decode unchanged.
- **Only a promoted editor can be demoted.** `setRole(_, to: .phone)` on an editor whose `promoted` is not `true`
  throws a new `DeviceStoreError.notPromoted`; the hub route answers 409 `{"error": "not-promoted"}`. A phone set to
  phone stays a no-op (200), as today.
- **Phones promoted before this change** (by `curl`) carry no flag, so they show as plain editors without a button.
  To turn one back into a phone: Remove it in the dialog and pair it again. Written in the README, no migration.
- **The Mac's admin API passes the call on.** New `POST /admin/devices/<id>/role` with `{role}`, admin token, JSON
  required (415), OPTIONS preflight, through `devicesCall` like `/name`: on an editor Mac forwarded to the hub's
  `/v2/admin/devices/<id>/role` with the usual 503 `hub-unreachable` and 502 `hub-unauthorized`; the hub's own answer
  (200 device, 400, 404, 409 `not-promoted`) is passed through. On a Mac that is not joined to a hub (origin Mac) it
  answers 404 `{"error": "needs-hub"}` and changes nothing.
- **Dossiary asks before promoting.** No `confirm()`: an inline panel under the phone's row, inside the devices dialog.
  "Make phone again" works on one click.

## Dossiary (devices dialog)

Per device row, by `role` and `promoted`:

| Row | Role label | Under the head | Button |
|---|---|---|---|
| `phone` | "iPhone or iPad" (unchanged) | library checkboxes (unchanged) | "Make editor" |
| `editor`, `promoted: true` | "iPhone or iPad (editor)" | "Can change every library on this hub." and "As a phone it keeps only the libraries ticked for it." | "Make phone again" |
| `editor`, not promoted | "Mac" | its libraries, as today | none |
| `mirror`, `restore` | unchanged | unchanged | none |

- **Make editor** opens a panel under the row's head (one at a time; opening another closes the first):
  "{name} will be able to change every library on this hub. It can also delete libraries for everyone, remove
  devices and make pairing codes." with buttons "Make editor" and "Cancel". Escape cancels (and does not close the
  dialog). Confirm sends `POST /admin/devices/<id>/role {"role": "editor"}`; while it runs the panel's buttons are
  disabled.
- **Make phone again** sends `{"role": "phone"}` at once; the button is disabled while it runs.
- **Answer 200:** the row is replaced with the device from the answer (`normalizeSyncDevice` keeps `promoted`) and a
  status line says "{name} is now an editor." / "{name} is a phone again.".
- **401:** back to Connect (`devicesTokenRejected`), as every other call.
- **Other answers:** the panel (or, for Make phone again, a line under the row head) shows the reason; nothing in the
  row changes. `needs-hub` → "Only a Raspberry Pi hub can make a phone an editor. This Mac isn't joined to one.";
  `not-promoted` → "This device was paired as an editor, so it can't become a phone. Remove it and pair it again.";
  anything else → `syncErrorText(res)` as today.
- All new text in the seven `STRINGS` blocks; the Armenian goes onto the review page
  (https://claude.ai/artifact/Bysut9bJ4JpHCFGer7pPtt) and the English into
  `~/Desktop/Dossiary make editor — English for Grammarly.txt`. Neutral wording, no alarm colours.

## Testing

- dossiary-sync (`swift test`): promotion sets `promoted`, the list reports it (and `false` for a phone, a Mac, a
  mirror); demoting a promoted phone clears it; demoting a never-promoted editor → 409 `not-promoted`, role unchanged;
  an old `devices.json` without the field decodes; the Mac's `/admin/devices/<id>/role` is forwarded (promote,
  demote, 409 passed through, hub down → 503, no token → 401, no JSON → 415); an origin Mac answers 404 `needs-hub`.
  The existing `DeviceRoleTests` stay green and are not loosened.
- Dossiary (`tests/test_devices_dialog.py`, new scenario): which rows get which button and label; the panel opens,
  Cancel and Escape send nothing; confirm sends the exact body and updates the row; Make phone again; the
  `needs-hub`, `not-promoted` and 503 texts; 401 to Connect; hostile device names escaped; German labels;
  `tests/test_i18n_coverage.py` passing.
- On the devices: promote the iPhone from Dossiary, share a library from the phone, make it a phone again and check
  it keeps the libraries ticked for it.

## Release

dossiary-sync 0.15.0 (Macs and Pi) and the next Dossiary minor version. The Pi needs 0.15.0 before the button works
there; an older Pi answers demotions of Macs without the guard, and promotions without the flag.

## Not in this design

- The phone app's Devices-sheet sentence ("This iPhone can change every library on this hub").
- Marking phones promoted before this change.
- Limiting what an editor phone may do on the hub.
