from fastapi import APIRouter, Depends

from . import attendance_handoff, class_schedule, seat_queue
from .auth import current_user, require
from .contracts import Code, Role
from .session_contracts import (
    AttendanceSubmission, CapacityChange, Reconciliation, SeatRequest, SeatWithdrawal, SessionBooking, SessionLedger,
)
from .session_ledger import read_ledger

router = APIRouter(prefix='/experiments/{code}/session')
organizer = require(Role.ORGANIZER)
instructor = require(Role.INSTRUCTOR)
observer = require(Role.OBSERVER)


@router.get('', response_model=SessionLedger)
def ledger(code: Code, user=Depends(current_user)):
    return read_ledger(code, user)


@router.post('', status_code=204)
def book(code: Code, item: SessionBooking, user=Depends(organizer)):
    class_schedule.book(code, item, user['email'])


@router.patch('/capacity', status_code=204)
def capacity(code: Code, item: CapacityChange, user=Depends(organizer)):
    class_schedule.revise_capacity(code, item, user['email'])


@router.post('/seats', status_code=204)
def request_seat(code: Code, item: SeatRequest, user=Depends(organizer)):
    seat_queue.request_seat(code, item, user['email'])


@router.post('/seats/{resident}/withdraw', status_code=204)
def withdraw(code: Code, resident: Code, item: SeatWithdrawal, user=Depends(organizer)):
    seat_queue.withdraw(code, resident, item, user['email'])


@router.post('/attendance/lock', status_code=204)
def lock_roll(code: Code, user=Depends(instructor)):
    attendance_handoff.lock_roll(code, user['email'])


@router.post('/attendance', status_code=204)
def submit_roll(code: Code, item: AttendanceSubmission, user=Depends(instructor)):
    attendance_handoff.submit_roll(code, item, user['email'])


@router.post('/attendance/reconcile', status_code=204)
def reconcile(code: Code, item: Reconciliation, user=Depends(observer)):
    attendance_handoff.reconcile(code, item, user['email'])
