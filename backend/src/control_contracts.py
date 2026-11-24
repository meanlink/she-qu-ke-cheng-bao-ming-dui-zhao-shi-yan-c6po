from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from .contracts import Code, Input, Label, ManualOutcome, Narrative, Outcome, Roster


class ControlStatus(StrEnum):
    PENDING = 'pending'
    APPROVED = 'approved'
    RETURNED = 'returned'


class DeliveryStatus(StrEnum):
    DELIVERED = 'delivered'
    FAILED = 'failed'


class Channel(StrEnum):
    SMS = 'sms'
    PHONE = 'phone'
    DESK = 'desk'


class ClearanceSubmission(Roster):
    source_ref: Label


class ControlDecision(Input):
    decision: Literal['approved', 'returned']
    note: Narrative


class DeliveryBatch(Roster):
    arm: Literal['A', 'B']
    delivered_on: date
    channel: Channel
    status: DeliveryStatus
    source_ref: Label


class CorrectionSubmission(Input):
    participant_code: Code
    proposed_outcome: ManualOutcome
    proposed_observed_on: date
    proposed_source_ref: Label
    reason: Narrative


class ReviewRecord(BaseModel):
    status: ControlStatus
    submitted_at: datetime
    submitted_by: str
    decided_at: datetime | None
    decided_by: str | None
    decision_note: str | None


class ClearanceRecord(ReviewRecord):
    version: int
    codes: list[str]
    source_ref: str


class DeliveryRecord(BaseModel):
    participant_code: str
    delivered_on: date
    channel: Channel
    status: DeliveryStatus
    source_ref: str
    recorded_by: str
    recorded_at: datetime


class CorrectionRecord(ReviewRecord):
    id: int
    participant_code: str
    original_outcome: Outcome
    original_observed_on: date
    original_source_ref: str
    original_observed_by: str
    proposed_outcome: Outcome
    proposed_observed_on: date
    proposed_source_ref: str
    reason: str


class Controls(BaseModel):
    clearances: list[ClearanceRecord]
    invitations: list[DeliveryRecord]
    corrections: list[CorrectionRecord]
