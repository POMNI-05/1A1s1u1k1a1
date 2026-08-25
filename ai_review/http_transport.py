"""Small standard-library JSON HTTP transport for AI provider adapters."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from .providers import AIReviewProviderError


class UrllibJsonTransport:
    """JSON transport with bounded timeout and diagnostic-free API-key handling."""

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise AIReviewProviderError(f"AI provider HTTP error: {exc.code}") from exc
        except OSError as exc:
            raise AIReviewProviderError("AI provider request failed") from exc
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AIReviewProviderError("AI provider returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise AIReviewProviderError("AI provider response must be an object")
        return decoded
