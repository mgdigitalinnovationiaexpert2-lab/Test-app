"""Privacy ordering shared across modules."""
from typing import Literal

Capability = str
Intent = Literal["LIGHT", "WORKHORSE", "FRONTIER"]
Privacy = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL"]
PRIVACY_LEVEL = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2}
