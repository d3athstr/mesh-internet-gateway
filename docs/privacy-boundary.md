# Privacy boundary

Decided 2026-08-10 (Don). This document is the authority; if code or config
disagrees with it, the code is wrong.

## The rule

> **Only Empire12-owned nodes are published to the internet.
> Techtaria customer-home endpoints are never published.**

Publishing a node to `mqtt.meshtastic.org` puts it on the public map
directories ([meshmap.net](https://meshmap.net/),
[meshtastic.liamcottle.net](https://meshtastic.liamcottle.net/)) along with
an approximate position. Default map-report position precision is a ~1459 m
deviation — that is *neighbourhood* resolution, which is more than enough to
identify which subdivision a customer lives in, and it is paired with a
stable node ID and a long name.

Techtaria endpoints sit inside customers' houses. Their position is customer
PII that we hold in order to run their home automation, not ours to
broadcast. There is no product benefit that justifies it.

## Published (E12-owned, opt in)

| Node | ID | Notes |
|---|---|---|
| `meshgw` | TBD | this gateway |
| Heltec V4 gateway | `!f66ae684` | E12-DMZ, HQ |
| HA V3 | `!3368d390` | serial-attached to HA |
| e12solar RAK router | `!918e5b5a` | outdoor solar ROUTER |

All four sit at the Empire12 home site — a location that is already the
public origin of this mesh, and Don's own property.

## Not published (dark)

- **Every Techtaria customer endpoint**, including the bench prototype
  `!f66b6bc0`. Even though the prototype is currently on-site, keeping the
  whole `pawmations-*` endpoint class dark means the fleet default is safe:
  a node that gets deployed to a customer never has to be *remembered* to be
  turned off.

Per-node settings that must stay off on endpoints:

```
mqtt.enabled                 = false
mqtt.map_reporting_enabled   = false
mqtt.proxy_to_client_enabled = false
position.ok_to_mqtt          = false   # "OK to MQTT" / share-position flag
```

## Channel policy on `meshgw`

| Idx | Channel | Uplink | Downlink | Why |
|---|---|---|---|---|
| 0 | primary (default LongFast) | **yes** | no | This is the only channel that reaches the public broker. Carries public mesh traffic only. |
| 1 | `paw-cmd` | **NO** | **NO** | C&C. Uplink would relay command traffic to a public broker; **downlink would let internet-sourced packets inject into the command path.** |
| 2 | `Techtaria` | **NO** | **NO** | Customer community chat. Private to the fleet; already relayed cloud-side by the ops bridge into DDB `pawmations-vega-mesh`. |

Downlink-off on idx 1 is the important one. The C&C receiver does validate an
HMAC envelope with a nonce-replay store, but that is defence in depth — it is
not a licence to accept packets from the open internet.

## Things that leak by accident

- **`mqtt.proxy_to_client_enabled`** routes MQTT through a connected client
  instead of the device's own network stack. It bypasses the assumption that
  "the endpoint has no internet, so it cannot publish". Keep it false fleet-wide.
- **Map reports are unencrypted by design** — that is how public maps read
  them. Enabling map reporting on a node with a precise fixed position
  publishes that position regardless of channel PSKs.
- **`position.fixed_position` + real coordinates** on an endpoint is exactly
  the data we do not want uplinked. Endpoints legitimately have fixed
  positions for local use; the protection is `ok_to_mqtt=false`, not the
  absence of coordinates.
- A future fleet-wide `--set` batch is the most likely way this rule gets
  broken. Any bulk Meshtastic config change must be `--limit`-style scoped to
  E12 nodes, never applied to `all`.
