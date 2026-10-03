# SPDX-License-Identifier: GPL-3.0-or-later
"""CI helper: publish the tail of a log as a GitHub error annotation.

Annotations are readable through the REST API (check-runs/{id}/annotations), which
helps when the raw log download is not accessible.
"""

import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else ["<no log>"]
tail = "\n".join(lines[-120:])
encoded = tail.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
print(f"::error title={path.name}::{encoded}")
