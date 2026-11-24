import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from . import controls, snapshot_archive, workflow
from .auth import authenticate, current_user, require
from .control_contracts import ClearanceSubmission, ControlDecision, Controls, CorrectionSubmission, DeliveryBatch
from .contracts import (
    Code, Decision, Dossier, Exclusion, Login, Observation, Plan, PlanCreate, PlanFields, Role, Roster,
    SnapshotStatus, SupplementSubmission, Transfer,
)
from .db import QUEUE, connect, migrate, redis_client
from .session_routes import router as session_router

logger = logging.getLogger('uvicorn.error')
organizer = require(Role.ORGANIZER)
observer = require(Role.OBSERVER)
reviewer = require(Role.REVIEWER)


@asynccontextmanager
async def lifespan(app):
    import os

    migrate()
    if os.getenv('SEED_DEMO', 'false').lower() == 'true':
        from scripts.seed_demo import seed

        try:
            logger.info('Demo seed: %s', seed())
        except Exception:
            logger.exception('演示数据初始化失败')
    yield


app = FastAPI(title='社区课程报名对照实验', lifespan=lifespan)
app.include_router(session_router)


def archive_reader(user=Depends(current_user)):
    if user['role'] == Role.INSTRUCTOR:
        raise HTTPException(403, '此档案操作由实验岗位处理')
    return user


@app.middleware('http')
async def errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception('Request failed: %s', request.state.request_id)
        return JSONResponse({'detail': '服务暂时不可用，请稍后重试'}, status_code=500)


@app.middleware('http')
async def trace(request: Request, call_next):
    request.state.request_id = uuid4().hex
    began = time.perf_counter()
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['Server-Timing'] = f'app;dur={(time.perf_counter() - began) * 1000:.1f}'
    if request.url.path != '/health':
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(RequestValidationError)
async def invalid_input(request, exc):
    error = exc.errors()[0]
    location = '.'.join(str(part) for part in error['loc'][1:])
    detail = str(error['ctx']['error']) if 'error' in error.get('ctx', {}) else (f'请检查字段 {location}' if location else '请检查输入')
    return JSONResponse({'detail': detail}, status_code=422)


@app.get('/health')
def health():
    with connect() as conn:
        conn.execute('SELECT 1 FROM experiment_plan LIMIT 1')
    redis_client().ping()
    return {'status': 'healthy'}


@app.post('/auth/login')
def login(item: Login):
    return authenticate(item.email, item.password)


@app.get('/auth/me')
def whoami(user=Depends(current_user)):
    return user


@app.get('/experiments', response_model=list[Plan])
def plans(user=Depends(current_user)):
    return workflow.plan_list(user['email'] if user['role'] == Role.INSTRUCTOR else None)


@app.post('/experiments', status_code=201, response_model=Plan)
def create(item: PlanCreate, user=Depends(organizer)):
    return workflow.create_plan(item, user['email'])


@app.get('/experiments/{code}', response_model=Dossier)
def detail(code: Code, user=Depends(current_user)):
    return workflow.dossier(code, user['email'] if user['role'] == Role.INSTRUCTOR else None)


@app.put('/experiments/{code}', response_model=Dossier)
def edit(code: Code, item: PlanFields, user=Depends(organizer)):
    workflow.edit_plan(code, item, user['email'])
    return workflow.dossier(code)


@app.post('/experiments/{code}/check', response_model=Dossier)
def check(code: Code, user=Depends(reviewer)):
    workflow.check(code, user['email'])
    return workflow.dossier(code)


@app.post('/experiments/{code}/assign', response_model=Dossier)
def assign(code: Code, item: Roster, user=Depends(organizer)):
    workflow.assign(code, item.codes, user['email'])
    return workflow.dossier(code)


@app.post('/experiments/{code}/roster/{resident}/exclude', response_model=Dossier)
def exclude(code: Code, resident: Code, item: Exclusion, user=Depends(organizer)):
    workflow.exclude(code, resident, item, user['email'])
    return workflow.dossier(code)


@app.post('/experiments/{code}/roster/{resident}/transfer', response_model=Dossier)
def transfer(code: Code, resident: Code, item: Transfer, user=Depends(observer)):
    workflow.report_transfer(code, resident, item, user['email'])
    return workflow.dossier(code)


@app.put('/experiments/{code}/observations', response_model=Dossier)
def observe(code: Code, item: Observation, user=Depends(observer)):
    workflow.observe(code, item, user['email'])
    return workflow.dossier(code)


@app.post('/experiments/{code}/analysis', status_code=202, response_model=Dossier)
def analysis(code: Code, user=Depends(observer)):
    if workflow.queue_analysis(code, user['email']):
        try:
            redis_client().lpush(QUEUE, code)
        except RedisError:
            logger.warning('分析已持久化，等待 worker 轮询 %s', code)
    return workflow.dossier(code)


@app.post('/experiments/{code}/decision', response_model=Dossier)
def decision(code: Code, item: Decision, user=Depends(reviewer)):
    workflow.decide(code, item, user['email'])
    return workflow.dossier(code)


@app.get('/experiments/{code}/snapshot', dependencies=[Depends(archive_reader)])
def snapshot(code: Code):
    payload = snapshot_archive.verified_payload(code)
    return Response(
        json.dumps(payload, ensure_ascii=False),
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="{code}-analysis.json"'},
    )


@app.get('/experiments/{code}/snapshot/status', response_model=SnapshotStatus, dependencies=[Depends(archive_reader)])
def snapshot_status(code: Code):
    return snapshot_archive.status(code)


@app.post('/experiments/{code}/snapshot/supplements', response_model=SnapshotStatus)
def submit_supplement(code: Code, item: SupplementSubmission, user=Depends(reviewer)):
    return snapshot_archive.submit(code, item, user['email'])


@app.get('/experiments/{code}/controls', response_model=Controls, dependencies=[Depends(archive_reader)])
def execution_controls(code: Code):
    return controls.details(code)


@app.post('/experiments/{code}/clearances', status_code=204)
def submit_clearance(code: Code, item: ClearanceSubmission, user=Depends(organizer)):
    controls.submit_clearance(code, item, user['email'])


@app.post('/experiments/{code}/clearances/{version}/decision', status_code=204)
def decide_clearance(code: Code, version: int, item: ControlDecision, user=Depends(reviewer)):
    controls.decide_clearance(code, version, item, user['email'])


@app.post('/experiments/{code}/invitations', status_code=204)
def record_invitations(code: Code, item: DeliveryBatch, user=Depends(organizer)):
    controls.record_invitations(code, item, user['email'])


@app.post('/experiments/{code}/corrections', status_code=204)
def submit_correction(code: Code, item: CorrectionSubmission, user=Depends(observer)):
    controls.submit_correction(code, item, user['email'])


@app.post('/experiments/{code}/corrections/{correction_id}/decision', status_code=204)
def decide_correction(code: Code, correction_id: int, item: ControlDecision, user=Depends(reviewer)):
    controls.decide_correction(code, correction_id, item, user['email'])
