"""OSINT web-search enrichment.

Supplements Adata / LSEG with open-source findings strictly across four trigger
categories — sanctions, corruption, reputation, conflict of interest — for the
company, its director and its founders. Facts-only: every finding carries a
source URL, never a score or recommendation.
"""
from app.services.osint.service import is_available, osint_screen

__all__ = ["is_available", "osint_screen"]
