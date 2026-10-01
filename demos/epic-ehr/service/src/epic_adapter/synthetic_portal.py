"""Compatibility entry point: the synthetic target is now the clinician EMR."""
from __future__ import annotations

from .synthetic_emr import Handler, main

__all__ = ["Handler", "main"]

if __name__ == "__main__":
    main()
