# Important Dates Admin Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin panel a UI for the `celebrations` list that
`celebration_display.py` already renders, and let a date optionally pin a
year so it fires once instead of annually.

**Architecture:** Three layers, bottom-up. The display module learns the
optional `year` field; the Flask save path learns to validate the list;
the admin page grows a row editor that serializes into the same
`celebrations` array that already exists in config.json. No new files —
this fills a gap in three existing ones.

**Tech Stack:** Python 3.9+, Flask, pendulum, pytest. Vanilla JS in the
admin template (the page has no build step and no framework — do not add
one).

**Spec:** `docs/superpowers/specs/2026-08-20-remote-message-and-important-dates-design.md`
(Part 2, plus the "Not doing" section)

## Global Constraints

- **16 characters per line, hard.** `_draw_celebration_frame` lays out
  `small_bold` at 6px per character on a 96px panel
  (`celebration_display.py:78-83`). Longer lines run off the edge.
- **Entry shape:** `{"date": "MM-DD", "name": str, "type": str}` plus
  optional `"year": int`. `date` is always MM-DD with no year in it.
- **`year` absent means annual.** That is the existing behavior and must
  not change for entries that lack the field.
- **`type: "holiday"` is special** — the renderer drops the type line
  entirely, giving `HAPPY` / `THANKSGIVING!`.
- **Never auto-delete a user's saved date.** Expired one-offs are marked
  in the UI, not removed.
- **Do not refactor `_message_for()`** (`celebration_display.py:41`). It is
  tested but unused; `_draw_celebration_frame` builds its lines
  independently. Pre-existing and out of scope.
- **Every new config key must be classified** in `REBOOT_REQUIRED_KEYS` or
  `APPLIES_LIVE_KEYS`. `tests/test_reboot_prompt.py::TestKeyClassification`
  fails otherwise.
- Run the suite with `pytest tests/ -v` from the repo root.

---

### Task 1: Optional `year` on celebration matching

**Files:**
- Modify: `celebration_display.py:28-39` (`_todays_celebrations`)
- Test: `tests/test_features.py` (extend `class TestCelebrations`, line 1503)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CelebrationDisplay._todays_celebrations(config: dict, today: pendulum.DateTime) -> list[dict]` — unchanged signature, new behavior. Task 2 validates the `year` field this task reads.

- [ ] **Step 1: Write the failing tests**

Add these methods inside the existing `class TestCelebrations` in
`tests/test_features.py` (it starts at line 1503 and already has a
`_display()` helper that returns an uninitialized instance):

```python
    def test_year_pinned_entry_matches_in_its_year(self) -> None:
        display = self._display()
        config = {'celebrations': [
            {'date': '07-09', 'name': 'RYAN', 'type': 'birthday',
             'year': 2027},
        ]}
        matches = display._todays_celebrations(
            config, pendulum.datetime(2027, 7, 9))
        assert len(matches) == 1 and matches[0]['name'] == 'RYAN'

    def test_year_pinned_entry_skipped_in_other_years(self) -> None:
        display = self._display()
        config = {'celebrations': [
            {'date': '07-09', 'name': 'RYAN', 'type': 'birthday',
             'year': 2027},
        ]}
        # Both before and after the pinned year: a one-off fires once.
        assert display._todays_celebrations(
            config, pendulum.datetime(2026, 7, 9)) == []
        assert display._todays_celebrations(
            config, pendulum.datetime(2028, 7, 9)) == []

    def test_unpinned_entry_matches_every_year(self) -> None:
        display = self._display()
        config = {'celebrations': [
            {'date': '07-09', 'name': 'RYAN', 'type': 'birthday'},
        ]}
        for year in (2026, 2027, 2030):
            assert len(display._todays_celebrations(
                config, pendulum.datetime(year, 7, 9))) == 1

    def test_unparseable_year_is_skipped_not_fired(self) -> None:
        # config.json can be hand-edited, bypassing admin validation. A
        # garbage year must not fall back to "annual" and fire forever.
        display = self._display()
        config = {'celebrations': [
            {'date': '07-09', 'name': 'RYAN', 'type': 'birthday',
             'year': 'soon'},
        ]}
        assert display._todays_celebrations(
            config, pendulum.datetime(2027, 7, 9)) == []

    def test_string_year_still_matches(self) -> None:
        # JSON hand-edits routinely quote numbers; "2027" means 2027.
        display = self._display()
        config = {'celebrations': [
            {'date': '07-09', 'name': 'RYAN', 'type': 'birthday',
             'year': '2027'},
        ]}
        assert len(display._todays_celebrations(
            config, pendulum.datetime(2027, 7, 9))) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_features.py::TestCelebrations -v`

Expected: the three year-related tests FAIL. `test_year_pinned_entry_skipped_in_other_years`
and `test_unparseable_year_is_skipped_not_fired` fail because the current
code ignores `year` entirely and returns the entry.
`test_unpinned_entry_matches_every_year` and `test_string_year_still_matches`
may already pass — that is fine and expected, they are regression guards.

- [ ] **Step 3: Implement the year check**

Replace `_todays_celebrations` (`celebration_display.py:28-39`) with:

```python
    @staticmethod
    def _todays_celebrations(
        config: dict[str, Any], today: pendulum.DateTime
    ) -> list[dict[str, Any]]:
        """Entries from config whose MM-DD date matches today

        An entry may pin a `year`, which makes it one-off: it fires in that
        year and never again. No `year` means annual.
        """
        key = today.format('MM-DD')
        matches = []
        for entry in config.get('celebrations', []):
            if not isinstance(entry, dict) or entry.get('date') != key \
                    or not entry.get('name'):
                continue
            year = entry.get('year')
            if year is not None:
                try:
                    if int(year) != today.year:
                        continue
                except (TypeError, ValueError):
                    # config.json is hand-editable, so a garbage year gets
                    # here. Skipping is safer than treating it as annual and
                    # firing every year forever.
                    continue
            matches.append(entry)
        return matches
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_features.py::TestCelebrations -v`
Expected: PASS, all of them, including the two pre-existing tests
(`test_matches_todays_celebrations`, `test_ignores_malformed_entries`).

- [ ] **Step 5: Commit**

```bash
git add celebration_display.py tests/test_features.py
git commit -m "Let an important date pin a year so it fires once"
```

---

### Task 2: Server-side validation of the celebrations list

**Files:**
- Modify: `wifi_config_server.py` — add `import datetime`; add `_validate_celebrations` next to `_clamp_brightness` (line 2352); add `'celebrations': []` to `DEFAULT_CONFIG` (line ~231); add `'celebrations'` to `APPLIES_LIVE_KEYS` (line ~168); add the coercion to `save_config_route` (line ~2394)
- Test: `tests/test_admin_config.py`

**Interfaces:**
- Consumes: the entry shape Task 1 reads, including optional `year`.
- Produces: `_validate_celebrations(raw, default) -> list[dict]`. Returns a cleaned list, or `default` when `raw` is not a list. Task 3's JS posts the array this function validates.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_config.py` (it already defines the `client`
fixture at line 8 — reuse it, do not redefine it):

```python
class TestCelebrationValidation:
    def _validate(self, raw, default=None):
        import wifi_config_server as wcs
        return wcs._validate_celebrations(raw, default if default is not None else [])

    def test_keeps_a_well_formed_entry(self):
        entry = {'date': '07-09', 'name': 'RYAN', 'type': 'birthday'}
        assert self._validate([entry]) == [entry]

    def test_non_list_falls_back_to_default(self):
        prior = [{'date': '07-09', 'name': 'RYAN', 'type': 'birthday'}]
        # A request that omits the key sends None; the saved list must survive.
        assert self._validate(None, prior) == prior
        assert self._validate('nope', prior) == prior

    def test_drops_non_dict_and_malformed_dates(self):
        assert self._validate(['nope', {'name': 'NO DATE'}]) == []
        assert self._validate([{'date': '7-9', 'name': 'X'}]) == []
        assert self._validate([{'date': 'bogus', 'name': 'X'}]) == []

    def test_rejects_impossible_calendar_dates(self):
        assert self._validate([{'date': '02-30', 'name': 'X'}]) == []
        assert self._validate([{'date': '13-01', 'name': 'X'}]) == []

    def test_allows_leap_day(self):
        # 02-29 is legal; it simply only fires in leap years.
        assert len(self._validate([{'date': '02-29', 'name': 'X'}])) == 1

    def test_requires_a_name(self):
        assert self._validate([{'date': '07-09', 'name': '   '}]) == []

    def test_defaults_missing_type_to_birthday(self):
        out = self._validate([{'date': '07-09', 'name': 'RYAN'}])
        assert out[0]['type'] == 'birthday'

    def test_coerces_and_range_checks_year(self):
        out = self._validate(
            [{'date': '07-09', 'name': 'RYAN', 'year': '2027'}])
        assert out[0]['year'] == 2027
        assert self._validate(
            [{'date': '07-09', 'name': 'RYAN', 'year': 1899}]) == []
        assert self._validate(
            [{'date': '07-09', 'name': 'RYAN', 'year': 'soon'}]) == []

    def test_blank_year_means_annual(self):
        out = self._validate([{'date': '07-09', 'name': 'RYAN', 'year': ''}])
        assert 'year' not in out[0]


class TestCelebrationsRoundTrip:
    def test_save_config_round_trips_celebrations(self, client, tmp_path):
        entry = {'date': '12-25', 'name': 'CHRISTMAS', 'type': 'holiday'}
        assert client.post(
            '/save_config', json={'celebrations': [entry]}).get_json()['success']
        saved = json.loads((tmp_path / 'config.json').read_text())
        assert saved['celebrations'] == [entry]

    def test_omitting_celebrations_keeps_saved_dates(self, client, tmp_path):
        entry = {'date': '12-25', 'name': 'CHRISTMAS', 'type': 'holiday'}
        client.post('/save_config', json={'celebrations': [entry]})
        # A save that only touches an unrelated field must not wipe the list.
        client.post('/save_config', json={'enable_bears': False})
        saved = json.loads((tmp_path / 'config.json').read_text())
        assert saved['celebrations'] == [entry]

    def test_celebrations_apply_live(self, client):
        body = client.post(
            '/save_config',
            json={'celebrations': [
                {'date': '12-25', 'name': 'CHRISTMAS', 'type': 'holiday'}]}
        ).get_json()
        assert body['reboot_required'] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_admin_config.py -v`
Expected: FAIL with `AttributeError: module 'wifi_config_server' has no
attribute '_validate_celebrations'`, and the round-trip tests fail because
`celebrations` is not yet in `DEFAULT_CONFIG`.

- [ ] **Step 3: Add the import**

At the top of `wifi_config_server.py`, after `import re` (line 12):

```python
import datetime
```

- [ ] **Step 4: Add the validator**

Insert immediately after `_clamp_brightness` ends (before the
`@app.route('/save_config', ...)` decorator at line ~2367):

```python
def _validate_celebrations(raw, default):
    """Return a cleaned celebrations list, or the default if unusable.

    /save_config copies request JSON straight into config.json, and
    celebration_display reads that file on the display thread. A malformed
    entry landing there is a screen that fails to come up on someone's
    birthday, so the cleaning happens here rather than at render time.
    """
    if not isinstance(raw, list):
        return default

    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        date = str(entry.get('date', '')).strip()
        if not re.fullmatch(r'\d{2}-\d{2}', date):
            continue
        try:
            # 2024 is a leap year, so 02-29 validates here and stays
            # available; it simply only ever matches in a leap year.
            datetime.date(2024, int(date[:2]), int(date[3:]))
        except ValueError:
            continue

        name = str(entry.get('name', '')).strip()
        if not name:
            continue

        cleaned_entry = {
            'date': date,
            'name': name,
            'type': str(entry.get('type', '') or 'birthday').strip()
                    or 'birthday',
        }

        year = entry.get('year')
        if year not in (None, ''):
            try:
                year = int(year)
            except (TypeError, ValueError):
                continue
            if not 2000 <= year <= 2100:
                continue
            cleaned_entry['year'] = year

        cleaned.append(cleaned_entry)

    return cleaned
```

- [ ] **Step 5: Register the config key**

In `APPLIES_LIVE_KEYS` (line ~168), add `'celebrations'` to the set — put
it next to `'enable_celebrations'`:

```python
    'enable_cubs_history', 'enable_sky', 'enable_iss', 'enable_celebrations',
    'celebrations',
```

In `DEFAULT_CONFIG` (line ~231), add directly below `'enable_celebrations'`:

```python
        'celebrations': [],
```

- [ ] **Step 6: Wire the validator into the save route**

In `save_config_route`, inside the second `current_config.update({...})`
block (the coercion block starting at line ~2393), add one entry:

```python
            'celebrations': _validate_celebrations(
                data.get('celebrations'),
                previous_config.get('celebrations', [])),
```

This follows the block's existing rule: fall back to `previous_config`,
not `current_config`, because the passthrough above has already copied the
incoming value in and validating against `current_config` would let a bad
value validate against itself.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/test_admin_config.py tests/test_reboot_prompt.py -v`
Expected: PASS. `test_every_default_key_is_classified` in particular
confirms `celebrations` got classified rather than silently defaulting.

- [ ] **Step 8: Commit**

```bash
git add wifi_config_server.py tests/test_admin_config.py
git commit -m "Validate the celebrations list on the way into config.json"
```

---

### Task 3: Important Dates editor in the admin page

**Files:**
- Modify: `wifi_config_server.py` — CSS in the `<style>` block (line 307); HTML after the `enable_celebrations` form-group (line ~1005); JS helpers, the config-load call (line ~1382), and the save payload (line ~1649)
- Test: `tests/test_admin_config.py`

**Interfaces:**
- Consumes: `_validate_celebrations` from Task 2; the entry shape from Task 1.
- Produces: the admin page posts `celebrations: [...]` in the `/save_config` body. No Python API.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_admin_config.py`:

```python
def test_admin_page_has_the_important_dates_editor(client):
    html = client.get('/admin').data.decode()
    assert 'id="celebrations_rows"' in html
    assert 'id="add_celebration"' in html
    # The type dropdown must offer the renderer's special-cased value.
    assert 'holiday' in html
    # The 16-char ceiling has to be enforced in the preview, not just hoped for.
    assert 'cel-overflow' in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_admin_config.py::test_admin_page_has_the_important_dates_editor -v`
Expected: FAIL — `assert 'id="celebrations_rows"' in html`.

- [ ] **Step 3: Add the CSS**

Inside the existing `<style>` block (opens at line 307), append before
`</style>`:

```css
        .celebration-row {
            display: flex; flex-wrap: wrap; gap: 6px;
            align-items: center; margin-bottom: 8px;
        }
        .celebration-row input, .celebration-row select { width: auto; }
        .celebration-row .cel-name { flex: 1 1 120px; }
        .celebration-row .cel-year { width: 100px; }
        .cel-preview {
            flex: 1 1 100%; font-family: monospace; font-size: 11px;
            opacity: 0.8;
        }
        .cel-preview span { display: block; }
        .cel-overflow { color: #ff6b6b; font-weight: bold; }
        .cel-expired { opacity: 0.5; }
        .cel-expired .cel-name { text-decoration: line-through; }
```

- [ ] **Step 4: Add the HTML**

Directly after the `enable_celebrations` form-group closes
(`wifi_config_server.py:~1004-1009`, the `</div>` following the
"Enable celebration days display" label), insert:

```html
                        <div class="form-group">
                            <label>Important Dates</label>
                            <p style="font-size:12px;opacity:0.7;margin:4px 0;">
                                Shown on the celebration screen. The panel font
                                fits 16 characters per line &mdash; longer lines
                                turn red below. Leave Year blank to repeat every
                                year.
                            </p>
                            <div id="celebrations_rows"></div>
                            <button type="button" id="add_celebration">+ Add date</button>
                        </div>
```

- [ ] **Step 5: Add the JavaScript**

In the page's `<script>` block, alongside the other helper functions, add:

```javascript
        const CELEBRATION_TYPES = ['birthday', 'anniversary', 'holiday'];
        const CELEBRATION_MONTHS = [
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

        function celebrationRowEntry(row) {
            const typeSel = row.querySelector('.cel-type');
            const type = typeSel.value === '__custom__'
                ? row.querySelector('.cel-type-custom').value.trim()
                : typeSel.value;
            const year = row.querySelector('.cel-year').value.trim();
            const entry = {
                date: row.querySelector('.cel-month').value + '-'
                    + row.querySelector('.cel-day').value,
                name: row.querySelector('.cel-name').value.trim(),
                type: type || 'birthday'
            };
            if (year) { entry.year = parseInt(year, 10); }
            return entry;
        }

        function celebrationPreviewLines(entry) {
            // Mirrors _draw_celebration_frame: HAPPY / TYPE / NAME!, with the
            // type line dropped entirely for holidays.
            const lines = ['HAPPY'];
            if (entry.type !== 'holiday') {
                lines.push((entry.type || '').toUpperCase());
            }
            lines.push((entry.name || '') + '!');
            return lines.filter(function (l) { return l && l !== '!'; });
        }

        function updateCelebrationRow(row) {
            const entry = celebrationRowEntry(row);
            const box = row.querySelector('.cel-preview');
            box.innerHTML = '';
            celebrationPreviewLines(entry).forEach(function (line) {
                const el = document.createElement('span');
                el.textContent = line;
                // 96px panel / 6px per small_bold character = 16.
                if (line.length > 16) { el.className = 'cel-overflow'; }
                box.appendChild(el);
            });
            const expired = entry.year && entry.year < new Date().getFullYear();
            row.classList.toggle('cel-expired', !!expired);
        }

        function celebrationRow(entry) {
            entry = entry || {};
            const row = document.createElement('div');
            row.className = 'celebration-row';
            const mm = (entry.date || '').slice(0, 2);
            const dd = (entry.date || '').slice(3, 5);

            const monthSel = document.createElement('select');
            monthSel.className = 'cel-month';
            CELEBRATION_MONTHS.forEach(function (label, i) {
                const n = String(i + 1).padStart(2, '0');
                monthSel.add(new Option(label, n, false, n === mm));
            });

            const daySel = document.createElement('select');
            daySel.className = 'cel-day';
            for (let d = 1; d <= 31; d++) {
                const n = String(d).padStart(2, '0');
                daySel.add(new Option(n, n, false, n === dd));
            }

            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.className = 'cel-name';
            nameInput.placeholder = 'NAME';
            nameInput.value = entry.name || '';

            const isCustom = !!entry.type
                && CELEBRATION_TYPES.indexOf(entry.type) === -1;

            const typeSel = document.createElement('select');
            typeSel.className = 'cel-type';
            CELEBRATION_TYPES.forEach(function (t) {
                typeSel.add(new Option(
                    t, t, false, !isCustom && t === (entry.type || 'birthday')));
            });
            typeSel.add(new Option('custom...', '__custom__', false, isCustom));

            const customInput = document.createElement('input');
            customInput.type = 'text';
            customInput.className = 'cel-type-custom';
            customInput.placeholder = 'TYPE';
            customInput.value = isCustom ? entry.type : '';
            customInput.style.display = isCustom ? '' : 'none';

            const yearInput = document.createElement('input');
            yearInput.type = 'number';
            yearInput.className = 'cel-year';
            yearInput.placeholder = 'every year';
            yearInput.min = 2000;
            yearInput.max = 2100;
            yearInput.value = entry.year || '';

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.textContent = 'Remove';
            removeBtn.onclick = function () { row.remove(); };

            const preview = document.createElement('div');
            preview.className = 'cel-preview';

            typeSel.onchange = function () {
                customInput.style.display =
                    typeSel.value === '__custom__' ? '' : 'none';
                updateCelebrationRow(row);
            };
            [monthSel, daySel, nameInput, customInput, yearInput].forEach(
                function (el) {
                    el.addEventListener('input', function () {
                        updateCelebrationRow(row);
                    });
                });

            row.append(monthSel, daySel, nameInput, typeSel, customInput,
                       yearInput, removeBtn, preview);
            updateCelebrationRow(row);
            return row;
        }

        function renderCelebrations(list) {
            const container = document.getElementById('celebrations_rows');
            container.innerHTML = '';
            (list || []).forEach(function (entry) {
                container.appendChild(celebrationRow(entry));
            });
        }

        function collectCelebrations() {
            return Array.from(document.querySelectorAll(
                '#celebrations_rows .celebration-row'))
                .map(celebrationRowEntry)
                .filter(function (e) { return e.name; });
        }
```

Leave these as top-level functions in the `<script>` block (which opens at
line 1272 and closes at 1945). The button handler is registered in Step 6
instead — this page wires every handler inside `window.onload` (line 1311),
and top-level registration would be inconsistent with the rest of the file.

- [ ] **Step 6: Load and save the list**

Inside `window.onload` (opens at line 1311), next to the
`enable_celebrations` line (~1382), add both the render call and the button
handler. `config` there is server-rendered by Jinja as
`{{ config | tojson }}` at line 1312 — there is no fetch to await:

```javascript
            renderCelebrations(config.celebrations);
            document.getElementById('add_celebration').onclick = function () {
                document.getElementById('celebrations_rows')
                    .appendChild(celebrationRow({type: 'birthday'}));
            };
```

In the save payload object, next to the `enable_celebrations` line
(~1649), add:

```javascript
                celebrations: collectCelebrations(),
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/ -v`
Expected: PASS, whole suite. The admin page is a Python string, so a JS
syntax error shows up as a failing assertion here only if it breaks the
HTML — see Step 8 for the check that actually catches JS mistakes.

- [ ] **Step 8: Verify the editor in a browser**

The admin template is a large inline string with no build step, so nothing
in pytest parses the JavaScript. Check it by hand:

```bash
python3 -c "import wifi_config_server" && echo "imports clean"
sudo python3 wifi_config_server.py
```

Open `http://localhost/admin`, expand the display-options section, and
confirm: "+ Add date" adds a row; typing a long name turns the preview
line red past 16 characters; choosing "holiday" drops the TYPE line from
the preview; a past year greys the row out; Save then reload brings the
rows back.

The server binds port 80 (`app.run(...)`, line 2640), hence `sudo`. If that
port is busy, edit the port in that call and revert before committing.

Alternatively, dump the rendered page without running a server:

```bash
python3 -c "
import wifi_config_server as w
w.app.config['TESTING'] = True
open('/tmp/admin.html','w').write(
    w.app.test_client().get('/admin').data.decode())
" && open /tmp/admin.html
```

The page's Save button posts to a server that is not there, so use this for
checking the editor's behavior, not the round-trip.

- [ ] **Step 9: Commit**

```bash
git add wifi_config_server.py tests/test_admin_config.py
git commit -m "Add an Important Dates editor to the admin page"
```

---

### Task 4: Document the feature

**Files:**
- Modify: `CLAUDE.md` (the "Configuration" section, the bullet list of `/home/pi/config.json` keys)

**Interfaces:**
- Consumes: the final entry shape from Tasks 1-3.
- Produces: nothing consumed by code.

- [ ] **Step 1: Add the config key documentation**

In `CLAUDE.md`, in the `/home/pi/config.json` bullet list (alongside
`team`, `nfl_team`, `nfl_preempt_mlb`, `panel_version`), add:

```markdown
- `celebrations` — important dates shown on the celebration screen, edited
  from the admin page. Each entry is `{"date": "MM-DD", "name": "RYAN",
  "type": "birthday"}` with an optional `"year": 2027` that makes it
  one-off instead of annual. `type: "holiday"` drops the type line, giving
  `HAPPY` / `THANKSGIVING!`. The panel fits **16 characters per line**
  (`small_bold` at 6px on a 96px panel), so long names overflow — the admin
  preview flags this. Validated in `_validate_celebrations` on save because
  `celebration_display` reads config.json on the display thread
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the celebrations config key"
```

---

## Done When

- [ ] `pytest tests/ -v` passes with no failures
- [ ] A date added in the admin page appears in `/home/pi/config.json`
- [ ] A date whose `year` is this year fires; last year's does not
- [ ] A save that omits `celebrations` leaves saved dates untouched
- [ ] The 16-character overflow warning appears while typing
