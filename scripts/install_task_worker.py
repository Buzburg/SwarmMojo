"""Install the credential-free validation service in the operator's user manager."""
import os
from pathlib import Path
import pwd
import subprocess


def install(user: str = 'rryan') -> None:
    if os.geteuid() != 0:
        raise RuntimeError('Install from root inside the Omarchy distribution')
    account = pwd.getpwnam(user)
    home = Path(account.pw_dir)
    directory = home / '.config/systemd/user'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'omarchy-task-worker.service'
    path.write_text('[Unit]\nDescription=Omarchy private rootless validation worker\n'
        '[Service]\nType=simple\nUMask=0077\nRestart=on-failure\nRestartSec=2\n'
        'RuntimeDirectory=omarchy-task-worker\nRuntimeDirectoryMode=0700\n'
        'TimeoutStopSec=45\nKillMode=mixed\n'
        f'ExecStart=/usr/bin/env -i HOME={home} USER={user} LOGNAME={user} PATH=/usr/bin:/bin LANG=C.UTF-8 '
        f'XDG_RUNTIME_DIR=/run/user/{account.pw_uid} DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{account.pw_uid}/bus '
        'ROMS_PYTHON_PREFIX=/opt/roms-env PYTHONUNBUFFERED=1 '
        f'ROMS_DATA_DIR={home}/.local/share/omarchy-harness/roms '
        f'ROMS_WORKSPACES_DIR={home}/.local/share/omarchy-harness/workspaces '
        '/usr/bin/python /opt/omarchy-harness/scripts/run_linux_env.py python -m app.task_worker\n'
        '[Install]\nWantedBy=default.target\n')
    for owned in (directory, path):
        os.chown(owned, account.pw_uid, account.pw_gid)
    subprocess.run(['loginctl', 'enable-linger', user], check=True)
    subprocess.run(['systemctl', 'start', f'user@{account.pw_uid}.service'], check=True)
    manager = ['runuser', '-u', user, '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{account.pw_uid}',
               f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{account.pw_uid}/bus', 'systemctl', '--user']
    subprocess.run([*manager, 'daemon-reload'], check=True)
    subprocess.run([*manager, 'enable', 'omarchy-task-worker.service'], check=True)
    subprocess.run([*manager, 'restart', 'omarchy-task-worker.service'], check=True)
    print('Installed the private validation worker. Verify its actual capabilities before use.')


if __name__ == '__main__':
    install()
