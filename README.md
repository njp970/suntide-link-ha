# Suntide Link for Home Assistant

Your inverter's live data at 1-second resolution, plus Suntide's
intelligence — the day's plan, the written story of your battery, savings,
and upcoming paid grid events — as native Home Assistant entities.

## What you get

**Local (no cloud required):** solar, house load, battery power, grid
power, and battery charge, polled directly from your Suntide Link on your
LAN. Faster and more reliable than any cloud path, because it never leaves
your house.

**Cloud (optional):** the plan headline, "the day so far" story, this
month's battery earnings, and the next paid grid event — the things only
Suntide's brain knows. Paste an integration token from the Suntide app
(Settings → Integrations) to enable.

## Install

1. HACS → Integrations → custom repository → this repo.
2. Settings → Devices & Services: your Link is discovered automatically.
3. Optionally paste a cloud token when asked. Done — no YAML anywhere.

Your Link keeps working with Home Assistant even if Suntide's cloud is
unreachable; the local sensors never depend on it.
