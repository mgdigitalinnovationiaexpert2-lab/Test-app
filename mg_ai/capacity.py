"""Compatibility re-export; capacity logic lives in mg_ai.common.capacity."""
from mg_ai.common.capacity import (Capacity, duration, fingerprint, groq_capacity, main,
                                   number, openrouter_capacity, refresh_openrouter)

__all__ = ["Capacity", "duration", "fingerprint", "groq_capacity", "main", "number",
           "openrouter_capacity", "refresh_openrouter"]
