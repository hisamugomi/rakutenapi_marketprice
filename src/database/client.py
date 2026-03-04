"""Supabase client singleton.

Loads credentials from Streamlit secrets (if running inside Streamlit)
or from environment variables (SUPABASE_URL / SERVICEROLE).
Never reads .env files directly.
"""

from __future__ import annotations

import functools
import logging
import os

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def get_supabase_client():
    """Return a cached Supabase client.

    Credential load order:
    1. ``st.secrets["SUPABASE_URL"]`` / ``st.secrets["servicerole"]``
    2. ``os.environ["SUPABASE_URL"]`` / ``os.environ["SERVICEROLE"]``

    Returns:
        Authenticated ``supabase.Client`` instance.

    Raises:
        KeyError: If neither Streamlit secrets nor env vars are configured.
    """
    from supabase import create_client

    try:
        import streamlit as st

        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["servicerole"]
        logger.debug("Supabase client initialised from Streamlit secrets.")
    except Exception:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SERVICEROLE"]
        logger.debug("Supabase client initialised from environment variables.")

    return create_client(url, key)
