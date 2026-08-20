"""The five meal slots, in one place.

This vocabulary was previously repeated three times -- the tuple in
`diary/service.py`, another in `profiles/router.py`, and the default-times dict in
`diary/router.py`. Three copies of the same list is three chances for a slot to
exist in one of them and not the others, which is exactly the drift that makes a
new slot appear in the diary but fail profile validation.
"""

SLOTS = ("breakfast", "snack1", "lunch", "snack2", "dinner")

# The slots a four-meal day leaves out. Only these can be switched off in the
# profile; a main meal that did not happen is a skip for that day, not a standing
# preference about how many times someone eats.
OPTIONAL_SLOTS = frozenset({"snack1", "snack2"})

# Used when a profile has no saved time for a slot -- a profile written before
# the slot existed, rather than a slot the user cleared.
DEFAULT_SLOT_TIMES = {
    "breakfast": "08:00",
    "snack1": "11:00",
    "lunch": "13:30",
    "snack2": "17:00",
    "dinner": "20:30",
}
