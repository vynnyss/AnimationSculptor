# SPDX-License-Identifier: GPL-3.0-or-later
import os

import pytest

ADDON_MODULE = os.environ.get("ASC_ADDON_MODULE", "bl_ext.user_default.animation_sculptor")


@pytest.fixture
def addon_module():
    return ADDON_MODULE
