"""Seed the ICMR-NIN 2020 nutrient requirement and upper-limit reference tables.

Every personalised target the app computes is derived from the numbers below, so
transcription accuracy matters more than almost anything else in this codebase.

Sources
-------
- RDA_ROWS (EAR / RDA / AI): ICMR-NIN, "A Brief Note on Nutrient Requirements for
  Indians, the Recommended Dietary Allowances (RDA) and the Estimated Average
  Requirements (EAR), ICMR - NIN, 2020" (the "brief note"), specifically:
    * Table 2a (protein, by sex, EAR/RDA in g/kg/d and g/d)
    * Table 3 (males — calcium, magnesium, iron, zinc, iodine, thiamine,
      riboflavin, niacin, vitamin B6, folate, vitamin B12, vitamin C,
      vitamin A, vitamin D; RDA 2020 and EAR 2020 columns)
    * Table 4 (females — same nutrients as Table 3)
  Retrieved 2026-08-16 from https://www.nin.res.in/rdabook/brief_note.pdf and
  read in full for this verification pass (see "Second verification pass"
  below for exactly what this document does and does not cover).
- UPPER_LIMIT_ROWS: the ICMR upper-limit committee report (2018 Tolerable Upper
  Intake Levels, ICMR-2018-TUL), with IOM (Institute of Medicine) values used
  as an explicit fallback where ICMR has not published a limit (magnesium,
  selenium, copper, manganese, phosphorus) or, for one row, no applicable
  ICMR category exists at all (postmenopausal iron — see below). The TUL
  committee report itself is a gated/paid ICMR publication; it was not
  independently re-fetched in this pass (see caveats below).

Second verification pass (2026-08-16)
--------------------------------------
The brief note PDF above was fetched and read end-to-end and checked against
every RDA_ROWS entry it could possibly cover (the general 18-59 adult, "usual
work"/moderate-activity figures):

  CONFIRMED against Table 2a/3/4, exact match, including the two figures most
  likely to be misremembered from secondary sources — women's zinc RDA is
  13.0 mg (not 13.2, a figure that circulates in some summaries) and vitamin D
  is expressed in the table as 600 IU, i.e. 15 ug, for the general adult band:
    protein (M/F EAR+RDA), calcium (M/F EAR+RDA), magnesium (M/F EAR+RDA),
    iron (M/F EAR+RDA), zinc (M/F EAR+RDA), iodine (M/F EAR+RDA),
    vitamin_a (M/F EAR+RDA), vitamin_d (M/F RDA, 18-59 band only),
    folate (M/F EAR+RDA), vitamin_b12 (M/F EAR+RDA), vitamin_c (M/F EAR+RDA),
    and the "moderate" activity row for thiamine, riboflavin, niacin and
    vitamin_b6 (M/F) — Table 3/4 print exactly one RDA-2020 figure per
    B-vitamin per sex, and it matches this file's "moderate" row in every
    case. The same tables' EAR-2020 column also confirmed, exactly: thiamine
    EAR 1.5/1.4 (M/F), riboflavin 2.1/2.0, niacin 15/12, vitamin_b6 2.1/1.6,
    and vitamin D EAR 400 IU = 10 ug (both sexes) — these are the values
    added in Fix round 1 below (Finding 3), and they were sitting in this
    same PDF the whole time; the first pass simply hadn't transcribed the
    EAR column for these five nutrients.

  NOT covered by the brief note, and NOT independently re-confirmed against a
  freely-available primary source in this pass (the underlying ICMR-NIN 2020
  book that would contain them, and the 2018 TUL committee report, are both
  gated/paid ICMR publications — https://www.nin.res.in only exposes the
  6-page brief note for free):
    * The 60+ age-band rise for calcium (1200) and vitamin_d (20 ug / 800 IU) —
      the brief note gives only one adult figure per nutrient, no elderly
      split.
    * Protein's 60+ rows, which reuse the 18-59 figures.
    * sodium / potassium / selenium AI values — absent from the brief note.
    * All of UPPER_LIMIT_ROWS — the ICMR 2018 TUL committee report was not
      accessible in this session.
  These rows are kept exactly as specified (values and source tags
  unchanged), per an explicit product ruling that reviewed this data set and
  the specific gaps in it (elderly figures, the deliberately-absent UL rows
  for thiamine/riboflavin/biotin/vitamin_b12/potassium, magnesium's
  supplemental-only UL, and the IOM fallback for postmenopausal iron) and
  confirmed them as intentional rather than transcription errors. None are
  marked "UNVERIFIED" because that would both contradict the ruling and break
  the tests that assert their exact source tags.

Fix round 1 (2026-08-16) — three defects found in the transcribed data itself
------------------------------------------------------------------------------
A review of the seeded data (not of this loader's logic) found:

  Finding 1 (Critical) — female vitamin_b6 sedentary was seeded as 1.9,
  identical to its own moderate value, violating the invariant that sedentary
  must sit strictly below moderate — the only one of the 8 B-vitamin
  nutrient/sex pairs where that held. The brief note has no sedentary/heavy
  breakdown for any B vitamin (only the moderate column is published; see
  above), and every other sedentary row in this file sits at ~0.78-0.83x its
  moderate figure, matching ICMR's own sedentary:moderate PAL ratio of
  1.40/1.80 = 0.779. Fixed by setting it to 1.9 x 0.779 = 1.48, rounded to 1.5
  to match the precision of its neighbours. Moderate (1.9) and heavy (2.4)
  were untouched.

  Finding 2 (provenance) — because every sedentary/heavy row in this block is
  derived from the published moderate figure via that PAL ratio rather than
  read off a table, they are now tagged `ICMR_DERIVED`
  ("ICMR-NIN-2020-derived") instead of the plain `ICMR` tag. Only the
  moderate rows — the ones Table 3/4 actually print — keep the plain
  ICMR-NIN-2020 tag. The derivation basis: ICMR's physical activity level
  (PAL) for adults is 1.40 (sedentary) / 1.80 (moderate) / 2.30 (heavy); the
  sedentary and heavy RDA for each B vitamin/sex is the moderate figure
  scaled by (sedentary or heavy PAL) / (moderate PAL) and rounded to one
  decimal place. This mirrors how the postmenopausal iron row carries `IOM`
  rather than pretending to be ICMR — a distinct tag wherever the number
  didn't come directly off a published ICMR table.

  Finding 3 (Important) — thiamine, riboflavin, niacin, vitamin_b6 and
  vitamin_d all have a published EAR in Table 3/4, but every row for these
  five had been seeded with ear=None, leaving the adequacy floor undefined
  for exactly the nutrients the compensation engine most needs it for. Added
  from the EAR-2020 column (see "CONFIRMED" above). Row placement: the
  brief note's EAR is not stratified by activity level (one number per
  nutrient per sex, unlike RDA which has a distinct figure per PAL band), so
  the same published EAR is attached to all three activity rows (sedentary/
  moderate/heavy) for a given nutrient and sex — the floor a target must
  never be pushed below doesn't change with which activity band the target
  itself uses. Vitamin D's EAR (10 ug) likewise has no age-band split in the
  source, so it is attached to both the 18-59 and 60+ rows for both sexes.
  One consequence worth flagging: the sedentary/heavy B-vitamin rows now
  carry a directly-published EAR alongside a PAL-derived RDA under the same
  `source` tag. The schema has one `source` field per row, not one per
  column, and `ICMR_DERIVED` was chosen to describe the row's RDA (the
  figure Finding 1/2 were about) — it is not a claim that every number on
  that row was extrapolated.

  Finding 4 (test coverage) — `test_b_vitamins_are_indexed_by_activity` only
  pinned the sedentary < moderate invariant for thiamine/male, which is how
  Finding 1 passed silently. Extended to check all four B vitamins x both
  sexes.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit

ICMR = "ICMR-NIN-2020"
# The brief note publishes only the moderate-activity RDA for the four
# energy-scaled B vitamins. Sedentary/heavy figures are extrapolated from it
# via ICMR's own PAL ratios (sedentary 1.40 / moderate 1.80 / heavy 2.30 —
# see the docstring's "Fix round 1" section) rather than read off a table, so
# they carry this distinct tag instead of pretending to be a published value.
ICMR_DERIVED = "ICMR-NIN-2020-derived"
ICMR_TUL = "ICMR-2018-TUL"
IOM = "IOM"

# (nutrient, sex, age_band, activity, ear, rda, ai, source)
# Activity is set only for the four energy-scaled B vitamins. The commonly
# quoted ICMR B-vitamin numbers are the MODERATE column; applying them to a
# sedentary user over-targets by roughly 25%.
RDA_ROWS: list[tuple] = [
    ("protein", "male", "18-59", None, 42.9, 54.0, None, ICMR),
    ("protein", "female", "18-59", None, 36.3, 45.7, None, ICMR),
    ("protein", "male", "60+", None, 42.9, 54.0, None, ICMR),
    ("protein", "female", "60+", None, 36.3, 45.7, None, ICMR),

    ("calcium", "male", "18-59", None, 800, 1000, None, ICMR),
    ("calcium", "female", "18-59", None, 800, 1000, None, ICMR),
    ("calcium", "male", "60+", None, 800, 1200, None, ICMR),
    ("calcium", "female", "60+", None, 800, 1200, None, ICMR),

    ("iron", "male", "18-59", None, 11, 19, None, ICMR),
    ("iron", "female", "18-59", None, 15, 29, None, ICMR),
    ("iron", "male", "60+", None, 11, 19, None, ICMR),
    # ICMR publishes no postmenopausal category; the spec requires falling
    # back to the IOM value rather than applying the menstruating figure.
    ("iron", "female", "60+", None, 5, 8, None, IOM),

    ("magnesium", "male", "18-59", None, 370, 440, None, ICMR),
    ("magnesium", "female", "18-59", None, 310, 370, None, ICMR),
    ("zinc", "male", "18-59", None, 14, 17, None, ICMR),
    ("zinc", "female", "18-59", None, 11, 13.0, None, ICMR),
    ("iodine", "male", "18-59", None, 95, 150, None, ICMR),
    ("iodine", "female", "18-59", None, 95, 150, None, ICMR),
    ("sodium", "male", "18-59", None, None, None, 2000, ICMR),
    ("sodium", "female", "18-59", None, None, None, 2000, ICMR),
    ("potassium", "male", "18-59", None, None, None, 3510, ICMR),
    ("potassium", "female", "18-59", None, None, None, 3510, ICMR),
    ("selenium", "male", "18-59", None, None, None, 40, ICMR),
    ("selenium", "female", "18-59", None, None, None, 40, ICMR),

    ("vitamin_a", "male", "18-59", None, 460, 1000, None, ICMR),
    ("vitamin_a", "female", "18-59", None, 390, 840, None, ICMR),
    # EAR 2020 = 10 ug (400 IU) — the brief note gives one EAR figure with no
    # age-band split, so it is applied to both the 18-59 and 60+ rows below.
    ("vitamin_d", "male", "18-59", None, 10, 15, None, ICMR),   # 600 IU
    ("vitamin_d", "female", "18-59", None, 10, 15, None, ICMR),
    ("vitamin_d", "male", "60+", None, 10, 20, None, ICMR),     # 800 IU
    ("vitamin_d", "female", "60+", None, 10, 20, None, ICMR),
    ("folate", "male", "18-59", None, 250, 300, None, ICMR),
    ("folate", "female", "18-59", None, 180, 220, None, ICMR),
    ("vitamin_b12", "male", "18-59", None, 2.0, 2.2, None, ICMR),
    ("vitamin_b12", "female", "18-59", None, 2.0, 2.2, None, ICMR),
    ("vitamin_c", "male", "18-59", None, 65, 80, None, ICMR),
    ("vitamin_c", "female", "18-59", None, 55, 65, None, ICMR),

    # Energy-scaled B vitamins, by activity level. The moderate-activity RDA
    # (and its matching EAR) is the one figure the brief note actually
    # publishes; sedentary and heavy are derived from it via ICMR's PAL
    # ratios (see ICMR_DERIVED above) and tagged accordingly. Each nutrient's
    # EAR is not activity-stratified in the source, so the same published EAR
    # is attached to all three activity rows for a given sex — the adequacy
    # floor does not depend on which activity band a user's target uses.
    ("thiamine", "male", "18-59", "sedentary", 1.5, 1.4, None, ICMR_DERIVED),
    ("thiamine", "male", "18-59", "moderate", 1.5, 1.8, None, ICMR),
    ("thiamine", "male", "18-59", "heavy", 1.5, 2.3, None, ICMR_DERIVED),
    ("thiamine", "female", "18-59", "sedentary", 1.4, 1.4, None, ICMR_DERIVED),
    ("thiamine", "female", "18-59", "moderate", 1.4, 1.7, None, ICMR),
    ("thiamine", "female", "18-59", "heavy", 1.4, 2.2, None, ICMR_DERIVED),
    ("riboflavin", "male", "18-59", "sedentary", 2.1, 2.0, None, ICMR_DERIVED),
    ("riboflavin", "male", "18-59", "moderate", 2.1, 2.5, None, ICMR),
    ("riboflavin", "male", "18-59", "heavy", 2.1, 3.2, None, ICMR_DERIVED),
    ("riboflavin", "female", "18-59", "sedentary", 2.0, 1.9, None, ICMR_DERIVED),
    ("riboflavin", "female", "18-59", "moderate", 2.0, 2.4, None, ICMR),
    ("riboflavin", "female", "18-59", "heavy", 2.0, 3.1, None, ICMR_DERIVED),
    ("niacin", "male", "18-59", "sedentary", 15, 14, None, ICMR_DERIVED),
    ("niacin", "male", "18-59", "moderate", 15, 18, None, ICMR),
    ("niacin", "male", "18-59", "heavy", 15, 23, None, ICMR_DERIVED),
    ("niacin", "female", "18-59", "sedentary", 12, 11, None, ICMR_DERIVED),
    ("niacin", "female", "18-59", "moderate", 12, 14, None, ICMR),
    ("niacin", "female", "18-59", "heavy", 12, 18, None, ICMR_DERIVED),
    ("vitamin_b6", "male", "18-59", "sedentary", 2.1, 1.9, None, ICMR_DERIVED),
    ("vitamin_b6", "male", "18-59", "moderate", 2.1, 2.4, None, ICMR),
    ("vitamin_b6", "male", "18-59", "heavy", 2.1, 3.1, None, ICMR_DERIVED),
    # Female B6 sedentary was mistranscribed as 1.9 (identical to moderate,
    # violating sedentary < moderate). Corrected to 1.9 x 0.779 = 1.48 -> 1.5,
    # the same sedentary:moderate PAL ratio (1.40/1.80) used for every other
    # row in this block.
    ("vitamin_b6", "female", "18-59", "sedentary", 1.6, 1.5, None, ICMR_DERIVED),
    ("vitamin_b6", "female", "18-59", "moderate", 1.6, 1.9, None, ICMR),
    ("vitamin_b6", "female", "18-59", "heavy", 1.6, 2.4, None, ICMR_DERIVED),
]

# (nutrient, value, supplemental_only, source)
UPPER_LIMIT_ROWS: list[tuple] = [
    ("iron", 45, False, ICMR_TUL),
    ("zinc", 40, False, ICMR_TUL),
    ("calcium", 2500, False, ICMR_TUL),
    ("iodine", 900, False, ICMR_TUL),
    ("vitamin_a", 3000, False, ICMR_TUL),
    ("vitamin_d", 100, False, ICMR_TUL),
    ("vitamin_e", 1000, False, ICMR_TUL),
    ("niacin", 35, False, ICMR_TUL),
    ("vitamin_b6", 100, False, ICMR_TUL),
    ("folate", 1000, False, ICMR_TUL),
    ("vitamin_c", 2000, False, ICMR_TUL),
    # Supplemental only — excludes food and water. Warning on dietary
    # magnesium would be a bug.
    ("magnesium", 350, True, IOM),
    ("selenium", 400, False, IOM),
    ("copper", 10, False, IOM),
    ("manganese", 11, False, IOM),
    ("phosphorus", 4000, False, IOM),
    # Deliberately absent, because ICMR set none: thiamine, riboflavin,
    # biotin, vitamin_b12, potassium.
]


def seed_reference(db: Session) -> tuple[int, int]:
    """Insert or update the RDA and upper-limit reference rows. Safe to re-run."""
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}

    for code, sex, age_band, activity, ear, rda, ai, source in RDA_ROWS:
        nutrient = nutrients.get(code)
        if nutrient is None:
            continue
        row = db.scalar(
            select(RdaReference).where(
                RdaReference.nutrient_id == nutrient.id,
                RdaReference.sex == sex,
                RdaReference.age_band == age_band,
                RdaReference.activity_level == activity,
            )
        )
        if row is None:
            row = RdaReference(
                nutrient_id=nutrient.id, sex=sex, age_band=age_band, activity_level=activity
            )
            db.add(row)
        row.ear, row.rda, row.ai, row.source = ear, rda, ai, source

    for code, value, supplemental_only, source in UPPER_LIMIT_ROWS:
        nutrient = nutrients.get(code)
        if nutrient is None:
            continue
        row = db.scalar(
            select(UpperLimit).where(
                UpperLimit.nutrient_id == nutrient.id, UpperLimit.age_band == "adult"
            )
        )
        if row is None:
            row = UpperLimit(nutrient_id=nutrient.id, age_band="adult")
            db.add(row)
        row.value, row.supplemental_only, row.source = value, supplemental_only, source

    db.flush()
    return len(RDA_ROWS), len(UPPER_LIMIT_ROWS)
