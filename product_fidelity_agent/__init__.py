import base64

import google.adk.telemetry as _adk_telemetry

# ---------------------------------------------------------------------------
# Patch: ADK 0.1.0 telemetry fails to JSON-serialize bytes fields
# (e.g. Part.thought_signature from Gemini thinking mode).
# ---------------------------------------------------------------------------
_orig_build_trace = _adk_telemetry._build_llm_request_for_trace


def _build_llm_request_for_trace_safe(llm_request):
    result = _orig_build_trace(llm_request)

    def _sanitize(obj):
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(i) for i in obj]
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("ascii")
        return obj

    return _sanitize(result)


_adk_telemetry._build_llm_request_for_trace = _build_llm_request_for_trace_safe

from .agent import root_agent
