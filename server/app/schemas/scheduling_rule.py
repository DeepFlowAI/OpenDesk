"""
Scheduling rule set Pydantic schemas.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Constraint keys and their numeric parameter ranges (min, max, default).
CONSTRAINT_PARAM_RANGES: dict[str, tuple[int, int, int]] = {
    "max_consecutive_days": (1, 31, 6),
    "min_rest_hours": (0, 48, 8),
    "max_weekly_work_days": (1, 7, 6),
    "max_daily_shifts": (1, 6, 2),
    "fairness_deviation": (0, 14, 2),
}
# Constraints without a numeric parameter; level is fixed to soft.
CONSTRAINTS_WITHOUT_PARAM: tuple[str, ...] = ("coverage_gap", "coverage_overflow")
CONSTRAINT_KEYS: tuple[str, ...] = (*CONSTRAINT_PARAM_RANGES, *CONSTRAINTS_WITHOUT_PARAM)

ConstraintLevel = Literal["hard", "soft"]


class ConstraintConfig(BaseModel):
    enabled: bool = True
    level: ConstraintLevel = "soft"
    value: int | None = None


class RotationTemplateDay(BaseModel):
    kind: Literal["shift", "off"]
    shift_id: int | None = None

    @model_validator(mode="after")
    def check_shift_id(self) -> "RotationTemplateDay":
        if self.kind == "shift" and self.shift_id is None:
            raise ValueError("shift_id is required when kind is 'shift'")
        if self.kind == "off" and self.shift_id is not None:
            raise ValueError("shift_id must be omitted when kind is 'off'")
        return self


class RotationTemplate(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=40)
    is_default: bool = False
    days: list[RotationTemplateDay] = Field(min_length=2, max_length=28)


def _validate_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Name is required")
    if len(v) > 40:
        raise ValueError("Name must be at most 40 characters")
    return v


ZERO_WEEK: list[int] = [0, 0, 0, 0, 0, 0, 0]


def _validate_week_counts(values: object, label: str) -> list[int]:
    if not isinstance(values, list) or len(values) != 7:
        raise ValueError(f"{label} must be an array of 7 numbers (Mon..Sun)")
    out: list[int] = []
    for n in values:
        if not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= 999:
            raise ValueError(f"{label} values must be integers between 0 and 999")
        out.append(n)
    return out


def _normalize_target_band(value: object, key: str) -> dict[str, list[int]]:
    """Accept legacy [7 ints] or {min,target,max}; always return the band object."""
    if isinstance(value, list):
        days = _validate_week_counts(value, f"targets[{key}]")
        return {"min": list(days), "target": list(days), "max": list(days)}
    if not isinstance(value, dict):
        raise ValueError(
            f"targets[{key}] must be {{min,target,max}} week arrays or a legacy 7-int array"
        )
    min_days = _validate_week_counts(value.get("min", ZERO_WEEK), f"targets[{key}].min")
    target_days = _validate_week_counts(
        value.get("target", ZERO_WEEK), f"targets[{key}].target"
    )
    max_days = _validate_week_counts(value.get("max", ZERO_WEEK), f"targets[{key}].max")
    for i in range(7):
        if not min_days[i] <= target_days[i] <= max_days[i]:
            raise ValueError(
                f"targets[{key}] day {i}: require min <= target <= max "
                f"(got {min_days[i]}, {target_days[i]}, {max_days[i]})"
            )
    return {"min": min_days, "target": target_days, "max": max_days}


def normalize_targets(v: dict | None) -> dict[str, dict[str, list[int]]]:
    """Normalize stored/legacy targets to the three-band shape (string keys)."""
    if not v:
        return {}
    if not isinstance(v, dict):
        raise ValueError("targets must be an object")
    out: dict[str, dict[str, list[int]]] = {}
    for key, value in v.items():
        try:
            int(key)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid shift id key in targets: {key}") from None
        out[str(key)] = _normalize_target_band(value, str(key))
    return out


def targets_to_engine_map(v: dict | None) -> dict[int, dict[str, list[int]]]:
    """Convert targets to engine map keyed by int shift id."""
    return {int(shift_id): band for shift_id, band in normalize_targets(v).items()}


def _validate_targets_write(v: dict) -> dict:
    """Write path: require the three-band object form (no legacy arrays)."""
    if not isinstance(v, dict):
        raise ValueError("targets must be an object")
    out: dict[str, dict[str, list[int]]] = {}
    for key, value in v.items():
        try:
            int(key)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid shift id key in targets: {key}") from None
        if isinstance(value, list):
            raise ValueError(
                f"targets[{key}] must be an object with min/target/max week arrays"
            )
        out[str(key)] = _normalize_target_band(value, str(key))
    return out


def _validate_constraints(v: dict) -> dict:
    if not isinstance(v, dict):
        raise ValueError("constraints must be an object")
    for key, cfg in v.items():
        if key not in CONSTRAINT_KEYS:
            raise ValueError(f"Unknown constraint key: {key}")
        if not isinstance(cfg, dict):
            raise ValueError(f"constraints[{key}] must be an object")
        config = ConstraintConfig.model_validate(cfg)
        if key in CONSTRAINTS_WITHOUT_PARAM:
            if config.value is not None:
                raise ValueError(f"constraints[{key}] must not have a value")
            if config.level != "soft":
                raise ValueError(f"constraints[{key}] level is fixed to soft")
        elif config.enabled:
            if config.value is None:
                raise ValueError(f"constraints[{key}] requires a value when enabled")
            low, high, _ = CONSTRAINT_PARAM_RANGES[key]
            if not low <= config.value <= high:
                raise ValueError(f"constraints[{key}] value must be between {low} and {high}")
    return v


def _validate_rotation_templates(v: list) -> list:
    if not isinstance(v, list):
        raise ValueError("rotation_templates must be an array")
    if len(v) > 10:
        raise ValueError("At most 10 rotation templates per rule set")
    templates = [RotationTemplate.model_validate(t) for t in v]
    ids = [t.id for t in templates]
    if len(ids) != len(set(ids)):
        raise ValueError("Rotation template ids must be unique")
    if sum(1 for t in templates if t.is_default) > 1:
        raise ValueError("At most one default rotation template")
    return [t.model_dump() for t in templates]


class RuleSetConfigFields(BaseModel):
    default_group_ids: list[int] = Field(default_factory=list, max_length=50)
    targets_enabled: bool = True
    targets: dict[str, dict[str, list[int]]] = Field(default_factory=dict)
    constraints: dict[str, dict] = Field(default_factory=dict)
    rotation_templates: list[dict] = Field(default_factory=list)

    @field_validator("default_group_ids")
    @classmethod
    def validate_group_ids(cls, v: list[int]) -> list[int]:
        return list(dict.fromkeys(v))

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, v: dict) -> dict:
        return _validate_targets_write(v)

    @field_validator("constraints")
    @classmethod
    def validate_constraints(cls, v: dict) -> dict:
        return _validate_constraints(v)

    @field_validator("rotation_templates")
    @classmethod
    def validate_rotation_templates(cls, v: list) -> list:
        return _validate_rotation_templates(v)


class RuleSetCreate(RuleSetConfigFields):
    name: str
    description: str | None = Field(default=None, max_length=500)
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)


class RuleSetUpdate(RuleSetConfigFields):
    name: str
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)


class RuleSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_default: bool
    default_group_ids: list[int]
    targets_enabled: bool = True
    targets: dict[str, dict[str, list[int]]]
    constraints: dict[str, dict]
    rotation_templates: list[dict]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("targets", mode="before")
    @classmethod
    def normalize_response_targets(cls, v: dict) -> dict:
        return normalize_targets(v)


class RuleSetListResponse(BaseModel):
    items: list[RuleSetResponse]


# ------------------------------------------------------------------
# Violations & rule-based generation
# ------------------------------------------------------------------

MAX_GENERATE_RANGE_DAYS = 31


class ViolationItem(BaseModel):
    level: ConstraintLevel
    constraint: str
    date: date
    employee_id: int | None = None
    employee_name: str | None = None
    shift_id: int | None = None
    shift_name: str | None = None
    detail: dict = Field(default_factory=dict)


class ViolationListResponse(BaseModel):
    items: list[ViolationItem]
    hard_count: int
    soft_count: int


class GenerateRequest(BaseModel):
    rule_set_id: int
    start_date: date
    end_date: date
    mode: Literal["fill", "clear"] = "fill"
    use_template: bool = True
    on_hard_conflict: Literal["skip", "abort"] = "skip"
    group_ids: list[int] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def check_range(self) -> "GenerateRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        if (self.end_date - self.start_date).days + 1 > MAX_GENERATE_RANGE_DAYS:
            raise ValueError(
                f"Date range must not exceed {MAX_GENERATE_RANGE_DAYS} days"
            )
        return self


class GenerateSampleLine(BaseModel):
    date: date
    shift_id: int
    shift_name: str
    added: list[str]
    gap: int


class GeneratePreviewResponse(BaseModel):
    to_create: int
    to_delete: int
    skipped_cells: int
    leave_skipped: int = 0
    target_met: int
    target_total: int
    hard_count: int
    soft_count: int
    hard_violations: list[ViolationItem]
    soft_violations: list[ViolationItem]
    sample: list[GenerateSampleLine]


class GenerateApplyResponse(BaseModel):
    created: int
    deleted: int
