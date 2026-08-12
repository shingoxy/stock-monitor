"""Compatibility entry point for the former Fuyao synchronization script.

Core tables are now synchronized through structured providers in sync_full.
Keeping a single writer prevents conflicting date/status/unit conventions.
"""
from scripts.sync_full import main


if __name__ == "__main__":
    main()
