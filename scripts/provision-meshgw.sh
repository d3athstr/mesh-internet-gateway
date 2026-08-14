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
vault_admin_key() {
    export VAULT_ADDR="${VAULT_ADDR:?set VAULT_ADDR to your Vault endpoint}"
    export VAULT_CACERT="${VAULT_CACERT:-/etc/ssl/certs/vault-ca.crt}"
    if [[ -z "${VAULT_TOKEN:-}" ]]; then
        VAULT_TOKEN=$(vault write -field=token auth/approle/login \
            role_id=$(jq -r .role_id /etc/vault.d/approle.json) \
            secret_id=$(jq -r .secret_id /etc/vault.d/approle.json))
        export VAULT_TOKEN
    fi
    vault kv get -field=public secret/empire12/meshtastic/admin-key
}

set_one() {
    echo "  set $1 = $2"
    [[ $DRY -eq 1 ]] && return 0
    "${MT[@]}" --set "$1" "$2"
    sleep 3          # let the device settle + commit before the next write
}

ch_set() {
    echo "  ch$1 $2 = $3"
    [[ $DRY -eq 1 ]] && return 0
    "${MT[@]}" --ch-index "$1" --ch-set "$2" "$3"
    sleep 3
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
# Writing coordinates REBOOTS the radio. Setting fixed_position WITHOUT
# writing coords broadcasts nothing — that bug has bitten this fleet before.
echo "-- position --"
if [[ $DRY -eq 0 ]]; then
    meshtastic --host "$HOST" \
        --setlat ***REMOVED-SITE-LAT*** --setlon -***REMOVED-SITE-LON*** --setalt 514
    sleep 10
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
set_one mqtt.tls_enabled true
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
set_one position.ok_to_mqtt true

# ---------------------------------------------------------------- channels
# THE PRIVACY BOUNDARY. See docs/privacy-boundary.md.
#   idx 0 primary   — uplink ON, downlink off   (the only public channel)
#   idx 1 paw-cmd   — uplink OFF, downlink OFF  (C&C: downlink = injection path)
#   idx 2 Techtaria — uplink OFF, downlink OFF  (customer community chat)
echo "-- channel uplink/downlink policy --"
ch_set 0 uplink_enabled true
ch_set 0 downlink_enabled false
ch_set 1 uplink_enabled false
ch_set 1 downlink_enabled false
ch_set 2 uplink_enabled false
ch_set 2 downlink_enabled false

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
  2. channel 1 (paw-cmd) and channel 2 (Techtaria) BOTH show
     uplink_enabled=false AND downlink_enabled=false.
     If either is true, STOP and fix before the node stays up.
  3. Node position appears in the node DB (check --info, NOT --get position,
     which only shows the fixed_position FLAG).
  4. Within ~15-30 min the node should appear on https://meshmap.net/
EOF
