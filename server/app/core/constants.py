"""
Cross-cutting application-level constants.
"""

# Sentinel value used by clients to indicate "filter records whose group field
# is NULL/empty". Chosen to be unlikely to collide with real custom-field data.
EMPTY_GROUP_VALUE = "__EMPTY__"
