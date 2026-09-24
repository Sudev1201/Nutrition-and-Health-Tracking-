"""What cycle data means, pure.

Three jobs: find the bleeds in a run of logged days, decide whether anything the
user reported calls for a clinician, and choose which coaching applies. None of
it produces a number the targets use. The iron target already averages menstrual
loss and the calorie target does not move with cycle phase (spec, section 8), so
this module has no path to either -- by construction, not by care.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

FLOWS = ("light", "medium", "heavy")

# The symptoms the coaching responds to. No cravings: the perimenstrual chocolate
# script is largely an American cultural artefact, and has no place here.
SYMPTOMS = ("cramps", "bloating", "breast_tenderness", "low_mood")
PMS_SYMPTOMS = frozenset({"bloating", "breast_tenderness", "low_mood"})
SYMPTOM_WORDS = {
    "cramps": "cramps",
    "bloating": "bloating",
    "breast_tenderness": "breast tenderness",
    "low_mood": "low mood",
}

# Bleeding on more than seven consecutive days is one of the validated
# heavy-bleeding signals, and the one the logs can show without asking.
LONG_BLEED_DAYS = 7
# How far back the logs are read, for display and for the signal above.
HISTORY_DAYS = 90
# "Around menstruation", for the vitamin C pairing.
RECENT_BLEED_DAYS = 7
# How far back logged PMS symptoms are named in the calcium note.
PMS_LOOKBACK_DAYS = 30
# Ginger and fenugreek were trialled on days 1-3 of menses only.
EARLY_BLEED_DAYS = 3

SCREENING_REASONS = (
    (
        "soaks_within_two_hours",
        "You reported soaking through a pad or tampon in two hours or less.",
    ),
    ("longer_than_seven_days", "You reported periods that last more than seven days."),
    ("large_clots", "You reported passing clots larger than a ₹10 coin."),
    ("flooding", "You reported flooding through to clothes or bedding."),
)


@dataclass(frozen=True)
class Day:
    date: datetime.date
    flow: str | None
    symptoms: frozenset[str]


@dataclass(frozen=True)
class Screening:
    answered_on: datetime.date
    soaks_within_two_hours: bool
    longer_than_seven_days: bool
    large_clots: bool
    flooding: bool


@dataclass(frozen=True)
class Bleed:
    start: datetime.date
    end: datetime.date

    @property
    def length(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    body: str
    evidence: str  # strong | moderate | low | traditional


COFFEE_TIMING = Note(
    id="coffee-timing",
    title="Keep coffee and tea an hour away from meals",
    body=(
        "In young Indian women, one cup of tea with a rice meal cut iron absorption by about "
        "49%, and two cups by about 67%. A one-hour gap roughly halves that."
    ),
    evidence="strong",
)

VITAMIN_C = Note(
    id="vitamin-c",
    title="Pair iron-rich meals with lemon, tomato, tamarind, amla or guava",
    body=(
        "Around your period, have something rich in vitamin C with the meal that carries your "
        "iron: it markedly improves how much of the iron in a rice-and-dal meal is absorbed. "
        "The mechanism is well established. This changes what to eat alongside, not how much "
        "iron you need."
    ),
    evidence="moderate",
)

GINGER = Note(
    id="ginger",
    title="Dry ginger (sukku), 750–2,000 mg a day on days 1–3",
    body=(
        "About half to one level teaspoon of dry ginger powder a day (a level teaspoon is "
        "roughly 1.8 g), split across meals, on the first three days of your period only. It "
        "compared well with mefenamic acid and ibuprofen in head-to-head trials for period "
        "pain, but painkillers such as ibuprofen still work better than any food. This is not "
        "a substitute for treatment."
    ),
    evidence="moderate",
)

FENUGREEK = Note(
    id="fenugreek",
    title="Fenugreek (methi) seed powder, 2.7–4 g a day on days 1–3",
    body=(
        "About one level teaspoon of powder a day, on the first three days, over two cycles. "
        "One small trial supports it, and it was of low quality: something to try, not a "
        "treatment."
    ),
    evidence="low",
)

CALCIUM_BODY = (
    "The only nutrient both ACOG and RCOG endorse for PMS. Typical intake among Indian women "
    "is around 270–500 mg a day. The trial took three cycles to show benefit, so give it time."
)

# Said whenever PMS symptoms were logged: severe PMS, and the low mood of PMDD
# especially, has effective clinical treatment, and a nutrient is not it.
PMS_TREATMENT = (
    "If these symptoms are severe or get in the way of daily life, low mood especially, see "
    "a clinician: there are effective treatments, and calcium is not a substitute for them."
)


def bleeds(days: Sequence[Day]) -> list[Bleed]:
    """Runs of consecutive logged bleeding days, oldest first."""
    runs: list[Bleed] = []
    for date in sorted(d.date for d in days if d.flow is not None):
        if runs and date - runs[-1].end == datetime.timedelta(days=1):
            runs[-1] = Bleed(runs[-1].start, date)
        else:
            runs.append(Bleed(date, date))
    return runs


def last_period_start(days: Sequence[Day]) -> datetime.date | None:
    runs = bleeds(days)
    return runs[-1].start if runs else None


def bleed_day(days: Sequence[Day], today: datetime.date) -> int | None:
    """Which day of a bleed today is, counting from logged bleeding: 1 on its first day.

    A bleed is current if it was logged today or yesterday -- today's log may simply
    not be in yet. Anything older is not current, and nothing is predicted.
    """
    runs = [run for run in bleeds(days) if run.start <= today]
    if not runs or (today - runs[-1].end).days > 1:
        return None
    return (today - runs[-1].start).days + 1


def referral_reason(
    days: Sequence[Day], screening: Screening | None, today: datetime.date
) -> str | None:
    """Why a clinician should see this, in whole sentences -- or None.

    Never a nutrient change. Flow logged as "heavy" is not on its own a trigger:
    it is a self-rating, not one of the validated questions.
    """
    reasons = []
    if screening is not None:
        reasons += [text for field, text in SCREENING_REASONS if getattr(screening, field)]

    recent = [run for run in bleeds(days) if 0 <= (today - run.end).days <= HISTORY_DAYS]
    long_runs = [run for run in recent if run.length > LONG_BLEED_DAYS]
    if long_runs:
        reasons.append(f"You logged bleeding on {long_runs[-1].length} days in a row.")

    return " ".join(reasons) if reasons else None


def coaching(days: Sequence[Day], today: datetime.date) -> list[Note]:
    """The notes that apply today, most broadly useful first."""
    notes = [COFFEE_TIMING]

    runs = [run for run in bleeds(days) if run.start <= today]
    if runs and (today - runs[-1].end).days < RECENT_BLEED_DAYS:
        notes.append(VITAMIN_C)

    current = bleed_day(days, today)
    if current is not None and current <= EARLY_BLEED_DAYS:
        started = today - datetime.timedelta(days=current - 1)
        if any("cramps" in d.symptoms for d in days if started <= d.date <= today):
            notes += [GINGER, FENUGREEK]

    pms = {
        symptom
        for d in days
        if 0 <= (today - d.date).days <= PMS_LOOKBACK_DAYS
        for symptom in d.symptoms
        if symptom in PMS_SYMPTOMS
    }
    notes.append(_calcium(pms))
    return notes


def _calcium(pms: set[str]) -> Note:
    body = CALCIUM_BODY
    if pms:
        named = _join([SYMPTOM_WORDS[s] for s in SYMPTOMS if s in pms])
        body = f"You logged {named} recently. {CALCIUM_BODY} {PMS_TREATMENT}"
    return Note(
        id="calcium", title="Calcium at 1,000–1,200 mg a day", body=body, evidence="moderate"
    )


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} and {words[-1]}"
