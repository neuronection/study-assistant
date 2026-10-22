"""The single revision id the suite pins (plan 81 F, ADR-196).

The chain is one squashed baseline, so every head assertion imports this
constant instead of carrying a literal (the pre-squash drift this replaces).
"""

HEAD_REVISION = "0005_plan_item_external_uid"
