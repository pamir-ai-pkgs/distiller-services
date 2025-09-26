#!/bin/bash
# MAC-based hostname generator for Distiller CM5 devices

set -e

declare -g PREFIX="${HOSTNAME_PREFIX:-distiller}"
declare -g VERBOSE="${VERBOSE:-false}"

log_error() { echo "ERROR: $*" >&2; }
log_warn() { echo "WARN: $*" >&2; }
log_info() { [[ "$VERBOSE" == "true" ]] && echo "INFO: $*"; }

get_mac_address() {
	# Priority: physical interfaces first, then any non-virtual
	local priority_interfaces="eth0 end0 enp0s3 eno1 wlan0 wlp1s0"
	local mac interface

	for interface in $priority_interfaces; do
		[[ -f "/sys/class/net/$interface/address" ]] || continue
		mac=$(<"/sys/class/net/$interface/address")
		[[ "$mac" != "00:00:00:00:00:00" ]] && echo "$mac" && return 0
	done

	for interface in /sys/class/net/*; do
		[[ -f "$interface/address" ]] || continue
		local name
		name=$(basename "$interface")

		# Skip virtual interfaces
		case "$name" in
		lo | docker* | veth* | br-* | virbr*) continue ;;
		esac

		mac=$(<"$interface/address")
		[[ "$mac" != "00:00:00:00:00:00" ]] && echo "$mac" && return 0
	done

	return 1
}

generate_hostname() {
	local mac="${1,,}" # Convert to lowercase
	mac="${mac//:/}"   # Remove colons
	# Use last 4 hex chars
	echo "${PREFIX}-${mac: -4}"
}

update_system_hostname() {
	local new_hostname="$1"

	echo "$new_hostname" >/etc/hostname
	hostname "$new_hostname"

	# Update via hostnamectl if available
	if command -v hostnamectl &>/dev/null; then
		hostnamectl set-hostname "$new_hostname" || true
	fi

	# Update /etc/hosts entry for local hostname resolution
	sed -i "/^127.0.1.1/d" /etc/hosts
	echo "127.0.1.1	$new_hostname" >>/etc/hosts

	# Notify avahi if running
	if systemctl is-active --quiet avahi-daemon; then
		if command -v avahi-set-host-name &>/dev/null; then
			avahi-set-host-name "$new_hostname" 2>/dev/null ||
				systemctl restart avahi-daemon 2>/dev/null || true
		else
			systemctl restart avahi-daemon 2>/dev/null || true
		fi
		log_info "Updated avahi hostname"
	fi
}

main() {
	[[ "${1:-}" == "-v" || "${1:-}" == "--verbose" ]] && VERBOSE=true

	log_info "Checking MAC-based hostname..."

	# Get MAC address
	if ! MAC_ADDRESS=$(get_mac_address); then
		log_warn "Could not detect MAC address, skipping hostname update"
		exit 0
	fi

	log_info "MAC address: $MAC_ADDRESS"

	# Generate and check hostname
	EXPECTED_HOSTNAME=$(generate_hostname "$MAC_ADDRESS")
	CURRENT_HOSTNAME=$(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null || echo "unknown")

	log_info "Current: $CURRENT_HOSTNAME, Expected: $EXPECTED_HOSTNAME"

	# Update if needed
	if [[ "$CURRENT_HOSTNAME" != "$EXPECTED_HOSTNAME" ]]; then
		update_system_hostname "$EXPECTED_HOSTNAME"
		echo "Hostname updated: $CURRENT_HOSTNAME → $EXPECTED_HOSTNAME"
	else
		log_info "Hostname already correct"
	fi
}

main "$@"
