
# ---------------------------------------------------------
# SERVICE: Sales Analytics Cache
# Purpose:
# Store recently requested sales analytics results.
# Avoid repeated database queries for identical requests.
#
# Features:
# 1. In-memory caching.
# 2. 30-second automatic expiry.
# 3. Cache invalidation after successful sales.
# 4. Thread-safe cache access.
# ---------------------------------------------------------

import time
import threading
from copy import deepcopy


# Cache configuration
CACHE_TTL_SECONDS = 30


# Internal cache storage
_analytics_cache = {}

# Thread synchronization
_cache_lock = threading.RLock()


# ---------------------------------------------------------
# FUNCTION: Get Cached Analytics
# Purpose:
# Retrieve an analytics result if it exists and has not expired.
# ---------------------------------------------------------

def get_cached_analytics(cache_key: str):

    with _cache_lock:

        cached_entry = _analytics_cache.get(cache_key)

        if cached_entry is None:
            return None

        cached_time, cached_data = cached_entry

        # Check cache expiry
        if time.monotonic() - cached_time >= CACHE_TTL_SECONDS:

            _analytics_cache.pop(cache_key, None)

            return None

        return deepcopy(cached_data)


# ---------------------------------------------------------
# FUNCTION: Store Analytics in Cache
# Purpose:
# Store a copy of verified analytics data with its timestamp.
# ---------------------------------------------------------

def set_cached_analytics(cache_key: str, data: dict):

    with _cache_lock:

        _analytics_cache[cache_key] = (
            time.monotonic(),
            deepcopy(data)
        )


# ---------------------------------------------------------
# FUNCTION: Invalidate Analytics Cache
# Purpose:
# Clear cached sales analytics after a successful sale.
# ---------------------------------------------------------

def invalidate_sales_analytics_cache():

    with _cache_lock:

        _analytics_cache.clear()

        print("Sales analytics cache invalidated.")
