![Suntide](https://raw.githubusercontent.com/njp970/suntide-link-ha/main/images/logo.png)

# Suntide Link for Home Assistant

Your solar inverter and battery in Home Assistant at **1-second resolution**,
straight off your LAN — plus, optionally, the intelligence from your Suntide
account: the day's plan, a written story of what your battery has done, this
month's earnings, and paid grid events your automations can react to.

Works with a [Suntide Link](https://suntide.energy) — the small box that
connects to your inverter locally and does the reading your cloud app was
never fast enough for.

> **Upgrading to 0.3.0?** Before your Link updates to firmware 0.17.0, turn
> on Home Assistant and local access for it in the Suntide app, then update
> this integration. See [Local access token](#local-access-token).

---

## Why this exists

Most inverter integrations poll a manufacturer's cloud: 5-minute data,
minutes late, and down when their API is. The Link reads your inverter
**on your own network every 5 seconds** and this integration reads the Link
at 1 Hz. Nothing in the fast path leaves your house or touches the internet.

**Local never depends on cloud.** That is the design rule the whole
integration is built around: if Suntide's API is unreachable — or you cancel
your subscription entirely — the power sensors keep updating at full speed.
Only the cloud-intelligence entities go quiet. Your dashboard is yours.

## Entities

### Local (always on, no account needed)

Polled from the Link on your LAN, once per second.

| Entity | Unit | Notes |
|---|---|---|
| `sensor.solar_power` | W | 0 on battery-only systems |
| `sensor.house_load` | W | derived from the inverter's own energy balance |
| `sensor.battery_power` | W | **positive = charging**, negative = discharging |
| `sensor.grid_power` | W | **positive = importing**, negative = exporting |
| `sensor.battery_charge` | % | state of charge |

### Cloud (optional — needs a Suntide token)

Refreshed every 5 minutes from your Suntide account.

| Entity | Type | What it is |
|---|---|---|
| `sensor.plan` | text | the plan headline (full text in the `full` attribute) |
| `sensor.the_day_so_far` | text | the day's story; every beat in the `beats` attribute |
| `sensor.battery_earned_this_month` | GBP | measured, never modelled |
| `sensor.next_grid_event` | timestamp | with `rate_per_kwh` and `expected_net` attributes |
| `sensor.cheap_rate_starts` / `_ends` | timestamp | your tariff's cheap window, today |
| `sensor.battery_holds_until` | timestamp | empty when the battery lasts the whole day |
| `sensor.predicted_spend_24h` | GBP | can be **negative** on a good grid-event day |
| `sensor.projected_end_of_day_charge` | % | where the plan expects the battery to land |
| `binary_sensor.grid_event_active` | on/off | **ON during a paid export/charge hour** |

## Automations this was built for

**Run the dishwasher when the cheap rate starts:**

```yaml
trigger:
  - platform: time
    at: sensor.cheap_rate_starts
action:
  - service: switch.turn_on
    target: { entity_id: switch.dishwasher }
```

**Get the EV charger out of the way during a paid grid event**
(your battery earning £1/kWh should not fight a 7 kW charger):

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.grid_event_active
    to: "on"
action:
  - service: switch.turn_off
    target: { entity_id: switch.ev_charger }
mode: single
```

**Warn if today won't make it:**

```yaml
trigger:
  - platform: state
    entity_id: sensor.battery_holds_until
condition:
  - condition: template
    value_template: "{{ states('sensor.battery_holds_until') not in ('unknown','unavailable','') }}"
action:
  - service: notify.mobile_app
    data:
      message: >
        Battery expected to run out at
        {{ as_timestamp(states('sensor.battery_holds_until')) | timestamp_custom('%H:%M') }}.
```

## Install

### HACS (recommended)

1. HACS → Integrations → ⋮ → **Custom repositories** →
   add `njp970/suntide-link-ha` (category: Integration).
2. Install **Suntide Link**, restart Home Assistant.
3. Settings → Devices & Services — your Link is **discovered automatically**
   (it announces itself on your network; nothing to type).
4. In the Suntide app, open Settings, then your Link, and turn on
   **Home Assistant and local access**.
5. Either paste a **cloud token** from the Suntide app
   (Settings → Integrations), which also fetches the Link's local access
   token for you and adds the intelligence entities, or paste the
   **local access token** the app shows for your Link (local sensors only).
   You can change either later with the integration's **Configure** button.

### Local access token

From firmware 0.17.0 the Link answers Home Assistant only when the request
carries its local access token. The token is made when you turn on Home
Assistant and local access for the Link in the Suntide app, and the app
shows it there. Local access is off until you turn it on.

- **With a cloud token**, the integration fetches the local access token
  from your Suntide account; you never type it.
- **Without one**, paste the token from the app.
- **If the Link refuses the token** (it has just updated, or you made a new
  token in the app), Home Assistant shows a re-authenticate prompt. With a
  cloud token saved, leave the box empty and the new token is fetched.
- Links on firmware before 0.17.0 ignore the token, so setting it early is
  harmless and saves a prompt later.

### Manual discovery fallback

If your network filters mDNS (some mesh systems, VLAN setups): add the
integration by hand and enter the Link's IP address, and its Link ID (for
example `link-0002`, shown in the Suntide app) so a cloud token can fetch
the local access token. Everything else is identical.

## Data & privacy — the plain version

- **The fast lane never leaves your house.** Local sensors talk directly to
  the Link over HTTP on your LAN, with the Link's local access token. The
  token is never written to Home Assistant's log.
- **The cloud token is read-only and scoped.** It reaches a summary of your
  own account and your own Links' local access tokens, and nothing else. It cannot
  change settings, cannot write to your inverter, and you can revoke it any
  time in the Suntide app — revocation takes effect on the next request.
- **Cancel your subscription and this keeps working.** The local entities
  are a property of the hardware you own, not of an account. Only the
  cloud entities depend on Suntide.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| Power entities `unavailable` | HA can't reach the Link — check it has power and Wi-Fi; if its IP changed and discovery is filtered, re-add with the new address |
| Cloud entities `unavailable`, local fine | Suntide's API is unreachable or your token was revoked — check the integration's log line; mint a fresh token in the app if needed |
| "Re-authenticate" prompt for the Link | The Link refused its local access token. Turn on Home Assistant and local access for it in the Suntide app, then open the prompt: leave it empty if you have a cloud token saved, or paste the token from the app |
| "Local access is off for this Link" | Turn on Home Assistant and local access for this Link in the Suntide app, then try again |
| Values frozen | They shouldn't be: local entities update every second. A frozen value with `available` state is a bug — please open an issue |
| Discovered device shows an odd name | The Link announces its device id (e.g. `link-bench-01`); rename the device in HA as you like |

## How it fits together

```
your inverter ──(Modbus, local)── Suntide Link ──(HTTP, LAN, 1s)── this integration
                                        │
                                        └─(TLS)── Suntide cloud ──(token, 5min)── cloud entities
```

Two coordinators, two trust domains, one rule: the left side never waits for
the right side.

## Development

Plain Home Assistant custom integration: `config_flow` + `DataUpdateCoordinator`,
no external requirements. Tests use `pytest-homeassistant-custom-component`
(Python 3.13):

```
pip install -r requirements_test.txt
pytest
```

PRs welcome, especially additional language
translations under `custom_components/suntide_link/translations/`.

## License

MIT — see [LICENSE](LICENSE). The integration is deliberately open: the
intelligence lives server-side, and the local data was always yours.
