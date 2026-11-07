"""OS adapters (SPEC §12.7). `get_adapter(dry_run)` picks by platform.system()."""

from __future__ import annotations

import platform

from roomservice.contracts.os import OSAdapter


def get_adapter(dry_run: bool) -> OSAdapter:
    if dry_run:
        from roomservice.desk.os.dry import DryAdapter

        return DryAdapter()
    system = platform.system()
    if system == "Darwin":
        from roomservice.desk.os.macos import MacOSAdapter

        return MacOSAdapter()
    if system == "Windows":
        from roomservice.desk.os.windows import WindowsAdapter

        return WindowsAdapter()
    from roomservice.desk.os.linux import LinuxAdapter

    return LinuxAdapter()
