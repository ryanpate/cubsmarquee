# Cubs Marquee — Instructions

The Cubs Marquee is a wall display that shows live baseball scores for your team. During
the season it follows the game pitch by pitch — the score, the inning, who's batting, and
who's on base. When there's no game on, it cycles through other things: your local
weather, football and golf scores, news headlines, team trivia, and a clock. It runs by
itself. You plug it in and leave it alone.

New here? Start with the [Quick Start](QUICKSTART.md) — it gets you running in about ten
minutes. This page is the full reference.

---

## What you need

In the box:

- The marquee, fully assembled
- Its power supply
- A printed setup card

You supply:

- A wall outlet
- Your home WiFi network name and password
- A phone, tablet, or laptop for the one-time setup

The marquee needs WiFi to work. Everything it displays — scores, weather, news — comes
from the internet.

## Setting it up

Full setup is in the [Quick Start](QUICKSTART.md). The short version: plug it in, connect
your phone to the marquee's own `CubsMarquee-Setup` network (password `gocubsgo2024`),
open `cubsmarquee.local/admin`, and enter your home WiFi details on the `WiFi Setup` tab.

A few things worth knowing:

**The marquee creates its own WiFi network only when it can't reach yours.** That's how
setup works, and it's also the safety net: if you change your home WiFi password later, or
move the marquee to a new house, it will go back to showing the `SETUP` screen and
broadcasting `CubsMarquee-Setup` so you can point it at the new network. You don't need to
reset anything.

**Give it two full minutes after any restart** before deciding something is wrong.

**`.local` addresses don't work on every phone.** If `cubsmarquee.local/admin` won't load
during setup, use `192.168.4.1` instead. Once the marquee is on your home WiFi, use
`cubsmarquee.local/admin`; if that fails, your router's device list will show the
marquee's address.

## Everyday use

Nothing. Leave it plugged in.

The marquee starts by itself whenever it has power, so it survives a power cut without any
help from you. Every night around 4 AM it checks for software updates and installs them,
which is why it may briefly go dark in the early morning.

To turn it off, unplug it. There's no power switch and no shutdown routine to worry about.

## Settings

Open `cubsmarquee.local/admin` from any device on your home WiFi. Settings live on the
`Display Config` tab, grouped into collapsible sections. Changes take effect after you tap
`Save Configuration` at the bottom.

### Team

Pick which baseball team the marquee follows, and which football team it shows during
football season.

### Brightness

| Setting | What it does | Default |
|---------|--------------|---------|
| `Brightness` | How bright the panel is, from 10% to 100%. Changes take about 10 seconds to appear. | 100% |
| `Auto-dim at night` | Lowers the brightness automatically during set hours | Off |
| `Dim from` / `until` | The hours to dim. Spans past midnight, so 22:00 to 07:00 works as you'd expect. | 22:00 to 07:00 |
| `Night brightness` | How bright it is during those hours | 30% |

If the marquee is in a bedroom or hallway, auto-dim is the setting you want.

### Display Mode

Controls when the marquee shows games versus everything else.

| Option | What it does |
|--------|--------------|
| `Automatic` | Games during the season, other content the rest of the year. This is the setting most people want. |
| `Always show game (if available)` | Prefers game coverage whenever a game exists |
| `Game schedule + off-season content rotation` | Shows the schedule alongside the rotating content |
| `Off-season content only` | Never interrupts with game information |

Default: `Automatic`.

### What it shows

Each of these is a checkbox you can turn on or off. All are on by default.

- Team facts & custom message
- Team breaking news
- Today in team history
- Spring Training countdown
- Playoff race (July–September)
- Wrigley scoreboard clock
- All-Star Game
- NFL team game (football season)
- NFL breaking news
- PGA Tour leaderboard, news, and facts (golf season)
- Weather
- Newsmax and USA Today headlines
- Stock exchange ticker
- ISS tracker — shows where the International Space Station is
- Flight tracking, and a full-screen radar view
- Bible verse of the day, and Bible facts

Each scrolling display also has its own speed slider, from 1 to 10.

### Weather

Enter your `ZIP Code (for weather)`. Without it, the weather display has no location to
report on. No account or API key is needed.

### Custom Message

Your own text, shown between team facts. Default: `GO CUBS GO!`

### Flight tracking

If you turn on flight tracking, set `Latitude` and `Longitude` for the spot you want to
watch, and a `Max Range` in nautical miles. There's an `Address Lookup` box that fills in
the coordinates for you from a street address or town name.

## Other tabs

**`System`** — rename the marquee. If you own more than one, give each a different name
(lowercase letters, numbers, and dashes only, like `cubsmarquee-1`) so their web addresses
don't collide. After renaming, the marquee's address becomes `thatname.local/admin`.

**`Service Control`** — shows whether the scoreboard is running, with `Start Service`,
`Stop Service`, and `Restart Service` buttons, plus `Reboot Pi` to restart the whole unit.
Reboot is the one to reach for; the others are mainly for troubleshooting.

**`Logs`** — `Application Logs`, `Error Logs`, and `WiFi Manager Logs`. Useful to copy
into a support email.

## Troubleshooting

**The panel is dark**
Check that the power supply is firmly seated at both ends and the outlet has power. If the
panel stays dark for more than two minutes with power connected, the unit needs service.

**It's stuck on the SETUP screen**
The marquee can't reach your WiFi. This is normal after a WiFi password change or a move
to a new house. Redo the [Quick Start](QUICKSTART.md) steps from step 2 to point it at the
network.

**The `CubsMarquee-Setup` network doesn't appear on my phone**
Wait two full minutes after plugging in — the first startup includes a restart partway
through. If it still doesn't appear, unplug the marquee, wait ten seconds, and plug it
back in.

**`cubsmarquee.local/admin` won't load**
Some phones don't handle `.local` addresses. During setup, use `192.168.4.1` instead.
Once the marquee is on your home WiFi, try from a laptop, or find its address in your
router's list of connected devices. Also confirm your phone is on the same WiFi network as
the marquee.

**The display is frozen or showing stale information**
Open `cubsmarquee.local/admin`, go to `Service Control`, and tap `Reboot Pi`. Wait two
minutes. If you can't reach the page, unplug the marquee and plug it back in.

**The weather shows the wrong place, or no weather at all**
Set your `ZIP Code (for weather)` on the `Display Config` tab and tap
`Save Configuration`.

**Scores look wrong or a game is missing**
Scores come from the league's official feed. Delayed or postponed games sometimes take a
few minutes to update there before the marquee can show the change.

**Still stuck**
Unplug it, wait ten seconds, plug it back in, and give it two minutes. If that doesn't fix
it, copy the `Error Logs` from the `Logs` tab and include them when you get in touch.

## Getting help

Email [SUPPORT EMAIL].

Please include: what the display is showing, what you already tried, and the `Error Logs`
from the `Logs` tab if you can reach the settings page.
