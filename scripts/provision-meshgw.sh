#!/bin/bash
# Provision meshgw's Meshtastic device settings: region, MQTT uplink, map
# reporting, and the channel uplink/downlink policy.
#
#   ./provision-meshgw.sh [--host meshgw.local] [--dry-run]
#
# This script is the AUTHORITY for the privacy boundary in
# docs/privacy-boundary.md. If you change what gets published, change it here.
#
# NOT YET RUN AGAINST HARDWARE. Review every line before first use.
#
# WHY EVERY SETTING IS ITS OWN INVOCATION: on this fleet, batching multiple
# --set arguments has repeatedly dropped settings SILENTLY on already-
# configured devices (documented for device.role, lora.region, led_heartbeat,
# ambient_lighting and store_forward). One transaction per setting, verified
# after, is slower and is the only way that has proven reliable.
set -euo pipefail

HOST="${MESHGW_HOST:-meshgw.local}"
DRY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --dry-run) DRY=1; shift ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

MT=(meshtastic --host "$HOST")

# The fleet admin key comes from Vault, never from this file — house rule is
# credentials in Vault only, and this repo is a candidate for going public.
# It is the PUBLIC half of the x25519 pair (the device only ever needs that),
# but it is still a fleet identifier and does not belong in git.
vault_login() {
    export VAULT_ADDR="${VAULT_ADDR:?set VAULT_ADDR to your Vault endpoint}"
    export VAULT_CACERT="${VAULT_CACERT:-/etc/ssl/certs/vault-ca.crt}"
    if [[ -z "${VAULT_TOKEN:-}" ]]; then
        VAULT_TOKEN=$(vault write -field=token auth/approle/login \
            role_id=$(jq -r .role_id /etc/vault.d/approle.json) \
            secret_id=$(jq -r .secret_id /etc/vault.d/approle.json))
        export VAULT_TOKEN
    fi
}

vault_admin_key() {
    vault_login
    vault kv get -field=public secret/empire12/meshtastic/admin-key
}

# The site coordinates come from Vault for the same reason the admin key does:
# THIS REPO IS PUBLIC. A fixed_position at sub-metre precision is a home
# address. secret/empire12/meshgw/site holds lat / lon / alt.
vault_site() {
    vault_login
    vault kv get -field="$1" secret/empire12/meshgw/site
}

# Poll the device API until it answers again (used after any write that
# reboots the radio). Returns non-zero if it never comes back.
wait_for_api() {
    local port="${MESHGW_API_PORT:-4403}" i
    for i in $(seq 1 60); do
        if (exec 3<>"/dev/tcp/${HOST}/${port}") 2>/dev/null; then
            exec 3<&- 2>/dev/null || true
            sleep 5           # let it finish coming up, not just bind
            return 0
        fi
        sleep 5
    done
    echo "device API did not come back on ${HOST}:${port}" >&2
    return 1
}

# A plain `sleep 3` between writes is NOT enough, and that is not a tuning
# problem -- several settings REBOOT the radio (confirmed for lora.region and
# for writing coordinates; assume any of them can). The API socket then
# disappears for far longer than 3s, so the NEXT write dies with
# "Timed out waiting for connection completion" or a BrokenPipeError, and under
# `set -e` that killed the entire run. Three consecutive runs on 2026-09-09
# aborted this way, each at a different setting, which is exactly what a
# reboot-race looks like.
#
# So: retry each write, and wait for the API to genuinely answer afterwards.
# Re-writing a value that already landed is harmless -- every one of these is
# idempotent -- whereas a half-applied privacy boundary is not.
_write_retry() {
    local label="$1"; shift
    local i out
    for i in 1 2 3 4 5; do
        if out=$("$@" 2>&1); then
            wait_for_api || true
            return 0
        fi
        echo "    $label: attempt $i failed, waiting for radio to come back" >&2
        wait_for_api || true
        sleep 5
    done
    echo "FAILED: $label did not apply after 5 attempts" >&2
    echo "$out" | tail -2 >&2
    return 1
}

set_one() {
    echo "  set $1 = $2"
    [[ $DRY -eq 1 ]] && return 0
    _write_retry "set $1" "${MT[@]}" --set "$1" "$2"
}

ch_set() {
    echo "  ch$1 $2 = $3"
    [[ $DRY -eq 1 ]] && return 0
    _write_retry "ch$1 $2" "${MT[@]}" --ch-index "$1" --ch-set "$2" "$3"
}

echo "== meshgw provisioning -> $HOST =="
[[ $DRY -eq 1 ]] && echo "   (dry run — nothing will be written)"

# ---------------------------------------------------------------- radio
# Region and role are set SOLO and FIRST — see the note above.
echo "-- radio --"
set_one lora.region US
set_one device.role ROUTER          # infrastructure node: relays for the mesh
set_one lora.modem_preset LONG_FAST # MUST match the rest of the fleet
# Start conservative. Raise to 30 only after the 3V3 rail is proven to hold
# through a TX burst — a sagging rail during TX presents as terrible range,
# not as a power fault.
set_one lora.tx_power 22

# ---------------------------------------------------------------- position
# meshgw is at the Empire12 home site (same coords as the HA V3 / RAK router).
# The coordinates themselves live in Vault at secret/empire12/meshgw/site --
# they are a home address and this repo is public.
# Writing coordinates REBOOTS the radio. Setting fixed_position WITHOUT
# writing coords broadcasts nothing — that bug has bitten this fleet before.
echo "-- position --"
if [[ $DRY -eq 0 ]]; then
    SITE_LAT=$(vault_site lat)
    SITE_LON=$(vault_site lon)
    SITE_ALT=$(vault_site alt)
    [[ -z "$SITE_LAT" || -z "$SITE_LON" ]] && {
        echo "no coordinates at secret/empire12/meshgw/site" >&2; exit 4; }
    meshtastic --host "$HOST" \
        --setlat "$SITE_LAT" --setlon "$SITE_LON" --setalt "${SITE_ALT:-0}"
    # Writing coordinates REBOOTS the radio. A fixed `sleep 10` is not enough --
    # the API socket comes back well after that, so the next --set died with
    # "Connection timed out" and took the whole run with it (2026-09-09, three
    # attempts in a row). Wait for the port to actually answer instead.
    wait_for_api
fi
set_one position.fixed_position true
set_one position.gps_mode DISABLED

# ---------------------------------------------------------------- MQTT
# This is what puts E12 nodes on the public map directories.
echo "-- MQTT uplink (public broker) --"
set_one mqtt.address mqtt.meshtastic.org
set_one mqtt.username meshdev          # documented public-broker credentials
set_one mqtt.password large4cats
set_one mqtt.root msh/US
set_one mqtt.encryption_enabled true   # ship ciphertext, not plaintext, for
                                       # anything that is not a map report
set_one mqtt.json_enabled false        # JSON publishes DECRYPTED payloads
# TLS IS NOT SUPPORTED BY meshtasticd (native/portduino) and this is not a
# soft failure: the firmware rejects the ENTIRE MQTT config while it is set --
#   ERROR [Router] Invalid MQTT config: tls_enabled is not supported on this node
# -- so mqtt.enabled silently reverts to false and the gateway never connects,
# while the CLI cheerfully reports every write as successful. Verified on
# fw 2.7.26, 2026-09-09. `tls_enabled true` is correct for ESP32 nodes; it is
# wrong here.
#
# The transport to mqtt.meshtastic.org:1883 is therefore PLAINTEXT. Accepted by
# Don 2026-09-09. What that does and does not expose:
#   - channel payloads stay Meshtastic-encrypted (mqtt.encryption_enabled true)
#   - the broker credentials are Meshtastic's documented public ones
#   - map reports are public by design
#   - what leaks is metadata: that this node connects, and its node ID
set_one mqtt.tls_enabled false
# proxy_to_client routes MQTT via a connected client instead of the device's
# own stack. It is how a supposedly-offline node ends up publishing. Off.
set_one mqtt.proxy_to_client_enabled false
set_one mqtt.enabled true

# ---------------------------------------------------------------- map report
echo "-- map reporting (public directories) --"
set_one mqtt.map_reporting_enabled true
set_one mqtt.map_report_settings.publish_interval_secs 900
# CONFIRM THE PRECISION -> METRES MAPPING IN THE MESHTASTIC DOCS BEFORE
# DEPLOY. Lower value = coarser. The firmware default is a ~1459 m deviation;
# this node sits at Don's home, so coarse is the right default and there is no
# reason to publish a sharper position than the directories need.
set_one mqtt.map_report_settings.position_precision 13
# fw 2.5+ gate — without this the position is withheld from MQTT entirely.
# The field is on the LoRa config, NOT position: `PositionConfig` has no
# `ok_to_mqtt` member (verified against fw 2.7.26 protobufs 2026-09-09).
# `--set position.ok_to_mqtt` therefore fails, and under `set -e` it aborts
# the run before the channel policy and hardening blocks ever execute.
set_one lora.config_ok_to_mqtt true

# ---------------------------------------------------------------- channels
# THE PRIVACY BOUNDARY. See docs/privacy-boundary.md.
#   idx 0 primary   — uplink ON, downlink off   (the only public channel)
#   idx 1 paw-cmd   — uplink OFF, downlink OFF  (C&C: downlink = injection path)
#   idx 2 Techtaria — uplink OFF, downlink OFF  (customer community chat)
#   idx 3 sentinel  — uplink OFF, downlink OFF  (Techtaria Sentinel RF counter-surv)
#
# Every secondary channel must be listed here. A channel this script does not
# name is a channel whose uplink state nothing re-asserts: it defaults to off
# when created, then drifts silently and no run of this script will correct it.
# sentinel was exactly that gap until 2026-09-09 — it existed on the V4 and the
# HA V3 while this script only knew about 0-2.
echo "-- channel uplink/downlink policy --"
ch_set 0 uplink_enabled true
ch_set 0 downlink_enabled false
ch_set 1 uplink_enabled false
ch_set 1 downlink_enabled false
ch_set 2 uplink_enabled false
ch_set 2 downlink_enabled false
ch_set 3 uplink_enabled false
ch_set 3 downlink_enabled false

# ---------------------------------------------------------------- hardening
# House standard D050.
echo "-- hardening (D050) --"
set_one power.is_power_saving false
set_one device.led_heartbeat_disabled true
if [[ $DRY -eq 1 ]]; then
    # Do not fetch on a dry run: set_one echoes its argument, and there is no
    # reason to put the key on a terminal or in a log to preview the plan.
    echo "  set security.admin_key = base64:<from vault>"
else
    ADMIN_KEY=$(vault_admin_key)
    [[ -z "$ADMIN_KEY" ]] && {
        echo "no admin key at secret/empire12/meshtastic/admin-key" >&2; exit 3; }
    set_one security.admin_key "base64:${ADMIN_KEY}"
fi
set_one security.is_managed false      # is_managed was tested and REJECTED —
                                       # it blocks local admin. admin_key only.

echo
echo "== verify =="
echo "Run these and read the output — do not assume the writes landed:"
cat <<'EOF'
  meshtastic --host $HOST --get mqtt
  meshtastic --host $HOST --get position
  meshtastic --host $HOST --info | sed -n '/Channels/,/^$/p'

CHECK, in this order:
  1. mqtt.enabled true AND map_reporting_enabled true
  2. channels 1 (paw-cmd), 2 (Techtaria) and 3 (sentinel) ALL show
     uplink_enabled=false AND downlink_enabled=false.
     If any is true, STOP and fix before the node stays up.
  2b. VERIFY EACH SECONDARY PSK BY HASH against its source of truth --
     sha256 of the DECODED BYTES, never by the channel merely being present
     with the right name. `--ch-add` seeds a RANDOM key, so an interrupted
     provisioning leaves a correctly-named channel that cannot decrypt a
     thing. The HA V3 ran two months that way. Sources:
       paw-cmd   Vault secret/empire12/pawmations/meshtastic/channel-psk
       sentinel  Vault secret/empire12/pawmations/meshtastic/sentinel-channel-psk
       Techtaria Vault secret/empire12/pawmations/meshtastic/techtaria-channel-psk
                 (mirror of AWS SM pawmations/meshtastic/community-channel)
     All three are stored WITHOUT the `base64:` prefix; the CLI requires it.
  3. Node position appears in the node DB (check --info, NOT --get position,
     which only shows the fixed_position FLAG).
  4. Within ~15-30 min the node should appear on https://meshmap.net/
EOF
