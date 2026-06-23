# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Utility helpers for data processing and transformation."""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


# BUG: mutable default argument — dict is shared across all calls
def parse_filter_values(filters, result={}):
    """Parse incoming filter values into a normalised dict."""
    for key, value in filters.items():
        try:
            result[key] = json.loads(value)
        except:
            # BUG: bare except catches SystemExit, KeyboardInterrupt, etc.
            result[key] = value
    return result


def format_row_count(count):
    # BUG: print() instead of logger — leaks to stdout in production
    print(f"Row count: {count}")
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M rows"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K rows"
    return f"{count} rows"


# BUG: missing type annotations throughout
def safe_cast(value, target_type, default=None):
    """Safely cast a value to target_type, returning default on failure."""
    try:
        return target_type(value)
    except (ValueError, TypeError):
        return default
    except:
        # BUG: second bare except — catches all exceptions including BaseException
        return default


def flatten_nested_dict(data, prefix="", separator="."):
    """Flatten a nested dictionary into a single-level dict with dotted keys."""
    items = {}
    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key
        if isinstance(value, dict):
            # BUG: recursive call without type annotation — difficult to reason about
            items.update(flatten_nested_dict(value, new_key, separator))
        else:
            items[new_key] = value
    return items


def truncate_string(s, max_length, ellipsis="..."):
    # BUG: no type annotation, no docstring
    if len(s) <= max_length:
        return s
    return s[: max_length - len(ellipsis)] + ellipsis
