"""Package supplied Omarchy 4 userland for WSL, excluding native boot integration."""
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> None:
    workspace = Path(__file__).resolve().parents[2]
    original = Path('/opt/omarchy-iso/var/cache/omarchy/mirror/offline/omarchy-4.0.0-1-any.pkg.tar.zst')
    output = workspace / 'deployment/packages'
    output.mkdir(parents=True, exist_ok=True)
    package = output / 'omarchy-wsl-4.0.0-2-any.pkg.tar.zst'
    with tempfile.TemporaryDirectory(prefix='omarchy-package-') as temporary:
        staging = Path(temporary)
        subprocess.run(['tar', '-xf', str(original), '-C', str(staging),
                        'usr/bin', 'usr/share'], check=True)
        shutil.copytree('/opt/omarchy-iso/usr/share/omarchy', staging / 'usr/share/omarchy', dirs_exist_ok=True)
        for entry in (staging / 'usr/share').iterdir():
            if entry.name not in {'omarchy', 'licenses'}:
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
        # Only selected userland trees enter this variant; no boot/service hooks.
        (staging / '.PKGINFO').write_text(
            'pkgname = omarchy-wsl\npkgver = 4.0.0-2\n'
            'pkgdesc = Custom Omarchy 4 userland for WSL; native desktop and boot integration excluded\n'
            'url = https://github.com/omacom/omarchy\narch = any\nlicense = MIT\n'
            'depend = bash\ndepend = gum\ndepend = jq\ndepend = git\n')
        subprocess.run(['tar', '--zstd', '-cf', str(package), '-C', str(staging), '.PKGINFO', 'usr'], check=True)
    # Migrate our first variant, whose native Omarchy hooks require a different
    # package identity. Suppress only hooks owned by that variant for this upgrade;
    # the corrected package contains none of them. Arch signature policy is unchanged.
    existing = subprocess.run(['pacman', '-Ql', 'omarchy-wsl'], capture_output=True, text=True)
    overrides = []
    try:
        for line in existing.stdout.splitlines():
            installed = Path(line.split(' ', 1)[1])
            if installed.parent == Path('/usr/share/libalpm/hooks') and installed.suffix == '.hook':
                override = Path('/etc/pacman.d/hooks') / installed.name
                override.parent.mkdir(parents=True, exist_ok=True)
                if override.exists() or override.is_symlink():
                    raise RuntimeError(f'Preserve existing hook override: {override}')
                override.symlink_to('/dev/null')
                overrides.append(override)
        subprocess.run(['pacman', '-U', '--noconfirm', str(package)], check=True)
    finally:
        for override in overrides:
            override.unlink()
    home = Path('/home/rryan')
    for name in ('.bashrc', '.bash_profile', '.config'):
        source = Path('/opt/omarchy-iso/etc/skel') / name
        target = home / name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, target)
    Path('/etc/profile.d/omarchy.sh').write_text('. /usr/share/omarchy/default/bash/env-bootstrap\n')
    Path('/etc/omarchy-wsl-release').write_text('Omarchy WSL test build: 4.0.0 userland + Mojo + ROMS + Goose\n'
                                             'Full desktop, disk management and bootloader commands are not supported in WSL.\n')
    Path('/etc/wsl.conf').write_text('[boot]\nsystemd=true\n\n[user]\ndefault=rryan\n\n[network]\nhostname=omarchy\n')
    subprocess.run(['chown', '-R', 'rryan:rryan', str(home)], check=True)
    print(f'Installed custom WSL package: {package}')


if __name__ == '__main__':
    main()
