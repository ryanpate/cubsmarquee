# Remote Message Posting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let someone outside the house put a message on a marquee by
visiting a private URL, without exposing the Pi to the internet.

**Architecture:** A Cloudflare Worker holds the current message per board
in KV. Each Pi polls it on a daemon thread and caches the result to a local
file; the rotation shows a new message once at the next segment boundary,
then keeps it in the custom-message slot until it is replaced or cleared.
The Worker is the source of truth; the cache exists so a network outage
does not blank the board.

**Tech Stack:** Cloudflare Workers + KV, wrangler, vitest with
`@cloudflare/vitest-pool-workers` (Worker side). Python 3.9+, `requests`,
Flask, pytest (Pi side). Node 22.17.0 and npm 10.9.2 are installed;
wrangler is not, and is added as a pinned devDependency.

**Spec:** `docs/superpowers/specs/2026-08-20-remote-message-and-important-dates-design.md`
(Part 1, plus the "Not doing" section)

## Global Constraints

- **The Pi never accepts inbound connections.** All traffic is the Pi
  polling out. The admin panel has no authentication and can reboot the Pi
  and rewrite WiFi credentials; it stays LAN-only.
- **Message cap: 200 characters, rejected not truncated**, with the count
  shown on the form.
- **Text is folded to latin-1** before storage, matching `to_bitmap_text`
  (`scoreboard_manager.py:44`). Substitutions are one character wide —
  tickers place each character at `index * char_width`, so a longer
  replacement would shift the scroll. Emoji become `?`.
- **`id` is a fresh `crypto.randomUUID()` on every post.** The Pi keys
  "already shown" off `id`, never off text, so re-posting identical text
  fires again.
- **The poller writes `/home/pi/remote_message.json`, never config.json.**
  `/save_config` does read-modify-write on config.json; a poller racing it
  would silently drop a settings edit.
- **The poller catches every exception.** It must never raise into the
  display loop.
- **Never commit secrets.** Board tokens live in `/home/pi/config.json`,
  which is untracked but currently *not* gitignored — Task 1 fixes that.
- **Every new config key must be classified** in `REBOOT_REQUIRED_KEYS` or
  `APPLIES_LIVE_KEYS`, or `tests/test_reboot_prompt.py` fails.
- Python suite: `pytest tests/ -v` from the repo root. Worker suite:
  `npm test` from `workers/marquee-message/`.

---

### Task 1: Stop config.json from ever being committed

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by code. Must land before any task writes a token into config.json.

`config.json` is untracked but not ignored, so `git add -A` would commit
it. It already holds `weather_api_key` and `airlabs_api_key`; this work
adds a board token, which makes the gap sharper.

- [ ] **Step 1: Confirm the gap is real**

```bash
git check-ignore -v config.json || echo "NOT ignored -- confirmed"
```

Expected: prints "NOT ignored -- confirmed".

- [ ] **Step 2: Add the ignore rules**

Append to `.gitignore`:

```gitignore
# User config -- holds API keys and per-board remote-message tokens
config.json
/home/pi/config.json
remote_message.json

# Cloudflare Worker
workers/*/node_modules/
workers/*/.wrangler/
.dev.vars
```

- [ ] **Step 3: Verify**

```bash
git check-ignore -v config.json && echo "now ignored"
git status --porcelain | grep -c config.json
```

Expected: "now ignored", and a count of `0`.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "Keep config.json and its API keys out of git"
```

---

### Task 2: Provision the Cloudflare KV namespace and generate board secrets

**Files:**
- Create: `workers/marquee-message/.dev.vars` (gitignored by Task 1)
- Create: `/private/tmp/claude-501/-Users-ryanpate-cubsmarquee/770c568b-d7fc-4991-8aed-ad8ee54bcaef/scratchpad/board-secrets.json` (scratchpad, never in the repo)

**Interfaces:**
- Consumes: nothing.
- Produces: a KV namespace id (used in `wrangler.jsonc`, Task 4) and a `BOARDS` JSON map of `{board: {pass, token}}` for three boards: `cubsmarquee`, `throckmarquee`, `cardsmarquee`.

The account is confirmed empty — zero KV namespaces, zero Workers — so
nothing here collides with existing resources.

- [ ] **Step 1: Create the KV namespace**

Use the Cloudflare MCP tool `kv_namespace_create` with
`title: "marquee-messages"`. It is already authenticated.

Record the returned `id` — `wrangler.jsonc` needs it in Task 4.

Verify with the `kv_namespaces_list` MCP tool: exactly one namespace named
`marquee-messages`.

- [ ] **Step 2: Generate the per-board secrets**

Each board gets its own passphrase (typed by a human on the posting page)
and its own device token (sent by the Pi). Separate values per board mean
handing out one board's link never grants the others.

```bash
SCRATCH="/private/tmp/claude-501/-Users-ryanpate-cubsmarquee/770c568b-d7fc-4991-8aed-ad8ee54bcaef/scratchpad"
mkdir -p "$SCRATCH"
python3 - <<'PY' > "$SCRATCH/board-secrets.json"
import json, secrets
words = ['maple','cedar','harbor','copper','lantern','meadow',
         'anchor','falcon','ember','willow','ridge','cobalt']
boards = {}
for board in ('cubsmarquee', 'throckmarquee', 'cardsmarquee'):
    # A passphrase someone can read over the phone; a token they never see.
    phrase = '-'.join(secrets.choice(words) for _ in range(3))
    boards[board] = {'pass': phrase, 'token': secrets.token_urlsafe(32)}
print(json.dumps(boards, indent=2))
PY
cat "$SCRATCH/board-secrets.json"
```

Expected: three boards, each with a hyphenated three-word `pass` and a
long random `token`.

- [ ] **Step 3: Write the local dev copy**

```bash
mkdir -p workers/marquee-message
SCRATCH="/private/tmp/claude-501/-Users-ryanpate-cubsmarquee/770c568b-d7fc-4991-8aed-ad8ee54bcaef/scratchpad"
printf 'BOARDS=%s\n' "$(python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1]))))' "$SCRATCH/board-secrets.json")" \
  > workers/marquee-message/.dev.vars
```

- [ ] **Step 4: Verify it cannot be committed**

```bash
git check-ignore -v workers/marquee-message/.dev.vars && echo "ignored, good"
```

Expected: prints the matching `.gitignore` rule then "ignored, good". If it
does not, stop and fix Task 1 before going further.

- [ ] **Step 5: No commit**

Nothing in this task is committable — that is the point. Do not
`git add` anything here.

---

### Task 3: Worker request handling, test-first

**Files:**
- Create: `workers/marquee-message/package.json`
- Create: `workers/marquee-message/src/text.js`
- Create: `workers/marquee-message/test/text.test.js`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `foldToPanelText(input: string) -> string` and `validateMessage(input: string) -> {ok: true, text: string} | {ok: false, error: string}`, both imported by `src/index.js` in Task 4.

Text normalization is split into its own module so it can be tested
without a Worker runtime, and so the fold stays a single definition that
both the Worker and its posting page use.

- [ ] **Step 1: Create the package**

`workers/marquee-message/package.json`:

```json
{
  "name": "marquee-message",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "dev": "wrangler dev",
    "deploy": "wrangler deploy"
  },
  "devDependencies": {
    "@cloudflare/vitest-pool-workers": "^0.5.2",
    "vitest": "~2.0.5",
    "wrangler": "^3.78.0"
  }
}
```

`vitest` is pinned to ~2.0.x because `@cloudflare/vitest-pool-workers`
requires that range; a newer vitest fails to start the pool. If npm reports
a peer-dependency conflict, take the versions npm asks for rather than
forcing these — the pin is a starting point, not a requirement.

There is deliberately **no** `vitest.config.js` yet. `text.js` is pure
JavaScript with no Worker runtime needed, and the Workers pool config must
point at a `wrangler.jsonc` that does not exist until Task 4 — adding it
now would stop this task's own tests from starting. Task 4 adds both
together.

```bash
cd workers/marquee-message && npm install
```

- [ ] **Step 2: Write the failing tests**

`workers/marquee-message/test/text.test.js`:

```javascript
import { describe, it, expect } from 'vitest';
import { foldToPanelText, validateMessage } from '../src/text.js';

describe('foldToPanelText', () => {
  it('folds typographic punctuation to ASCII', () => {
    expect(foldToPanelText('‘a’ “b”')).toBe("'a' \"b\"");
    expect(foldToPanelText('a—b')).toBe('a-b');
    expect(foldToPanelText('wait…')).toBe('wait.');
  });

  it('keeps substitutions one character wide', () => {
    // Tickers place each character at index * char_width, so a
    // replacement that grew would shift the whole scroll.
    for (const ch of ['‘', '’', '“', '”', '—',
                      '…', '•']) {
      expect(foldToPanelText(ch)).toHaveLength(1);
    }
  });

  it('replaces anything above latin-1 with a question mark', () => {
    // One '?' per code point, matching Python's per-character loop. An
    // emoji is two UTF-16 units but one character to Python, so counting
    // units here would put a second '?' on the panel that the Pi's own
    // fold would never produce.
    expect(foldToPanelText('hi \u{1F389}')).toBe('hi ?');
  });

  it('leaves plain ASCII alone', () => {
    expect(foldToPanelText('HAPPY BIRTHDAY')).toBe('HAPPY BIRTHDAY');
  });
});

describe('validateMessage', () => {
  it('accepts and folds a normal message', () => {
    const out = validateMessage('  Grandpa’s   birthday!  ');
    expect(out.ok).toBe(true);
    expect(out.text).toBe("Grandpa's birthday!");
  });

  it('rejects empty and whitespace-only input', () => {
    expect(validateMessage('').ok).toBe(false);
    expect(validateMessage('    ').ok).toBe(false);
  });

  it('rejects over 200 characters rather than truncating', () => {
    const out = validateMessage('x'.repeat(201));
    expect(out.ok).toBe(false);
    expect(out.error).toMatch(/200/);
  });

  it('accepts exactly 200 characters', () => {
    expect(validateMessage('x'.repeat(200)).ok).toBe(true);
  });

  it('measures length after folding, not before', () => {
    // The panel sees what the fold produces, so that is what gets
    // measured -- 100 emoji fold to 100 characters, not 200.
    const out = validateMessage('\u{1F389}'.repeat(100));
    expect(out.ok).toBe(true);
    expect(out.text).toBe('?'.repeat(100));
  });

  it('rejects non-string input', () => {
    expect(validateMessage(undefined).ok).toBe(false);
    expect(validateMessage(42).ok).toBe(false);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd workers/marquee-message && npm test
```

Expected: FAIL — cannot resolve `../src/text.js`.

- [ ] **Step 4: Implement the module**

`workers/marquee-message/src/text.js`:

```javascript
// Mirrors _BITMAP_TEXT_MAP / to_bitmap_text in scoreboard_manager.py:36-49.
// The BDF fonts are latin-1 only and PIL raises UnicodeEncodeError above
// U+00FF, so fold before storing. Every substitution is one character
// wide: the tickers place each character at index * char_width, and a
// wider replacement would shift the scroll.
const FOLD = {
  '‘': "'", '’': "'", '‚': "'", '‛': "'",
  '′': "'", '“': '"', '”': '"', '„': '"',
  '″': '"', '–': '-', '—': '-', '―': '-',
  '−': '-', '…': '.', '•': '*',
};

export const MAX_MESSAGE_CHARS = 200;

export function foldToPanelText(text) {
  let out = '';
  for (const ch of String(text)) {
    const mapped = FOLD[ch];
    if (mapped !== undefined) {
      out += mapped;
    } else if (ch.codePointAt(0) < 256) {
      out += ch;
    } else {
      // One '?' per code point. The for..of loop yields whole code points,
      // so an emoji contributes a single '?' -- which is what Python's
      // per-character fold produces for the same input.
      out += '?';
    }
  }
  return out;
}

export function validateMessage(raw) {
  if (typeof raw !== 'string') {
    return { ok: false, error: 'Message must be text.' };
  }
  const text = foldToPanelText(raw).replace(/\s+/g, ' ').trim();
  if (!text) {
    return { ok: false, error: 'Message is empty.' };
  }
  if (text.length > MAX_MESSAGE_CHARS) {
    return {
      ok: false,
      error: `Message is ${text.length} characters; the limit is `
             + `${MAX_MESSAGE_CHARS}. Please shorten it.`,
    };
  }
  return { ok: true, text };
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd workers/marquee-message && npm test
```

Expected: PASS, all cases.

- [ ] **Step 6: Commit**

```bash
git add workers/marquee-message/package.json \
        workers/marquee-message/package-lock.json \
        workers/marquee-message/src/text.js \
        workers/marquee-message/test/text.test.js
git commit -m "Fold remote message text to what the panel font can draw"
```

---

### Task 4: Worker routes and auth

**Files:**
- Create: `workers/marquee-message/wrangler.jsonc`
- Create: `workers/marquee-message/vitest.config.js`
- Create: `workers/marquee-message/src/index.js`
- Create: `workers/marquee-message/src/page.js`
- Create: `workers/marquee-message/test/worker.test.js`

**Interfaces:**
- Consumes: `foldToPanelText`, `validateMessage`, `MAX_MESSAGE_CHARS` from Task 3.
- Produces: the HTTP contract the Pi poller in Task 6 depends on — `GET /api/b/<board>` returns `200 {text, id, updated_at}` when set, `204` when cleared, `401` on a bad token.

- [ ] **Step 1: Write wrangler.jsonc**

Substitute the KV id recorded in Task 2 Step 1 for `<KV_NAMESPACE_ID>`:

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "marquee-message",
  "main": "src/index.js",
  "compatibility_date": "2026-08-01",
  "observability": { "enabled": true },
  "kv_namespaces": [
    { "binding": "MESSAGES", "id": "<KV_NAMESPACE_ID>" }
  ]
}
```

The `BOARDS` secret is not listed here — secrets never live in config.
It is set in Task 5.

Now add `workers/marquee-message/vitest.config.js`, which needs the file
above to exist:

```javascript
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.jsonc' },
      },
    },
  },
});
```

`test/text.test.js` from Task 3 now runs under the Workers pool too. It is
pure JavaScript, so it passes there unchanged.

- [ ] **Step 2: Write the failing tests**

`workers/marquee-message/test/worker.test.js`:

```javascript
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';

const BOARDS = {
  cubsmarquee: { pass: 'open-sesame', token: 'device-token-1' },
  cardsmarquee: { pass: 'other-phrase', token: 'device-token-2' },
};

beforeEach(async () => {
  env.BOARDS = JSON.stringify(BOARDS);
  await env.MESSAGES.delete('msg:cubsmarquee');
  await env.MESSAGES.delete('msg:cardsmarquee');
});

function post(board, pass, message) {
  return SELF.fetch(`https://x/b/${board}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ pass, message }),
  });
}

function poll(board, token) {
  return SELF.fetch(`https://x/api/b/${board}`, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
}

describe('posting page', () => {
  it('serves a form for a known board', async () => {
    const res = await SELF.fetch('https://x/b/cubsmarquee');
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('<form');
  });

  it('404s an unknown board', async () => {
    expect((await SELF.fetch('https://x/b/nope')).status).toBe(404);
  });
});

describe('POST auth', () => {
  it('rejects a wrong passphrase and leaves KV untouched', async () => {
    const res = await post('cubsmarquee', 'wrong', 'HELLO');
    expect(res.status).toBe(401);
    expect(await env.MESSAGES.get('msg:cubsmarquee')).toBeNull();
  });

  it("rejects another board's passphrase", async () => {
    const res = await post('cubsmarquee', BOARDS.cardsmarquee.pass, 'HELLO');
    expect(res.status).toBe(401);
  });

  it('accepts the right passphrase and stores folded text', async () => {
    const res = await post('cubsmarquee', BOARDS.cubsmarquee.pass,
                           'Grandpa’s day');
    expect(res.status).toBe(200);
    const stored = JSON.parse(await env.MESSAGES.get('msg:cubsmarquee'));
    expect(stored.text).toBe("Grandpa's day");
    expect(stored.id).toBeTruthy();
    expect(stored.updated_at).toBeGreaterThan(0);
  });

  it('rejects an over-long message with a 400', async () => {
    const res = await post('cubsmarquee', BOARDS.cubsmarquee.pass,
                           'x'.repeat(201));
    expect(res.status).toBe(400);
    expect(await env.MESSAGES.get('msg:cubsmarquee')).toBeNull();
  });

  it('gives identical text a fresh id each post', async () => {
    await post('cubsmarquee', BOARDS.cubsmarquee.pass, 'SAME');
    const first = JSON.parse(await env.MESSAGES.get('msg:cubsmarquee')).id;
    await post('cubsmarquee', BOARDS.cubsmarquee.pass, 'SAME');
    const second = JSON.parse(await env.MESSAGES.get('msg:cubsmarquee')).id;
    expect(second).not.toBe(first);
  });
});

describe('device polling', () => {
  it('401s without a token', async () => {
    expect((await poll('cubsmarquee', null)).status).toBe(401);
  });

  it("401s with another board's token", async () => {
    expect((await poll('cubsmarquee', BOARDS.cardsmarquee.token)).status)
      .toBe(401);
  });

  it('204s when nothing is set', async () => {
    expect((await poll('cubsmarquee', BOARDS.cubsmarquee.token)).status)
      .toBe(204);
  });

  it('returns the stored message', async () => {
    await post('cubsmarquee', BOARDS.cubsmarquee.pass, 'HELLO');
    const res = await poll('cubsmarquee', BOARDS.cubsmarquee.token);
    expect(res.status).toBe(200);
    expect((await res.json()).text).toBe('HELLO');
  });

  it('keeps boards isolated', async () => {
    await post('cubsmarquee', BOARDS.cubsmarquee.pass, 'CUBS');
    expect((await poll('cardsmarquee', BOARDS.cardsmarquee.token)).status)
      .toBe(204);
  });
});

describe('clearing', () => {
  it('401s without a token', async () => {
    const res = await SELF.fetch('https://x/api/b/cubsmarquee',
                                 { method: 'DELETE' });
    expect(res.status).toBe(401);
  });

  it('clears with a token, and the next poll is empty', async () => {
    await post('cubsmarquee', BOARDS.cubsmarquee.pass, 'HELLO');
    const res = await SELF.fetch('https://x/api/b/cubsmarquee', {
      method: 'DELETE',
      headers: { authorization: `Bearer ${BOARDS.cubsmarquee.token}` },
    });
    expect(res.status).toBe(200);
    expect((await poll('cubsmarquee', BOARDS.cubsmarquee.token)).status)
      .toBe(204);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd workers/marquee-message && npm test
```

Expected: FAIL — no `src/index.js`.

- [ ] **Step 4: Write the posting page**

`workers/marquee-message/src/page.js`:

```javascript
import { MAX_MESSAGE_CHARS } from './text.js';

// The fold table is duplicated into the browser deliberately: the preview
// must show exactly what the Worker will store, and the page cannot import
// a module the Worker bundles server-side.
export function postingPage(board) {
  return `<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Message the ${board} marquee</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:34rem;margin:2rem auto;
      padding:0 1rem;background:#0b1220;color:#eef}
 textarea,input{width:100%;font-size:1rem;padding:.6rem;border-radius:.4rem;
      border:1px solid #456;background:#111c2e;color:#eef}
 textarea{height:6rem}
 button{margin-top:1rem;padding:.7rem 1.4rem;font-size:1rem;border:0;
      border-radius:.4rem;background:#0053a0;color:#fff}
 .preview{margin-top:1rem;padding:.6rem;background:#000;color:#ffdf00;
      font-family:ui-monospace,monospace;word-break:break-all;border-radius:.4rem}
 .count{font-size:.85rem;opacity:.75}
 .over{color:#ff6b6b;font-weight:bold}
 .msg{margin-top:1rem;padding:.6rem;border-radius:.4rem}
 .ok{background:#12381e}.err{background:#3a1520}
</style></head><body>
<h1>${board}</h1>
<form id="f">
 <label>Message<textarea id="m" maxlength="400" autofocus></textarea></label>
 <div class="count"><span id="c">0</span> / ${MAX_MESSAGE_CHARS}</div>
 <div class="preview" id="p"></div>
 <label>Passphrase<input id="k" type="password" autocomplete="current-password"></label>
 <button type="submit">Send to the marquee</button>
</form>
<div id="out"></div>
<script>
const FOLD={'\\u2018':"'",'\\u2019':"'",'\\u201a':"'",'\\u201b':"'",
 '\\u2032':"'",'\\u201c':'"','\\u201d':'"','\\u201e':'"','\\u2033':'"',
 '\\u2013':'-','\\u2014':'-','\\u2015':'-','\\u2212':'-','\\u2026':'.',
 '\\u2022':'*'};
function fold(t){let o='';for(const ch of String(t)){const m=FOLD[ch];
 if(m!==undefined)o+=m;else if(ch.codePointAt(0)<256)o+=ch;
 else o+='?'.repeat(ch.length);}return o;}
const m=document.getElementById('m'),p=document.getElementById('p'),
      c=document.getElementById('c');
function upd(){const t=fold(m.value).replace(/\\s+/g,' ').trim();
 p.textContent=t||'\\u2014';c.textContent=t.length;
 c.parentElement.className='count'+(t.length>${MAX_MESSAGE_CHARS}?' over':'');}
m.addEventListener('input',upd);upd();
document.getElementById('f').addEventListener('submit',async e=>{
 e.preventDefault();
 const r=await fetch(location.pathname,{method:'POST',
  headers:{'content-type':'application/json'},
  body:JSON.stringify({pass:document.getElementById('k').value,
                       message:m.value})});
 const b=await r.json().catch(()=>({}));
 const out=document.getElementById('out');
 out.className='msg '+(r.ok?'ok':'err');
 out.textContent=r.ok?'Sent. It reaches the board within a few minutes.'
                     :(b.error||'Could not send.');
 if(r.ok){m.value='';upd();}
});
</script></body></html>`;
}
```

- [ ] **Step 5: Write the Worker**

`workers/marquee-message/src/index.js`:

```javascript
import { validateMessage } from './text.js';
import { postingPage } from './page.js';

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

// Constant-time compare so a wrong passphrase leaks nothing through timing.
function secretsMatch(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const enc = new TextEncoder();
  const x = enc.encode(a);
  const y = enc.encode(b);
  if (x.length !== y.length) return false;
  return crypto.subtle.timingSafeEqual
    ? crypto.subtle.timingSafeEqual(x, y)
    : x.every((v, i) => v === y[i]);
}

function boardConfig(env, board) {
  try {
    return JSON.parse(env.BOARDS || '{}')[board] || null;
  } catch {
    return null;
  }
}

function bearer(request) {
  const header = request.headers.get('authorization') || '';
  return header.startsWith('Bearer ') ? header.slice(7) : '';
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const post = url.pathname.match(/^\/b\/([A-Za-z0-9_-]+)$/);
    const api = url.pathname.match(/^\/api\/b\/([A-Za-z0-9_-]+)$/);
    const board = (post || api)?.[1];
    if (!board) return new Response('Not found', { status: 404 });

    const cfg = boardConfig(env, board);
    // Unknown board is a 404 before any auth work: there is nothing to
    // compare against, and it is not a credential failure.
    if (!cfg) return new Response('Not found', { status: 404 });

    const key = `msg:${board}`;

    if (post && request.method === 'GET') {
      return new Response(postingPage(board), {
        headers: { 'content-type': 'text/html; charset=utf-8' },
      });
    }

    if (post && request.method === 'POST') {
      const body = await request.json().catch(() => ({}));
      if (!secretsMatch(body.pass, cfg.pass)) {
        return json({ error: 'Wrong passphrase.' }, 401);
      }
      const check = validateMessage(body.message);
      if (!check.ok) return json({ error: check.error }, 400);

      await env.MESSAGES.put(key, JSON.stringify({
        text: check.text,
        id: crypto.randomUUID(),
        updated_at: Math.floor(Date.now() / 1000),
      }));
      return json({ ok: true, text: check.text });
    }

    if (api) {
      if (!secretsMatch(bearer(request), cfg.token)) {
        return json({ error: 'Unauthorized' }, 401);
      }
      if (request.method === 'GET') {
        const stored = await env.MESSAGES.get(key);
        if (!stored) return new Response(null, { status: 204 });
        return new Response(stored, {
          headers: { 'content-type': 'application/json' },
        });
      }
      if (request.method === 'DELETE') {
        await env.MESSAGES.delete(key);
        return json({ ok: true });
      }
    }

    return new Response('Method not allowed', { status: 405 });
  },
};
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd workers/marquee-message && npm test
```

Expected: PASS, every describe block.

- [ ] **Step 7: Commit**

```bash
git add workers/marquee-message/wrangler.jsonc \
        workers/marquee-message/vitest.config.js \
        workers/marquee-message/src/index.js \
        workers/marquee-message/src/page.js \
        workers/marquee-message/test/worker.test.js
git commit -m "Add the marquee message Worker with per-board auth"
```

---

### Task 5: Deploy the Worker and set the BOARDS secret

**Files:**
- None committed. This task produces a deployed URL.

**Interfaces:**
- Consumes: the KV id and `BOARDS` map from Task 2; the Worker from Tasks 3-4.
- Produces: the live base URL `https://marquee-message.<subdomain>.workers.dev`, needed for `remote_message_url` in Task 8.

There is no MCP tool for deploying a Worker or setting a secret, so this
task uses the wrangler CLI. `wrangler login` is interactive.

- [ ] **Step 1: Authenticate wrangler**

This opens a browser and cannot be driven from a tool call. Ask the user to
run it in their session:

> Please run `! npx wrangler login` and approve the browser prompt.

Then confirm:

```bash
cd workers/marquee-message && npx wrangler whoami
```

Expected: the account email and id.

- [ ] **Step 2: Deploy**

```bash
cd workers/marquee-message && npx wrangler deploy
```

Expected: a published URL of the form
`https://marquee-message.<subdomain>.workers.dev`. Record it — the
subdomain is assigned by Cloudflare and is not knowable before this step.

- [ ] **Step 3: Set the BOARDS secret**

```bash
SCRATCH="/private/tmp/claude-501/-Users-ryanpate-cubsmarquee/770c568b-d7fc-4991-8aed-ad8ee54bcaef/scratchpad"
cd workers/marquee-message
python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1]))))' \
  "$SCRATCH/board-secrets.json" | npx wrangler secret put BOARDS
```

Expected: "Success! Uploaded secret BOARDS".

- [ ] **Step 4: Smoke-test the live deployment**

Replace `<URL>` with the deployed base URL and `<PASS>`/`<TOKEN>` with
`cubsmarquee`'s values from the scratchpad file:

```bash
# Wrong passphrase -> 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST '<URL>/b/cubsmarquee' \
  -H 'content-type: application/json' -d '{"pass":"nope","message":"hi"}'

# Right passphrase -> 200
curl -s -X POST '<URL>/b/cubsmarquee' -H 'content-type: application/json' \
  -d '{"pass":"<PASS>","message":"HELLO FROM CURL"}'

# Device poll -> the message
curl -s '<URL>/api/b/cubsmarquee' -H 'authorization: Bearer <TOKEN>'

# Clear -> then 204
curl -s -X DELETE '<URL>/api/b/cubsmarquee' -H 'authorization: Bearer <TOKEN>'
curl -s -o /dev/null -w '%{http_code}\n' '<URL>/api/b/cubsmarquee' \
  -H 'authorization: Bearer <TOKEN>'
```

Expected: `401`, then a JSON body with the folded text, then the stored
message, then `204`.

- [ ] **Step 5: No commit**

Nothing here is committable.

---

### Task 6: The Pi-side poller

**Files:**
- Create: `remote_message.py`
- Test: `tests/test_remote_message.py`

**Interfaces:**
- Consumes: the HTTP contract from Task 4.
- Produces:
  - `CACHE_PATH: str` — module constant, `/home/pi/remote_message.json`
  - `current_message() -> str | None`
  - `take_pending_takeover() -> str | None`
  - `poll_once(config: dict) -> None`
  - `start_poller() -> None`
  - `clear_local_cache() -> None`

  Task 7 calls `current_message` and `take_pending_takeover`; Task 8 calls `clear_local_cache`; `main.py` calls `start_poller`.

- [ ] **Step 1: Write the failing tests**

`tests/test_remote_message.py`:

```python
"""Remote message poller: caching, failure behavior, takeover bookkeeping"""

import json

import pytest


CONFIG = {
    'enable_remote_message': True,
    'remote_message_url': 'https://example.invalid/api/b/cubsmarquee',
    'remote_message_token': 'tok',
}


@pytest.fixture
def rm(tmp_path, monkeypatch):
    import remote_message
    monkeypatch.setattr(
        remote_message, 'CACHE_PATH', str(tmp_path / 'remote_message.json'))
    # Module-level state leaks between tests otherwise: a takeover shown in
    # one test would suppress it in the next.
    monkeypatch.setattr(remote_message, '_last_shown_id', None, raising=False)
    monkeypatch.setattr(remote_message, '_last_error', None, raising=False)
    # current_message() and take_pending_takeover() both consult
    # _load_config() to honour the enable toggle. Unstubbed, that reads the
    # real /home/pi/config.json -- absent on a dev machine, so every
    # assertion would see a disabled feature and get None.
    monkeypatch.setattr(remote_message, '_load_config', lambda: dict(CONFIG))
    return remote_message


class _Resp:
    def __init__(self, status, payload=None, text=''):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


def _stub_get(monkeypatch, rm, resp):
    def fake_get(url, headers=None, timeout=None):
        if isinstance(resp, Exception):
            raise resp
        return resp
    monkeypatch.setattr(rm.requests, 'get', fake_get)


class TestPolling:
    def test_stores_a_good_response(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        assert rm.current_message() == 'HELLO'

    def test_timeout_keeps_the_cache(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        # The board must keep showing the message through an outage.
        _stub_get(monkeypatch, rm, rm.requests.exceptions.Timeout())
        rm.poll_once(CONFIG)
        assert rm.current_message() == 'HELLO'

    def test_server_error_keeps_the_cache(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        _stub_get(monkeypatch, rm, _Resp(500, text='boom'))
        rm.poll_once(CONFIG)
        assert rm.current_message() == 'HELLO'

    def test_malformed_json_keeps_the_cache(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        _stub_get(monkeypatch, rm, _Resp(200, None))
        rm.poll_once(CONFIG)
        assert rm.current_message() == 'HELLO'

    def test_missing_fields_keep_the_cache(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        _stub_get(monkeypatch, rm, _Resp(200, {'text': 'NO ID'}))
        rm.poll_once(CONFIG)
        assert rm.current_message() == 'HELLO'

    def test_204_clears_the_cache(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        _stub_get(monkeypatch, rm, _Resp(204))
        rm.poll_once(CONFIG)
        assert rm.current_message() is None

    def test_disabled_feature_does_not_poll(self, rm, monkeypatch):
        called = []
        monkeypatch.setattr(
            rm.requests, 'get',
            lambda *a, **k: called.append(1))
        rm.poll_once({**CONFIG, 'enable_remote_message': False})
        assert called == []

    def test_missing_url_does_not_poll(self, rm, monkeypatch):
        called = []
        monkeypatch.setattr(
            rm.requests, 'get',
            lambda *a, **k: called.append(1))
        rm.poll_once({**CONFIG, 'remote_message_url': ''})
        assert called == []

    def test_disabled_feature_hides_a_cached_message(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        monkeypatch.setattr(
            rm, '_load_config', lambda: {**CONFIG,
                                         'enable_remote_message': False})
        assert rm.current_message() is None

    def test_poll_never_raises(self, rm, monkeypatch):
        # The poller runs on a thread beside the display; an exception
        # escaping here is a dead poller at best.
        _stub_get(monkeypatch, rm, RuntimeError('unexpected'))
        rm.poll_once(CONFIG)  # must not raise


class TestTakeover:
    def _store(self, rm, monkeypatch, text, msg_id):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': text, 'id': msg_id, 'updated_at': 1}))
        rm.poll_once(CONFIG)

    def test_returns_a_new_message_once(self, rm, monkeypatch):
        self._store(rm, monkeypatch, 'HELLO', 'abc')
        assert rm.take_pending_takeover() == 'HELLO'
        assert rm.take_pending_takeover() is None

    def test_repolling_the_same_id_does_not_refire(self, rm, monkeypatch):
        self._store(rm, monkeypatch, 'HELLO', 'abc')
        rm.take_pending_takeover()
        self._store(rm, monkeypatch, 'HELLO', 'abc')
        assert rm.take_pending_takeover() is None

    def test_identical_text_with_a_new_id_fires_again(self, rm, monkeypatch):
        self._store(rm, monkeypatch, 'HELLO', 'abc')
        rm.take_pending_takeover()
        # Re-posting the same words is a deliberate act and must show.
        self._store(rm, monkeypatch, 'HELLO', 'def')
        assert rm.take_pending_takeover() == 'HELLO'

    def test_nothing_cached_means_no_takeover(self, rm):
        assert rm.take_pending_takeover() is None


class TestClear:
    def test_clear_local_cache_empties_it(self, rm, monkeypatch):
        _stub_get(monkeypatch, rm, _Resp(
            200, {'text': 'HELLO', 'id': 'abc', 'updated_at': 1}))
        rm.poll_once(CONFIG)
        rm.clear_local_cache()
        assert rm.current_message() is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_remote_message.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'remote_message'`.

- [ ] **Step 3: Implement the poller**

`remote_message.py`:

```python
"""Remote message: poll the Worker, cache locally, feed the rotation"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import requests

from logger import get_logger
from scoreboard_config import load_user_config

logger = get_logger("remote_message")

CACHE_PATH = '/home/pi/remote_message.json'
POLL_INTERVAL_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 10

# The id of the message already shown as a takeover. Process-local on
# purpose: after a restart the current message shows once more, which is
# the friendlier failure -- a reboot should not silently swallow a message
# nobody in the room ever saw.
_last_shown_id: str | None = None
_last_error: str | None = None


def _load_config() -> dict[str, Any]:
    """Config for the poller (cached loader; re-parses only on change)"""
    return load_user_config()


def _read_cache() -> dict[str, Any] | None:
    try:
        with open(CACHE_PATH, 'r') as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get('text') else None
    except (OSError, ValueError):
        return None


def _write_cache(payload: dict[str, Any] | None) -> None:
    """Atomically replace the cache; None clears it"""
    if payload is None:
        try:
            os.remove(CACHE_PATH)
        except OSError:
            pass
        return
    tmp_path = CACHE_PATH + '.tmp'
    try:
        with open(tmp_path, 'w') as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CACHE_PATH)
    except OSError as e:
        logger.warning(f"Could not write remote message cache: {e}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _enabled(config: dict[str, Any]) -> bool:
    return (bool(config.get('enable_remote_message', True))
            and bool(config.get('remote_message_url')))


def poll_once(config: dict[str, Any]) -> None:
    """Fetch the current message once. Never raises.

    On any failure the existing cache stands, so an outage keeps showing
    the last message instead of blanking the board.
    """
    global _last_error
    try:
        if not _enabled(config):
            return

        response = requests.get(
            config['remote_message_url'],
            headers={
                'authorization':
                    f"Bearer {config.get('remote_message_token', '')}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code == 204:
            _write_cache(None)
            _last_error = None
            return

        if response.status_code != 200:
            # Logged once per distinct error: this runs every 30s and would
            # otherwise fill the log during any sustained outage.
            error = f"HTTP {response.status_code}"
            if error != _last_error:
                logger.warning(f"Remote message poll failed: {error}")
                _last_error = error
            return

        payload = response.json()
        text = payload.get('text')
        message_id = payload.get('id')
        if not isinstance(text, str) or not text or not message_id:
            error = "malformed payload"
            if error != _last_error:
                logger.warning(f"Remote message poll failed: {error}")
                _last_error = error
            return

        _write_cache({
            'text': text,
            'id': str(message_id),
            'fetched_at': time.time(),
        })
        _last_error = None

    except Exception as e:  # noqa: BLE001 - a poller must never take down the display
        error = f"{type(e).__name__}: {e}"
        if error != _last_error:
            logger.warning(f"Remote message poll failed: {error}")
            _last_error = error


def current_message() -> str | None:
    """The cached remote message, or None when there is none to show"""
    if not _enabled(_load_config()):
        return None
    cached = _read_cache()
    return cached['text'] if cached else None


def take_pending_takeover() -> str | None:
    """Return a message not yet shown as a takeover, exactly once"""
    global _last_shown_id
    if not _enabled(_load_config()):
        return None
    cached = _read_cache()
    if not cached:
        return None
    if cached.get('id') == _last_shown_id:
        return None
    _last_shown_id = cached.get('id')
    return cached['text']


def clear_local_cache() -> None:
    """Drop the cached message (used after a successful remote clear)"""
    _write_cache(None)


def _poll_loop() -> None:
    while True:
        poll_once(_load_config())
        time.sleep(POLL_INTERVAL_SECONDS)


def start_poller() -> None:
    """Start the background poll thread (idempotent per process)"""
    thread = threading.Thread(
        target=_poll_loop, name='remote-message-poller', daemon=True)
    thread.start()
    logger.info("Remote message poller started")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_remote_message.py -v`
Expected: PASS, all cases.

- [ ] **Step 5: Commit**

```bash
git add remote_message.py tests/test_remote_message.py
git commit -m "Poll the Worker for a remote message and cache it locally"
```

---

### Task 7: Show the message in the rotation

**Files:**
- Modify: `off_season_handler.py` — import (line ~29), `_tick` (line 620), `_display_custom_message` (line 1228); add `_maybe_show_remote_takeover`
- Modify: `main.py` — start the poller in `run()` (line 91)
- Test: `tests/test_remote_message.py`

**Interfaces:**
- Consumes: `current_message`, `take_pending_takeover`, `start_poller` from Task 6.
- Produces: `OffSeasonHandler._maybe_show_remote_takeover() -> None`; `_display_custom_message(duration=180, message_only=False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_remote_message.py`:

```python
class TestRotationIntegration:
    def _handler(self):
        from off_season_handler import OffSeasonHandler
        return OffSeasonHandler.__new__(OffSeasonHandler)

    def test_remote_message_wins_over_custom_message(self, monkeypatch):
        import off_season_handler as osh
        monkeypatch.setattr(
            osh.remote_message, 'current_message', lambda: 'FROM GRANDMA')
        handler = self._handler()
        handler.config = {'custom_message': 'GO CUBS GO'}
        assert handler._active_custom_message() == 'FROM GRANDMA'

    def test_falls_back_to_custom_message(self, monkeypatch):
        import off_season_handler as osh
        monkeypatch.setattr(
            osh.remote_message, 'current_message', lambda: None)
        handler = self._handler()
        handler.config = {'custom_message': 'GO CUBS GO'}
        assert handler._active_custom_message() == 'GO CUBS GO'

    def test_takeover_shows_the_message_once(self, monkeypatch):
        import off_season_handler as osh
        pending = ['SURPRISE']
        monkeypatch.setattr(
            osh.remote_message, 'take_pending_takeover',
            lambda: pending.pop() if pending else None)
        handler = self._handler()
        shown = []
        handler._display_custom_message = (
            lambda duration=180, message_only=False: shown.append(
                (duration, message_only)))
        handler._maybe_show_remote_takeover()
        handler._maybe_show_remote_takeover()
        assert len(shown) == 1
        assert shown[0][1] is True  # message_only, no facts rotation

    def test_takeover_error_does_not_break_the_rotation(self, monkeypatch):
        import off_season_handler as osh

        def boom():
            raise RuntimeError('nope')

        monkeypatch.setattr(
            osh.remote_message, 'take_pending_takeover', boom)
        handler = self._handler()
        handler._maybe_show_remote_takeover()  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_remote_message.py::TestRotationIntegration -v`
Expected: FAIL — `AttributeError: module 'off_season_handler' has no
attribute 'remote_message'`.

- [ ] **Step 3: Import the module**

In `off_season_handler.py`, next to the `celebration_display` import
(line 29):

```python
import remote_message
```

Import the module, not its functions: the tests monkeypatch
`osh.remote_message.current_message`, which only works through the module
object.

- [ ] **Step 4: Add the message resolver and the takeover**

Add these two methods to `OffSeasonHandler`, next to
`_display_custom_message`:

```python
    def _active_custom_message(self) -> str:
        """The remote message when one is posted, else the configured one"""
        remote = remote_message.current_message()
        if remote:
            return remote
        return self.config.get(
            'custom_message', f'GO {self.team.short_name.upper()} GO!')

    def _maybe_show_remote_takeover(self) -> None:
        """Show a newly posted message once, between rotation segments"""
        try:
            pending = remote_message.take_pending_takeover()
            if not pending:
                return
            print(f"Remote message takeover: {pending[:60]}")
            self._display_custom_message(duration=60, message_only=True)
        except Exception as e:
            # A takeover failing must not end the rotation cycle.
            print(f"Error in remote message takeover: {e}")
```

- [ ] **Step 5: Use the resolver and add `message_only`**

In `_display_custom_message` (line 1228), change the signature and the
message source. Replace lines 1228-1232:

```python
    def _display_custom_message(self, duration=180, message_only=False):
        """Display custom scrolling message combined with random Cubs facts

        With message_only, the facts rotation is skipped and the message
        repeats for the whole duration -- used by the remote-message
        takeover, which is about one message, not a facts slot.
        """
        custom_message = self._active_custom_message()
```

Then, in the same method, where a completed scroll advances to the next
fact, keep showing the message when `message_only` is set. Change the
block at lines ~1268-1273 from advancing unconditionally:

```python
                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96

                    # If we just finished showing the custom message
                    if showing_custom and not custom_shown:
                        custom_shown = True
                        showing_custom = False
                    elif message_only:
                        # Repeat the message instead of moving into facts.
                        showing_custom = True
                        custom_shown = False
                    else:
```

- [ ] **Step 6: Call the takeover between segments**

In `_tick` (line 620), after the flight interstitial and before the
`between_callback`:

```python
        def _tick():
            """Run the between-segment interstitial (if enabled) and
            optionally invoke the external between_callback. Returns True
            to abort the rotation."""
            if flights_between and flights_enabled:
                try:
                    self.flight_display.display_flight_info(
                        duration=flight_interstitial_sec
                    )
                except Exception as e:
                    print(f"Flight interstitial error: {e}")
            # A posted message interrupts the rotation here rather than
            # aborting the cycle, so the segment order after it survives.
            self._maybe_show_remote_takeover()
            if between_callback is not None:
                return bool(between_callback())
            return False
```

- [ ] **Step 7: Start the poller**

In `main.py`, inside `run()` (line 91), before the main `while` loop at
line 117:

```python
        import remote_message
        remote_message.start_poller()
```

Import inside `run()`, matching how this file defers other imports, and so
importing `main` in a test never starts a thread.

- [ ] **Step 8: Run the whole suite**

Run: `pytest tests/ -v`
Expected: PASS. Watch `tests/test_bugfixes.py` in particular — it asserts
on the rotation's display-handler wiring.

- [ ] **Step 9: Commit**

```bash
git add off_season_handler.py main.py tests/test_remote_message.py
git commit -m "Show a posted remote message once, then keep it in rotation"
```

---

### Task 8: Admin panel controls

**Files:**
- Modify: `wifi_config_server.py` — `DEFAULT_CONFIG`, `APPLIES_LIVE_KEYS`, a `/clear_remote_message` route, HTML, JS
- Test: `tests/test_admin_config.py`

**Interfaces:**
- Consumes: `clear_local_cache` from Task 6; the Worker's DELETE contract from Task 4.
- Produces: config keys `remote_message_url`, `remote_message_token`, `enable_remote_message`; route `POST /clear_remote_message`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_config.py`:

```python
class TestRemoteMessageAdmin:
    def test_keys_round_trip_and_apply_live(self, client, tmp_path):
        body = client.post('/save_config', json={
            'remote_message_url': 'https://x.workers.dev/api/b/cubsmarquee',
            'remote_message_token': 'tok',
            'enable_remote_message': True,
        }).get_json()
        assert body['success']
        assert body['reboot_required'] is False
        saved = json.loads((tmp_path / 'config.json').read_text())
        assert saved['remote_message_token'] == 'tok'

    def test_admin_page_has_the_remote_message_block(self, client):
        html = client.get('/admin').data.decode()
        assert 'id="remote_message_url"' in html
        assert 'id="enable_remote_message"' in html
        assert 'id="clear_remote_message"' in html
        assert 'id="remote_message_current"' in html

    def test_status_reports_nothing_posted(self, client, monkeypatch):
        import wifi_config_server as wcs
        monkeypatch.setattr(wcs, '_read_remote_cache', lambda: None)
        body = client.get('/remote_message_status').get_json()
        assert body['posted'] is False

    def test_status_reports_the_cached_message_and_age(
            self, client, monkeypatch):
        import time
        import wifi_config_server as wcs
        monkeypatch.setattr(
            wcs, '_read_remote_cache',
            lambda: {'text': 'HELLO', 'id': 'abc',
                     'fetched_at': time.time() - 120})
        body = client.get('/remote_message_status').get_json()
        assert body['posted'] is True
        assert body['text'] == 'HELLO'
        assert 110 <= body['age_seconds'] <= 130

    def test_clear_without_a_url_reports_failure(self, client):
        body = client.post('/clear_remote_message').get_json()
        assert body['success'] is False

    def test_clear_calls_the_worker_then_drops_the_cache(
            self, client, tmp_path, monkeypatch):
        import wifi_config_server as wcs
        client.post('/save_config', json={
            'remote_message_url': 'https://x.workers.dev/api/b/cubsmarquee',
            'remote_message_token': 'tok',
        })
        calls = {}

        class _R:
            status_code = 200

        def fake_delete(url, headers=None, timeout=None):
            calls['url'] = url
            calls['headers'] = headers
            return _R()

        monkeypatch.setattr(wcs.requests, 'delete', fake_delete)
        cleared = []
        monkeypatch.setattr(
            wcs, '_clear_remote_cache', lambda: cleared.append(1))

        body = client.post('/clear_remote_message').get_json()
        assert body['success'] is True
        assert calls['headers']['authorization'] == 'Bearer tok'
        assert cleared == [1]

    def test_clear_reports_a_worker_failure(self, client, monkeypatch):
        import wifi_config_server as wcs
        client.post('/save_config', json={
            'remote_message_url': 'https://x.workers.dev/api/b/cubsmarquee',
            'remote_message_token': 'tok',
        })

        def boom(url, headers=None, timeout=None):
            raise wcs.requests.exceptions.Timeout()

        monkeypatch.setattr(wcs.requests, 'delete', boom)
        assert client.post('/clear_remote_message').get_json()['success'] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_admin_config.py::TestRemoteMessageAdmin -v`
Expected: FAIL — the config keys and the route do not exist.

- [ ] **Step 3: Register the config keys**

`wifi_config_server.py` does not import `requests` today (verified), so add
it next to `import re` at line 12:

```python
import requests
```

`requests` is already in `requirements.txt`, so nothing new is installed.

In `APPLIES_LIVE_KEYS`:

```python
    'remote_message_url', 'remote_message_token', 'enable_remote_message',
```

In `DEFAULT_CONFIG`:

```python
        'remote_message_url': '',
        'remote_message_token': '',
        'enable_remote_message': True,
```

Add the cache path as a module constant next to the other path constants
(near `STATUS_FILE`). It must match `remote_message.CACHE_PATH` from
Task 6:

```python
REMOTE_MESSAGE_CACHE_PATH = '/home/pi/remote_message.json'
```

- [ ] **Step 4: Add the clear route**

Next to the other routes, after `save_config_route`:

```python
def _read_remote_cache():
    """The Pi's cached remote message, or None.

    Read directly rather than through remote_message: the admin panel is a
    separate service and must still start when the display-side module's
    dependencies are missing.
    """
    try:
        with open(REMOTE_MESSAGE_CACHE_PATH, 'r') as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get('text') else None
    except (OSError, ValueError):
        return None


@app.route('/remote_message_status')
def remote_message_status():
    """Report the message currently posted to this board, if any"""
    cached = _read_remote_cache()
    if not cached:
        return jsonify({'posted': False})
    return jsonify({
        'posted': True,
        'text': cached['text'],
        'age_seconds': int(time.time() - cached.get('fetched_at', 0)),
    })


def _clear_remote_cache():
    """Drop the Pi's cached remote message.

    Imported lazily: the admin panel runs as its own service and must not
    fail to start when the display-side module's deps are unavailable.
    """
    try:
        import remote_message
        remote_message.clear_local_cache()
    except Exception as e:
        print(f"Could not clear remote message cache: {e}")


@app.route('/clear_remote_message', methods=['POST'])
def clear_remote_message():
    """Clear the posted message at the Worker, then locally.

    The Worker is the source of truth: clearing only the local cache would
    let the next poll fetch the same message straight back.
    """
    config = load_config()
    url = config.get('remote_message_url', '')
    if not url:
        return jsonify({
            'success': False,
            'message': 'No remote message URL configured'})
    try:
        response = requests.delete(
            url,
            headers={
                'authorization':
                    f"Bearer {config.get('remote_message_token', '')}"},
            timeout=10)
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'message': f'Worker returned {response.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

    _clear_remote_cache()
    return jsonify({'success': True})
```

- [ ] **Step 5: Add the HTML**

Next to the other display toggles (near `enable_celebrations`, line ~1005):

```html
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_remote_message">
                                Enable remote message posting
                            </label>
                            <p style="font-size:12px;opacity:0.7;margin:4px 0;">
                                A posted message shows once, then takes the
                                custom-message slot until replaced or cleared.
                            </p>
                            <label for="remote_message_url">Worker URL:</label>
                            <input type="text" id="remote_message_url"
                                   placeholder="https://marquee-message.<sub>.workers.dev/api/b/cubsmarquee">
                            <label for="remote_message_token">Board token:</label>
                            <input type="password" id="remote_message_token">
                            <label>Currently posted:</label>
                            <div id="remote_message_current"
                                 style="font-family:monospace;padding:.4rem;
                                        background:#000;color:#ffdf00;
                                        border-radius:.3rem;">&mdash;</div>
                            <button type="button" id="clear_remote_message">
                                Clear posted message
                            </button>
                            <span id="clear_remote_message_result"></span>
                        </div>
```

- [ ] **Step 6: Add the JavaScript**

Inside `window.onload` (line 1311), next to the other config loads:

```javascript
            document.getElementById('enable_remote_message').checked =
                config.enable_remote_message !== false;
            document.getElementById('remote_message_url').value =
                config.remote_message_url || '';
            document.getElementById('remote_message_token').value =
                config.remote_message_token || '';
            async function refreshRemoteMessage() {
                const el = document.getElementById('remote_message_current');
                try {
                    const b = await (await fetch(
                        '/remote_message_status')).json();
                    if (!b.posted) { el.textContent = '\u2014'; return; }
                    const mins = Math.floor(b.age_seconds / 60);
                    el.textContent = b.text + '  (' +
                        (mins < 1 ? 'just now' : mins + ' min ago') + ')';
                } catch (e) {
                    el.textContent = '\u2014';
                }
            }
            refreshRemoteMessage();

            document.getElementById('clear_remote_message').onclick =
                async function () {
                    const out = document.getElementById(
                        'clear_remote_message_result');
                    out.textContent = 'Clearing...';
                    const r = await fetch('/clear_remote_message',
                                          {method: 'POST'});
                    const b = await r.json();
                    out.textContent = b.success
                        ? 'Cleared.'
                        : ('Failed: ' + (b.message || 'unknown'));
                    refreshRemoteMessage();
                };
```

In the save payload object, next to `enable_celebrations`:

```javascript
                enable_remote_message:
                    document.getElementById('enable_remote_message').checked,
                remote_message_url:
                    document.getElementById('remote_message_url').value,
                remote_message_token:
                    document.getElementById('remote_message_token').value,
```

- [ ] **Step 7: Run the suite**

Run: `pytest tests/ -v`
Expected: PASS, including `test_every_default_key_is_classified`.

- [ ] **Step 8: Commit**

```bash
git add wifi_config_server.py tests/test_admin_config.py
git commit -m "Add remote message settings and a clear button to the admin page"
```

---

### Task 9: Deploy to a Pi and verify end to end

**Files:**
- None. This task is verification on hardware.

**Interfaces:**
- Consumes: everything above.
- Produces: a working board.

- [ ] **Step 1: Push**

```bash
git push origin main
```

The nightly updater at 4 AM pulls main, py_compile-gates it, syncs tracked
files to `/home/pi/`, and reboots. To verify now rather than tomorrow,
continue with Step 2.

- [ ] **Step 2: Deploy to cubsmarquee**

Copy to `/home/pi/` — the repo root, **not** `/home/pi/cubsmarquee/`:

```bash
scp remote_message.py off_season_handler.py main.py wifi_config_server.py \
    pi@cubsmarquee.local:/home/pi/
```

If `cubsmarquee.local` does not resolve, mDNS from the Mac is unreliable
here; find the IP with `arp -a` and match a Raspberry Pi MAC OUI.

- [ ] **Step 3: Configure the board**

In `http://cubsmarquee.local/admin`, set the Worker URL to
`<deployed-url>/api/b/cubsmarquee` and the board token to `cubsmarquee`'s
token from the Task 2 scratchpad file. Save.

- [ ] **Step 4: Reboot**

```bash
ssh pi@cubsmarquee.local 'sudo reboot'
```

A `systemctl restart` leaves zombie processes holding the matrix; a full
reboot is required.

- [ ] **Step 5: Verify**

Post a message at `<deployed-url>/b/cubsmarquee` using that board's
passphrase, then watch:

```bash
ssh pi@cubsmarquee.local 'tail -f /home/pi/scoreboard_logs/scoreboard.log'
```

Expected, in order:
1. "Remote message poller started" at boot
2. Within 30s of posting, `/home/pi/remote_message.json` holds the text
3. Within one segment boundary (0-3 min), "Remote message takeover:" and
   the message on the panel
4. After the takeover, the message appears in the custom-message slot
   instead of the configured `custom_message`
5. "Clear posted message" in the admin panel removes it, and the board
   reverts to the configured `custom_message`

- [ ] **Step 6: Verify the outage behavior**

```bash
ssh pi@cubsmarquee.local 'sudo iptables -A OUTPUT -d 1.1.1.1 -j DROP'
```

Simpler and safer: temporarily set an unreachable Worker URL in the admin
panel. Either way the posted message must keep showing, and the log must
show the poll failure logged **once**, not every 30 seconds.

Restore the correct URL afterwards.

---

### Task 10: Document the feature

**Files:**
- Modify: `CLAUDE.md` — Project Structure table, APIs Used, Configuration

- [ ] **Step 1: Document it**

Add `remote_message.py` to the "Services & Infrastructure" table:

```markdown
| `remote_message.py` | Polls the Cloudflare Worker for a posted message, caches it to `/home/pi/remote_message.json` |
```

Add to "APIs Used":

```markdown
- **Marquee Message Worker** (`workers/marquee-message/`) - a Cloudflare
  Worker holding the current posted message per board in KV. Each board has
  its own URL and passphrase; the Pi polls with a per-board token. The Pi
  never accepts inbound connections — the admin panel has no authentication
  and can reboot the Pi, so it stays LAN-only. Secrets live in the Worker's
  `BOARDS` secret, never in `wrangler.jsonc`
```

Add to the `/home/pi/config.json` bullet list:

```markdown
- `remote_message_url` — the Worker's device endpoint for this board,
  `https://marquee-message.<sub>.workers.dev/api/b/<board>`
- `remote_message_token` — this board's device token. **Per-board**: one
  board's token never grants another
- `enable_remote_message` — when false the poller idles and the board falls
  back to `custom_message` without needing the cache cleared

A posted message shows once at the next rotation-segment boundary (0-3
min, not instant — the takeover lives in `_tick()`, which runs between
segments), then holds the custom-message slot until replaced or cleared.
It never overwrites `custom_message`, so clearing reverts to the original.
A live game holds the display: `_display_rotation_cycle` is the only
integration point, so takeovers wait for the game to end.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document remote message posting"
```

---

## Done When

- [ ] `pytest tests/ -v` passes
- [ ] `npm test` in `workers/marquee-message/` passes
- [ ] `git check-ignore config.json` matches
- [ ] Posting at the board URL puts the message on that panel within ~3 min
- [ ] A wrong passphrase is rejected; another board's passphrase is rejected
- [ ] Clearing from the admin panel reverts the board to `custom_message`
- [ ] With the Worker unreachable, the message keeps showing and the failure
      is logged once, not every 30 seconds
