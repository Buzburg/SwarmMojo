#!/usr/bin/env bash
# ==============================================================================
# Omarchy Mojo RWKV7 Harness: Systemd & Environment Setup Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BROKER_BIN="${SCRIPT_DIR}/.pixi/envs/default/bin/omarchy-broker"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
LOCAL_BIN="${HOME}/.local/bin"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/omarchy"

echo "======================================================================"
echo " Omarchy Mojo RWKV7 System Deployment Setup"
echo "======================================================================"

# 1. Verify compiled broker binary
if [[ ! -x "${BROKER_BIN}" ]]; then
    echo "[*] Compiling native Mojo broker binary..."
    if command -v pixi >/dev/null 2>&1; then
        (cd "${SCRIPT_DIR}" && pixi run build-broker)
    else
        echo "[!] pixi not found in PATH. Ensure Pixi is installed."
        exit 1
    fi
fi
echo "[✓] Native broker binary verified: ${BROKER_BIN}"

# 2. Setup runtime directory
mkdir -p "${RUNTIME_DIR}"
chmod 0700 "${RUNTIME_DIR}"
echo "[✓] Runtime socket directory ready: ${RUNTIME_DIR} (0700)"

# 3. Setup CLI harness script
mkdir -p "${LOCAL_BIN}"
cat << 'EOF' > "${LOCAL_BIN}/omarchy-harness"
#!/usr/bin/env bash
SOCKET="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/omarchy/broker.sock"
if [[ ! -S "${SOCKET}" ]]; then
    echo "[!] Broker socket not active at ${SOCKET}" >&2
    echo "    Start the service via: systemctl --user start omarchy-broker" >&2
    exit 1
fi
CMD="${1:-STATUS}"
if [[ "${CMD}" == "{"* ]]; then
    echo "${CMD}" | nc -U "${SOCKET}"
else
    echo "${CMD}" | nc -U "${SOCKET}"
fi
EOF
chmod +x "${LOCAL_BIN}/omarchy-harness"
echo "[✓] CLI harness wrapper installed: ${LOCAL_BIN}/omarchy-harness"

# 4. Generate systemd user unit
mkdir -p "${USER_SYSTEMD_DIR}"
SERVICE_FILE="${USER_SYSTEMD_DIR}/omarchy-broker.service"
cat << EOF > "${SERVICE_FILE}"
[Unit]
Description=Omarchy Mojo Native IPC Broker Daemon
After=network.target

[Service]
Type=simple
ExecStart=${BROKER_BIN}
Environment=OMARCHY_BROKER_SOCKET=%t/omarchy/broker.sock
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=default.target
EOF

echo "[✓] Systemd user service installed: ${SERVICE_FILE}"
echo ""
echo "Deployment Commands for Omarchy / Arch Linux:"
echo "  1. Reload user units:    systemctl --user daemon-reload"
echo "  2. Enable & start:       systemctl --user enable --now omarchy-broker"
echo "  3. Check status:         systemctl --user status omarchy-broker"
echo "  4. Test ping via CLI:    omarchy-harness PING"
echo "======================================================================"
