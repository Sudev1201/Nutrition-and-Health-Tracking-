"""The guard on AI text, and the fingerprint of what a cached text was written from.

Pure: no database and no provider. The guard is the only thing standing between
a model's answer and the Plan screen, beside the planner's portion and rationale,
so every class of word it refuses is pinned here, along with what it must let
through.
"""

import hashlib

import pytest

from app.llm.providers import PROMPT_VERSION
from app.planner import polish
from app.planner.polish import BANNED_WORDS, MAX_TEXT, brief_hash, clean

# --- what is kept ------------------------------------------------------------------------


def test_clean_prose_is_kept_stripped():
    assert clean("  Soft, steamed rice cakes with a gentle tang.\n") == (
        "Soft, steamed rice cakes with a gentle tang."
    )


@pytest.mark.parametrize("text", [None, "", "   ", "\n\t  "])
def test_nothing_is_not_text(text):
    assert clean(text) is None


def test_the_limit_is_280_characters_after_stripping():
    assert MAX_TEXT == 280
    at_limit = "x" * 280

    assert clean(at_limit) == at_limit
    assert clean(f"   {at_limit}   ") == at_limit
    assert clean("x" * 281) is None


# --- numbers, in digits or in words -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Use 500 g of rice",
        "Ready in 5 minutes",
        "Covers 90% of your calcium",
        "Best eaten on day 2",
        # Any numeric character, not only 0-9: an Arabic-Indic five, a half, a square.
        "Ready in ٥ minutes",
        "Squeeze ½ a lemon over it",
        "Serve warm²",
    ],
)
def test_a_digit_or_any_numeric_character_is_refused(text):
    assert clean(text) is None


def test_a_percent_sign_is_refused_on_its_own():
    assert clean("A high % of it is rice") is None


@pytest.mark.parametrize(
    "text",
    [
        "Serves two happily",
        "Ready in ten minutes",
        "Simmer for fifteen minutes",
        "Ninety seconds in hot oil is enough",
        "Half a lemon over the top lifts it",
        "A dozen curry leaves make it",
        "A hundred percent comfort",
    ],
)
def test_a_number_in_words_is_refused(text):
    assert clean(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Double the dal for a heartier bowl",
        "Twice the rice keeps it mild",
        "Halve the rice and add more greens",
    ],
)
def test_a_multiplier_is_refused(text):
    # No number in it, and still a change to the planner's portion.
    assert clean(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "A cup of rice to start",
        "A teaspoon of ghee on top",
        "Measure out the grams carefully",
        "A generous serving with chutney",
        "Keep the portion small",
        "Low in calories",
        # The household measures the planner's own portions are written in.
        "A katori of curd on the side",
        "A tumbler of buttermilk after",
        "A ladle of sambar over the rice",
        "Have a bowl of this with a glass of buttermilk",
        "Serve it in bowls with chutney",
        "Pour it into glasses to set",
        "A piece of jaggery on the side",
        "Cut it into pieces while warm",
    ],
)
def test_a_unit_or_a_measure_is_refused(text):
    assert clean(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Packed with protein",
        "A good source of calcium",
        "Rich in vitamins",
        "High in fibre and filling",
        "Very nutritious",
        "Light on carbs",
    ],
)
def test_a_nutrient_claim_is_refused(text):
    assert clean(text) is None


@pytest.mark.parametrize("word", sorted(BANNED_WORDS))
def test_every_banned_word_is_refused_in_any_case(word):
    for form in (word, word.upper(), word.capitalize()):
        assert clean(f"Made with {form} in mind") is None, form


# --- whole words only ---------------------------------------------------------------------
#
# A word is a run of ASCII letters. So a banned word inside a longer word is
# not that word ("someone", "stone", "honey", "soften"), while a banned word
# joined by a hyphen is still a word of its own ("one-pot").


@pytest.mark.parametrize(
    "text",
    [
        "Cook it in a cast-iron pan.",
        "Someone always asks for more.",
        "A stone-ground batter makes it lighter.",
        "Finish with a little honey.",
        "Soften the onions first.",
        "Often served at breakfast.",
        "A glassy sheen on the onions.",
        "A little masterpiece of a breakfast.",
    ],
)
def test_a_banned_word_inside_a_longer_word_does_not_count(text):
    assert clean(text) == text


def test_a_hyphenated_number_word_still_counts():
    assert clean("A one-pot dinner.") is None


def test_the_pulses_called_gram_are_ingredients_not_units():
    # IFCT names the pulses in most seeded recipes "Bengal gram", "Black gram",
    # "Green gram" and "Red gram", and the model is shown those names.
    assert "gram" not in BANNED_WORDS
    assert clean("Soaked Bengal gram tossed with grated coconut.") == (
        "Soaked Bengal gram tossed with grated coconut."
    )


@pytest.mark.parametrize("word", ["bowl", "bowls", "glass", "glasses", "piece", "pieces"])
def test_the_planners_generic_measures_are_banned(word):
    # The seeded recipes and foods.measures.GENERIC_MEASURES write portions in these.
    assert word in BANNED_WORDS
    for form in (word, word.upper(), word.capitalize()):
        assert clean(f"Serve it with a {form} of buttermilk.") is None, form


def test_iron_is_left_for_the_pan():
    assert "iron" not in BANNED_WORDS


# --- the fingerprint ----------------------------------------------------------------------


def test_the_fingerprint_is_a_sha256_of_exactly_what_was_sent():
    expected = hashlib.sha256(
        f"v{PROMPT_VERSION}\nIdli\nBlack gram, dal\nRice, parboiled, milled".encode()
    ).hexdigest()

    assert brief_hash("Idli", ("Black gram, dal", "Rice, parboiled, milled")) == expected


def test_the_fingerprint_is_stable():
    ingredients = ("Black gram, dal", "Rice, parboiled, milled")

    assert brief_hash("Idli", ingredients) == brief_hash("Idli", list(ingredients))
    assert len(brief_hash("Idli", ingredients)) == 64


@pytest.mark.parametrize(
    ("name", "ingredients"),
    [
        ("Rava idli", ("Black gram, dal", "Rice, parboiled, milled")),
        ("Idli", ("Black gram, whole", "Rice, parboiled, milled")),
        ("Idli", ("Black gram, dal",)),
        ("Idli", ("Black gram, dal", "Fenugreek seeds", "Rice, parboiled, milled")),
    ],
)
def test_the_fingerprint_changes_with_the_name_or_any_ingredient(name, ingredients):
    original = brief_hash("Idli", ("Black gram, dal", "Rice, parboiled, milled"))

    assert brief_hash(name, ingredients) != original


def test_a_new_prompt_version_changes_every_fingerprint(monkeypatch):
    before = brief_hash("Idli", ("Black gram, dal",))

    monkeypatch.setattr(polish, "PROMPT_VERSION", PROMPT_VERSION + 1)

    assert brief_hash("Idli", ("Black gram, dal",)) != before
