from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, NaiveDatetime, model_validator

from .contracts import Code, Input, Label, Outcome

Limit = Annotated[int, Field(ge=1, le=500)]
SeatStatus = Literal['confirmed', 'waitlisted', 'withdrawn']
MarkStatus = Literal['attended', 'absent']


class SessionStage(StrEnum):
    ENROLLING = 'enrolling'
    LOCKED = 'locked'
    SUBMITTED = 'submitted'
    RECONCILED = 'reconciled'


class CapacityChange(Input):
    seat_limit: Limit
    source_ref: Label


class SessionBooking(CapacityChange):
    instructor_email: Annotated[str, Field(min_length=3, max_length=254)]
    starts_at: NaiveDatetime
    ends_at: NaiveDatetime
    room_limit: Limit

    @model_validator(mode='after')
    def same_day(self):
        if self.starts_at.date() != self.ends_at.date() or self.starts_at >= self.ends_at:
            raise ValueError('开课与下课须在同一天，且下课时间须晚于开课时间')
        return self


class SeatRequest(Input):
    participant_code: Code
    received_on: date
    source_ref: Label


class SeatWithdrawal(Input):
    received_on: date
    source_ref: Label


class AttendanceEntry(Input):
    participant_code: Code
    status: MarkStatus


class AttendanceSubmission(Input):
    source_ref: Label
    entries: Annotated[list[AttendanceEntry], Field(max_length=500)]

    @model_validator(mode='after')
    def unique_entries(self):
        if len({entry.participant_code for entry in self.entries}) != len(self.entries):
            raise ValueError('签到表中每位居民只能出现一次')
        return self


class Reconciliation(Input):
    source_ref: Label


class InstructorProfile(BaseModel):
    email: str
    display_name: str
    teaching_limit: int


class CourseSession(BaseModel):
    instructor_email: str
    instructor_name: str
    teaching_limit: int
    starts_at: datetime
    ends_at: datetime
    room_limit: int
    seat_limit: int
    schedule_ref: str
    stage: SessionStage
    locked_at: datetime | None
    last_received_on: date
    may_lock: bool
    may_submit: bool


class SeatRecord(BaseModel):
    participant_code: str
    arm: Literal['A', 'B']
    status: SeatStatus
    queue_position: int | None
    requested_on: date
    request_ref: str
    confirmed_at: datetime | None
    withdrawn_on: date | None
    withdrawal_ref: str | None


class AttendanceRoll(BaseModel):
    source_ref: str
    submitted_by: str
    submitted_at: datetime
    reconciled_by: str | None
    reconciled_at: datetime | None
    reconcile_ref: str | None


class HandoffRow(BaseModel):
    participant_code: str
    arm: Literal['A', 'B']
    outcome: Outcome


class SessionLedger(BaseModel):
    session: CourseSession | None
    instructors: list[InstructorProfile]
    seats: list[SeatRecord]
    roll: AttendanceRoll | None
    outcomes: list[HandoffRow]
    may_book: bool
