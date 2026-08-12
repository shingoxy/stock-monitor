"""Compatibility entry point for the former iFinD search-based importer.

Natural-language search results are not safe as authoritative database rows;
use the structured full synchronization pipeline instead.
"""
from scripts.sync_full import main


if __name__ == "__main__":
    main()
