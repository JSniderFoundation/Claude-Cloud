"""NetSuite adapter. Phase 1 ships the fake; phase 2 adds SuiteQL reads and the Payment Hold write-back."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from ..config import settings

log = logging.getLogger("lienwaiver.netsuite")


class NetSuiteAdapter(Protocol):
    def set_vendor_hold(self, vendor_netsuite_id: str | None, vendor_name: str, on_hold: bool, reason: str) -> None: ...


@dataclass
class FakeNetSuite:
    """Records hold calls so the UI and tests can show what would have happened."""

    calls: list[dict] = field(default_factory=list)

    def set_vendor_hold(self, vendor_netsuite_id, vendor_name, on_hold, reason):
        self.calls.append({"netsuite_id": vendor_netsuite_id, "vendor": vendor_name, "on_hold": on_hold, "reason": reason})
        log.info("NetSuite (fake): %s hold for %s (%s): %s", "SET" if on_hold else "CLEAR", vendor_name, vendor_netsuite_id, reason)


class RestNetSuite:
    """Phase 2. Sets the Payment Hold checkbox on the vendor's open bills and stamps the custom
    'Lien Waiver Hold' field so holds AP set for other reasons are never cleared by this tool."""

    def set_vendor_hold(self, vendor_netsuite_id, vendor_name, on_hold, reason):
        raise NotImplementedError("NetSuite REST write-back is phase 2")


_fake = FakeNetSuite()


def get_adapter() -> NetSuiteAdapter:
    if settings.netsuite_backend == "rest":
        return RestNetSuite()
    return _fake
