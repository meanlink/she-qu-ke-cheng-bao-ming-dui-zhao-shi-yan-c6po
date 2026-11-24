from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Narrative = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=300)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r'^[A-Z0-9][A-Z0-9_-]{1,23}$')]


class Role(StrEnum):
    ORGANIZER = 'organizer'
    OBSERVER = 'observer'
    REVIEWER = 'reviewer'
    INSTRUCTOR = 'instructor'


class Phase(StrEnum):
    DRAFT = 'draft'
    CHECKED = 'checked'
    OBSERVING = 'observing'
    QUEUED = 'queued'
    REVIEW = 'review'
    FROZEN = 'frozen'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class Outcome(StrEnum):
    NO_SIGNUP = 'no_signup'
    ABSENT = 'absent'
    ATTENDED = 'attended'
    WAITLISTED = 'waitlisted'
    WITHDRAWN = 'withdrawn'


ManualOutcome = Literal['no_signup', 'absent', 'attended']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Input):
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class PlanFields(Input):
    title: Label
    question: Narrative
    site: Label
    control_invite: Label
    variant_invite: Label
    window_start: date
    window_end: date
    primary_metric: Literal['signup', 'attendance']
    min_per_arm: Annotated[int, Field(ge=12, le=500)]

    @model_validator(mode='after')
    def check_range(self):
        if self.window_end < self.window_start:
            raise ValueError('观测结束日期须晚于或等于开始日期')
        if self.control_invite == self.variant_invite:
            raise ValueError('两种邀请方式必须不同')
        return self


class PlanCreate(PlanFields):
    code: Code


class Roster(Input):
    codes: Annotated[list[Code], Field(min_length=1, max_length=1000)]

    @model_validator(mode='after')
    def unique_codes(self):
        if len(set(self.codes)) != len(self.codes):
            raise ValueError('名单包含重复居民编号')
        return self


class OutcomeEntry(Input):
    code: Code
    outcome: ManualOutcome


class Observation(Input):
    observed_on: date
    source_ref: Label
    entries: Annotated[list[OutcomeEntry], Field(min_length=1, max_length=1000)]

    @model_validator(mode='after')
    def unique_entries(self):
        if len({row.code for row in self.entries}) != len(self.entries):
            raise ValueError('同一批次只能为每位居民保存一条观测')
        return self


class Exclusion(Input):
    reason: Literal['duplicate', 'ineligible']
    reference: Narrative


class Transfer(Input):
    reported_arm: Literal['A', 'B']
    reference: Narrative


class Decision(Input):
    decision: Literal['approved', 'rejected']
    note: Narrative


class Plan(PlanCreate):
    id: int
    state: Phase
    author: str
    checked_by: str | None
    checked_at: datetime | None
    allocation_seed: str | None
    roster_digest: str | None
    created_at: datetime


class Assignment(BaseModel):
    plan_id: int
    participant_code: str
    arm: Literal['A', 'B']
    outcome: Outcome | None
    source_ref: str | None
    observed_on: date | None
    observed_by: str | None
    exclusion_reason: Literal['duplicate', 'ineligible'] | None
    exclusion_ref: str | None
    reported_arm: Literal['A', 'B'] | None
    deviation_ref: str | None
    delivered_on: date | None = None


class Review(BaseModel):
    plan_id: int
    status: Literal['queued', 'ready', 'frozen', 'approved', 'rejected']
    requested_by: str
    requested_at: datetime
    input_digest: str | None
    result: dict[str, float | int | bool] | None
    freeze_reason: str | None
    decision_note: str | None
    decided_by: str | None
    decided_at: datetime | None


class ArmTally(BaseModel):
    assigned: int
    eligible: int
    recorded: int
    signup: int
    attendance: int


class AuditEntry(BaseModel):
    actor: str
    event: str
    detail: str
    occurred_at: datetime


class SupplementSubmission(Input):
    source_ref: Label
    note: Narrative


class SupplementRecord(BaseModel):
    id: int
    source_ref: str
    input_digest: str
    note: str
    mismatch_reason: str | None
    status: Literal['pending', 'restored', 'manual']
    requested_by: str
    requested_at: datetime
    applied_at: datetime | None


class SnapshotStatus(BaseModel):
    code: str
    primary_metric: Literal['signup', 'attendance']
    state: Literal['not_ready', 'missing', 'pending', 'mismatch', 'manual', 'verified']
    reason: str | None
    digest: str | None
    computed_digest: str
    groups: dict[Literal['A', 'B'], ArmTally]
    statistics: dict[str, float | int | bool] | None
    supplements: list[SupplementRecord]


class Dossier(BaseModel):
    plan: Plan
    assignments: list[Assignment]
    groups: dict[Literal['A', 'B'], ArmTally]
    review: Review | None
    events: list[AuditEntry]
    clearance_status: Literal['pending', 'approved', 'returned'] | None
    pending_corrections: int
    has_session: bool
