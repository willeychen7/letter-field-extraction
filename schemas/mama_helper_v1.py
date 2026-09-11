"""
Fixed prompt + JSON schema for Mama Helper's core letter-understanding
fields, v1.

Design rationale (from hunyuan-experiment/ testing history, see
../docs/findings.md):
  - Uses the OFFICIAL Information Extraction template pattern (Tencent-
    Hunyuan README "Application-oriented Prompts" table): "提取图片中的:
    [keys] 的字段内容，并按照JSON格式返回。" -- this pattern gave 100%
    valid-JSON output across a 20-real-letter test, far more stable than
    doc_parse/spotting_json (40-60% format compliance).
  - `sender` and `recipient_name` are asked in the SAME request here (v1),
    matching the original 9-field IE test where sender/recipient direction
    was wrong in 6/10 ground-truth-checkable cases. The split-request
    variant (ask separately) showed better direction accuracy in isolated
    spot checks but has NOT been validated on the full ground-truth batch
    yet -- that is exactly what the Phase 1 evaluation in
    evaluation/mama_helper_v1_eval/ is for. Do not assume v1 is final;
    it is the baseline this schema's own evaluation is measured against.
  - Every field must be null when not present in the image -- the prompt
    says so explicitly, but empirically the model sometimes emits the
    Python-style string "None" instead of JSON null. normalize_fields()
    below corrects that at the parsing layer only (never invents a value).
"""

import json
import re

FIELDS = [
    "document_type",
    "sender",
    "recipient_name",
    "amount",
    "due_date",
    "is_action_required",
    "action_cn",
    "risk_cn",
    "summary_cn",
]

PROMPT = (
    "提取图片中的: ['" + "', '".join(FIELDS) + "'] 的字段内容，"
    "并按照JSON格式返回。如果某个字段在图片中确实不存在，必须返回 null，"
    "不要猜测，也不要用其他字段的内容代替。"
)

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_NULL_STRINGS = {"none", "null", "n/a", "", "unknown", "未知"}


def _strip_code_fence(content: str) -> str:
    m = _FENCE_PATTERN.search(content)
    return m.group(1) if m else content


def normalize_fields(data: dict) -> dict:
    """Map string "None"/"null"/"" etc. to real None. Never fills a value
    that wasn't already present -- this is normalization, not imputation.
    """
    out = {}
    for key in FIELDS:
        val = data.get(key)
        if isinstance(val, str) and val.strip().lower() in _NULL_STRINGS:
            val = None
        out[key] = val
    return out


def parse_model_output(content: str) -> tuple[dict | None, str]:
    """Returns (normalized_fields_or_None, parse_status).

    parse_status in {"valid_json_object", "valid_json_wrong_shape", "parse_failed"}.
    This function ONLY reads structure -- it does not validate field
    correctness (amount plausibility, date ordering, sender-looks-like-a-
    person-name, etc.). Those checks belong to a separate validation layer
    that should reuse mama-helper's existing fieldExtractor.js logic
    (ported or called out to), not be reimplemented here with new regex.
    """
    unfenced = _strip_code_fence(content)
    try:
        data = json.loads(unfenced)
    except (json.JSONDecodeError, TypeError):
        return None, "parse_failed"

    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]

    if not isinstance(data, dict):
        return None, "valid_json_wrong_shape"

    return normalize_fields(data), "valid_json_object"
