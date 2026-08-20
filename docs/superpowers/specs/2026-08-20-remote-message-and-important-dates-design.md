# Remote Message Posting & Important Dates Admin

## Problem

**Remote messages.** The custom message that scrolls in the marquee's
rotation can only be changed from `cubsmarquee.local/admin`, which is
Flask on `0.0.0.0:80` and reachable only from the house LAN. There is no
tunnel and no cloud component. A relative who wants to put "HAPPY
BIRTHDAY GRANDPA" on the board has to be standing in the building.

**Important dates.** `celebration_display.py` already renders birthdays
and holidays from a `celebrations` list in `/home/pi/config.json`, and
`off_season_handler.py:801` already gives it a rotation slot gated by the
`enable_celebrations` toggle at `wifi_config_server.py:1006`. But there is
no UI for the list itself — the only way to add a date today is to hand-edit
config.json over SSH. The feature is built and unreachable.

## Solution — Part 1: Remote messages

A small Cloudflare Worker holds the current message; each Pi polls it and
caches the result locally. Nothing inbound to the house network, and the
admin panel (which has no authentication and can reboot the Pi and rewrite
WiFi credentials) stays LAN-only.

### Worker: `workers/marquee-message/`

One deployment serving all three boards on separate paths, so each board
has its own link and its own passphrase to hand out.

| Route | Purpose |
|-------|---------|
| `GET /b/<board>` | Posting page: textarea, passphrase field, live preview |
| `POST /b/<board>` | Validate passphrase, normalize text, write KV |
| `GET /api/b/<board>` | Device poll; requires that board's token |
| `DELETE /api/b/<board>` | Clear; requires that board's token |

**Auth** is a single Worker secret `BOARDS`, a JSON map
`{"<board>": {"pass": "...", "token": "..."}}`, set with
`wrangler secret put BOARDS`. Keeping it in a secret rather than KV means
auth costs no KV read and rotating a passphrase is one command. Compare
with a constant-time comparison; return 401 without revealing which of
board/passphrase was wrong.

**KV** holds one key per board, `msg:<board>`:

```json
{"text": "HAPPY BIRTHDAY GRANDPA", "id": "<uuid>", "updated_at": 1755650000}
```

`id` is a fresh `crypto.randomUUID()` on every post. The Pi keys "have I
shown this yet" off `id`, not off the text, so re-posting identical text
still triggers a takeover.

**Normalization on POST**, so the poster sees the real result instead of
discovering it on the panel:

- Fold typographic punctuation and strip anything the latin-1 bitmap fonts
  cannot draw — the same substitutions `to_bitmap_text()` applies in
  `scoreboard_manager.py:44`, which `draw_text` already runs on every
  string it renders (`scoreboard_manager.py:645`). Emoji become `?`.
- Collapse whitespace, trim, reject empty.
- Reject over 200 characters, with the count shown on the form. Rejecting
  beats truncating: a message silently cut mid-word is a worse surprise
  than being told to shorten it.

The posting page runs the identical fold in JS as you type and shows the
folded text, so what you see is what the panel draws.

### Pi poller: `remote_message.py` (new)

A daemon thread started from `main.py`, polling `remote_message_url` every
30 seconds with the `remote_message_token` as a bearer header.

The thread re-reads config at the top of each cycle via the cached
`load_user_config()`, which only re-parses when the file changes. So URL,
token and the enable toggle all apply live, with no restart and no
per-poll file parse.

Writes `/home/pi/remote_message.json` via temp-file + `os.replace`, the
same atomic pattern `save_config()` uses at `wifi_config_server.py:278`.

**It deliberately does not write config.json.** `/save_config` does a
read-modify-write on that file; a poller racing it would silently drop
whichever settings edit lost. The cache is its own file for that reason.

Cache contents: `{"text": ..., "id": ..., "fetched_at": ...}`.

**Failure handling — the cache is authoritative when the network is not:**

| Condition | Behavior |
|-----------|----------|
| Timeout / connection error | Keep cache; message keeps showing through an outage |
| Non-200 | Keep cache; log at debug (a poll failing every 30s must not flood the log) |
| Malformed / missing fields | Keep cache; log once per distinct error |
| 204 / empty (cleared) | Clear the cache file |

Every exception is caught inside the thread. The poller can never raise
into the display loop.

Module functions consumed by the display side:

- `current_message() -> str | None` — cached text, or None
- `take_pending_takeover() -> str | None` — returns the text exactly once
  per new `id`, then records that id as shown

### Rotation integration

Two touch points.

**1. Takeover, in `_tick()`** (`off_season_handler.py:620`). `_tick()`
already runs the flight interstitial between rotation segments; a takeover
is the same shape:

```python
def _tick():
    if flights_between and flights_enabled:
        ...flight interstitial...
    self._maybe_show_remote_takeover()          # new
    if between_callback is not None:
        return bool(between_callback())
    return False
```

`_maybe_show_remote_takeover()` calls `take_pending_takeover()` and, when
it returns text, shows it for 60 seconds before the rotation resumes where
it left off.

Putting it in `_tick()` rather than aborting the cycle (the way the
All-Star takeover does at `main.py:463`) means the rotation is interrupted,
not restarted — the segment order after the takeover is preserved.

**Latency is bounded by the segment, not the poll.** A message appears
within one segment boundary, so 0–3 minutes. Making it truly instant would
mean threading an interrupt check through roughly twenty independent
display loops; not worth it for this feature.

**Live games do not get takeovers.** `_display_rotation_cycle` is the only
integration point, so a live MLB or preempting NFL game holds the display
until it ends. That matches how every other takeover in the codebase
defers to a live game.

**2. Rotation slot**, in `_display_custom_message()`
(`off_season_handler.py:1228`). Line 1231 becomes: prefer
`remote_message.current_message()`, fall back to the configured
`custom_message`. So a posted message owns the slot until it is replaced
or cleared, and clearing reverts to whatever `custom_message` was — the
original is never overwritten.

`_display_custom_message` gains one parameter, `message_only=False`. When
True it repeats the message and skips the facts rotation; the takeover
uses it. This is a smaller change than a parallel rendering path and
keeps the marquee background and scroll behavior identical.

### Admin panel

A new "Remote Message" block:

- Current remote message, read-only, with its age
- **Clear** button → Flask `POST /clear_remote_message` → Worker
  `DELETE /api/b/<board>` with the token → clears the local cache
- `remote_message_url` and `remote_message_token` fields
- `enable_remote_message` toggle, matching every other screen

When `enable_remote_message` is false the poller stays idle and
`current_message()` returns None, so the board falls back to
`custom_message` without needing the cache cleared.

### New config keys

`remote_message_url` (str, `''`), `remote_message_token` (str, `''`),
`enable_remote_message` (bool, `True`).

All three go in `DEFAULT_CONFIG` and `APPLIES_LIVE_KEYS` in
`wifi_config_server.py`. `tests/test_reboot_prompt.py` fails on a key
classified in neither set, so this is enforced, not remembered.

## Solution — Part 2: Important dates

### Data contract

Unchanged shape plus one optional field:

```json
{"date": "07-09", "name": "RYAN", "type": "birthday", "year": 2027}
```

`year` absent means annual — today's behavior, unchanged. When present it
must equal the current year, so a one-off fires once and then stops
matching. `_todays_celebrations()` (`celebration_display.py:29`) gains
exactly that one condition.

Expired one-offs are **not** deleted automatically. The admin row marks
them "expired" so you can remove them deliberately; silently dropping a
user's saved data is worse than a stale row.

### Admin UI

An "Important Dates" block beside the existing `enable_celebrations`
toggle. Repeating rows:

`[month/day] [name] [type ▾ + custom] [year — blank = every year] [remove]`

plus an "Add date" button, serialized into the existing `celebrations`
array on save.

**Each row previews the three lines as the panel draws them** — `HAPPY` /
`TYPE` / `NAME!` — turning red past 16 characters.
`_draw_celebration_frame` (`celebration_display.py:78`) lays out
`small_bold` at 6px per character on a 96px panel, so 16 characters is a
hard ceiling. The preview makes that visible while typing rather than on
someone's birthday.

The type dropdown offers Birthday / Anniversary / Holiday plus a
free-text option. Holiday is special in the renderer: it drops the type
line entirely, giving `HAPPY` / `THANKSGIVING!`.

### Server-side validation

`celebrations: []` joins `DEFAULT_CONFIG` and `APPLIES_LIVE_KEYS`, plus a
`_validate_celebrations()` beside the existing `_clamp_brightness` and
`_validate_hhmm` coercions, falling back to `previous_config` on a bad
payload exactly as they do.

Rules: must be a list; non-dict entries dropped; `date` must match
`^\d{2}-\d{2}$` *and* be a real calendar date; `name` non-empty after
strip; `type` defaults to `birthday`; `year`, if present, an int in
2000–2100.

This is not defensive politeness. `/save_config` copies request JSON
straight into config.json, and `celebration_display` runs on the display
thread — a malformed entry landing there is a screen that fails to come
up.

## Not doing

Deliberately out of scope, recorded so it is not re-litigated:

- **Moderation queue / per-poster identity.** Posting is private behind a
  shared passphrase per board; there is no untrusted poster to moderate.
- **Message expiry timers.** Messages live until replaced or cleared.
- **Rate limiting on the Worker.** No anonymous access to abuse.
- **Refactoring `_message_for()`** (`celebration_display.py:41`), which is
  tested but unused — `_draw_celebration_frame` builds its lines
  independently. Pre-existing, unrelated to this work, left alone.
- **`"02-29"` handling.** It fires only in leap years. Correct enough.

## Testing

**Python (`pytest`), Pi side:**

- Poller: parses a good response; keeps the cache on timeout, non-200, and
  malformed JSON; clears on 204.
- `take_pending_takeover()` returns text once per `id` and None thereafter;
  a re-post of identical text with a new `id` does fire again.
- `_display_custom_message` prefers the cached remote text and falls back
  to `custom_message` when the cache is empty or the feature is disabled.
- Extend `TestCelebrations` (`tests/test_features.py:1503`): year-pinned
  entry matches in its year and not others; un-pinned matches any year;
  expired one-off never matches.
- `_validate_celebrations`: bad date string, impossible calendar date
  (`02-30`), missing name, non-list payload, out-of-range year, and a
  round-trip through `/save_config`.
- `tests/test_reboot_prompt.py` already enforces classification of the
  four new config keys.

**Vitest, Worker side** (`@cloudflare/vitest-pool-workers`), covering the
auth boundary specifically:

- POST with wrong passphrase → 401, KV unchanged
- POST with right passphrase → 200, KV holds folded text and a new `id`
- Device GET without token → 401; with token → the stored message
- DELETE with token → subsequent GET is empty
- Normalization: smart quotes folded, emoji become `?`, >200 chars
  rejected, whitespace-only rejected
- Two posts of identical text produce different `id`s
