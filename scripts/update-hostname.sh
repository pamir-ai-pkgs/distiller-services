#!/bin/bash
# Update hostname based on MAC address for Distiller CM5 services
# This script is called by systemd ExecStartPre to ensure consistent MAC-based hostname

set -e

# Function to get MAC address from network interfaces
get_mac_address() {
    # Priority order: physical ethernet first, then wireless
    for interface in eth0 end0 enp0s3 eno1 wlan0 wlp1s0; do
        if [ -f "/sys/class/net/$interface/address" ]; then
            mac=$(cat "/sys/class/net/$interface/address" 2>/dev/null || true)
            if [ -n "$mac" ] && [ "$mac" != "00:00:00:00:00:00" ]; then
                echo "$mac"
                return 0
            fi
        fi
    done
    
    # Fallback: first non-virtual interface
    for interface in /sys/class/net/*; do
        ifname=$(basename "$interface")
        # Skip virtual interfaces
        case "$ifname" in
            lo|docker*|veth*|br-*|virbr*) continue ;;
        esac
        
        if [ -f "$interface/address" ]; then
            mac=$(cat "$interface/address" 2>/dev/null || true)
            if [ -n "$mac" ] && [ "$mac" != "00:00:00:00:00:00" ]; then
                echo "$mac"
                return 0
            fi
        fi
    done
    
    return 1
}

# Function to generate hostname from MAC address
generate_hostname_from_mac() {
    local mac="$1"
    local prefix="${2:-distiller}"
    
    # Clean MAC address (remove colons and convert to lowercase)
    local clean_mac=$(echo "$mac" | tr '[:upper:]' '[:lower:]' | tr -d ':')
    
    # Use last 4 hex characters for device ID
    local device_id="${clean_mac: -4}"
    
    # Generate hostname
    echo "${prefix}-${device_id}"
}

# Function to update avahi hostname
update_avahi_hostname() {
    local hostname="$1"
    
    if ! systemctl is-active --quiet avahi-daemon; then
        echo "avahi-daemon is not running, skipping hostname update"
        return 0
    fi
    
    # Try using avahi-set-host-name (preferred)
    if command -v avahi-set-host-name >/dev/null 2>&1; then
        if avahi-set-host-name "$hostname" 2>/dev/null; then
            echo "Successfully set avahi hostname using avahi-set-host-name"
            return 0
        else
            echo "avahi-set-host-name failed, falling back to restart"
        fi
    else
        echo "avahi-set-host-name not found, falling back to restart"
    fi
    
    # Fallback: restart avahi-daemon
    if systemctl restart avahi-daemon 2>/dev/null; then
        echo "Restarted avahi-daemon to pick up hostname"
    else
        echo "Warning: Failed to update avahi hostname"
    fi
}

# Main script
main() {
    echo "Checking MAC-based hostname..."
    
    # Get MAC address
    MAC_ADDRESS=$(get_mac_address)
    if [ -z "$MAC_ADDRESS" ]; then
        echo "Warning: Could not detect MAC address, skipping hostname update"
        exit 0
    fi
    
    echo "Detected MAC address: $MAC_ADDRESS"
    
    # Generate expected hostname
    EXPECTED_HOSTNAME=$(generate_hostname_from_mac "$MAC_ADDRESS")
    echo "Expected hostname: $EXPECTED_HOSTNAME"
    
    # Get current hostname
    if command -v hostname >/dev/null 2>&1; then
        CURRENT_HOSTNAME=$(hostname)
    elif [ -f /etc/hostname ]; then
        CURRENT_HOSTNAME=$(cat /etc/hostname)
    else
        echo "Warning: Could not determine current hostname"
        CURRENT_HOSTNAME=""
    fi
    echo "Current hostname: $CURRENT_HOSTNAME"
    
    # Check if hostname needs updating
    if [ "$CURRENT_HOSTNAME" != "$EXPECTED_HOSTNAME" ]; then
        echo "Updating hostname from $CURRENT_HOSTNAME to $EXPECTED_HOSTNAME"
        
        # Update /etc/hostname
        echo "$EXPECTED_HOSTNAME" > /etc/hostname
        
        # Apply hostname immediately
        if command -v hostname >/dev/null 2>&1; then
            hostname "$EXPECTED_HOSTNAME"
        fi
        
        # Update using hostnamectl if available
        if command -v hostnamectl >/dev/null 2>&1; then
            hostnamectl set-hostname "$EXPECTED_HOSTNAME" || true
        fi
        
        # Update /etc/hosts using a temporary file approach to avoid sed permission issues
        update_hosts_file "$EXPECTED_HOSTNAME"
        
        echo "Hostname updated successfully"
        
        # Update avahi to pick up new hostname
        update_avahi_hostname "$EXPECTED_HOSTNAME"
    else
        echo "Hostname is already correct"
    fi
}

# Function to update /etc/hosts with better permission handling
update_hosts_file() {
    local hostname="$1"
    local temp_file="/tmp/hosts.$$"
    
    # Create new hosts file in temp location
    {
        # Copy all lines except 127.0.1.1
        grep -v "^127.0.1.1" /etc/hosts 2>/dev/null || true
        # Add our hostname entry
        echo "127.0.1.1	$hostname"
    } > "$temp_file"
    
    # Replace /etc/hosts atomically
    if [ -f "$temp_file" ]; then
        cp "$temp_file" /etc/hosts && rm -f "$temp_file"
        echo "Updated /etc/hosts successfully"
        return 0
    else
        echo "Warning: Failed to update /etc/hosts"
        return 1
    fi
}

# Run main function
main