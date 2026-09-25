"""Model registry.

Importing this package registers every model on `Base.metadata`. Alembic and
the test fixtures both import from here rather than from individual modules,
so metadata is always complete no matter which entry point loaded first —
otherwise `create_all`/`drop_all` and autogenerate silently miss tables.
"""

from app.models.base import Base
from app.models.cycle import CycleLog, CycleScreening, CycleSettings, CycleSymptom
from app.models.diary import MealLog, MealSlotSkip
from app.models.food import (
    Dish,
    DishIngredient,
    DishNutrient,
    Ingredient,
    IngredientNutrient,
    PortionMeasure,
)
from app.models.household import Household, HouseholdInvite, HouseholdMember
from app.models.llm import DishPolish, UserSettings
from app.models.nutrient import Nutrient
from app.models.plan import MealPlan, MealPlanItem
from app.models.profile import (
    AvoidedFood,
    FavouriteIngredient,
    HealthCondition,
    MealSlotTime,
    Medication,
    ObservanceRule,
    Profile,
    UsualIntakeItem,
)
from app.models.push import PushSubscription, ReminderDelivery
from app.models.reference import RdaReference, UpperLimit
from app.models.user import User
from app.models.weight import CalorieAdjustment, WeightLog

__all__ = [
    "AvoidedFood",
    "Base",
    "CalorieAdjustment",
    "CycleLog",
    "CycleScreening",
    "CycleSettings",
    "CycleSymptom",
    "Dish",
    "DishIngredient",
    "DishNutrient",
    "DishPolish",
    "FavouriteIngredient",
    "HealthCondition",
    "Household",
    "HouseholdInvite",
    "HouseholdMember",
    "Ingredient",
    "IngredientNutrient",
    "MealLog",
    "MealPlan",
    "MealPlanItem",
    "MealSlotSkip",
    "MealSlotTime",
    "Medication",
    "Nutrient",
    "ObservanceRule",
    "PortionMeasure",
    "Profile",
    "PushSubscription",
    "RdaReference",
    "ReminderDelivery",
    "UpperLimit",
    "User",
    "UserSettings",
    "UsualIntakeItem",
    "WeightLog",
]
