# Changelog

## 0.3.0 (2026-09-16)

**Upgrade note:** Before your Link updates to firmware 0.17.0, turn on Home
Assistant and local access for it in the Suntide app, then update this
integration.

- The Link's local sensors now use a local access token. From firmware
  0.17.0 the Link only answers requests that carry it.
- Set-up fetches the token for you when you add a Suntide cloud token, or
  takes the token shown in the Suntide app. It is checked against the Link
  before the device is added.
- If the Link refuses the token (for example after it updates, or after a
  new token is made in the app), Home Assistant asks you to re-authenticate
  instead of leaving the sensors unavailable.
- Configure now changes the local access token as well as the cloud token.
  Leave the local token empty to fetch it again with your cloud token.
- Adding a Link by address can now take its Link ID, so a cloud token can
  fetch its local access token.
- Clearing the cloud token in Configure now removes it (it used to fall back
  to the one from set-up).
- Tokens are never written to the log.

## 0.2.3 (2026-08-31)

- Change the cloud token without deleting the device.

## 0.2.2 (2026-08-31)

- The integration carries its own brand icon.

## 0.2.1 (2026-08-31)

- Loads on current Home Assistant releases.

## 0.2.0 (2026-08-31)

- Automation-grade cloud entities: cheap rate times, battery holds until,
  predicted spend, projected end-of-day charge.
