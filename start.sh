#!/bin/bash

# Generate machine-id if missing
if [ ! -f /var/lib/dbus/machine-id ]; then
    dbus-uuidgen > /var/lib/dbus/machine-id
fi

# Start dbus
mkdir -p /var/run/dbus
dbus-daemon --system --fork 2>/dev/null || true

# Start pulseaudio
pulseaudio --start --log-target=syslog 2>/dev/null || true

# Start xrdp-sesman first
/usr/sbin/xrdp-sesman --nodaemon &
sleep 1

# Start xrdp foreground — keeps container alive
/usr/sbin/xrdp --nodaemon
