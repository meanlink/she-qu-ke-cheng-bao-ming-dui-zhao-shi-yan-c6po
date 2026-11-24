import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from .contracts import Role
from .db import connect

secret = os.environ['JWT_SECRET']
bearer = OAuth2PasswordBearer(tokenUrl='/auth/login')


def password_hash(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f'{salt.hex()}:{digest.hex()}'


def authenticate(email, password):
    with connect() as conn:
        user = conn.execute('SELECT * FROM staff WHERE email = %s', (email,)).fetchone()
    expected = user['password_hash'] if user else '00:' + '0' * 128
    got = password_hash(password, bytes.fromhex(expected.split(':')[0]))
    if not hmac.compare_digest(got, expected) or not user:
        raise HTTPException(401, '账号或密码有误')
    token = jwt.encode(
        {'sub': user['email'], 'exp': datetime.now(timezone.utc) + timedelta(hours=8)},
        secret, algorithm='HS256',
    )
    return {'access_token': token, 'token_type': 'bearer', 'user': public_user(user)}


def public_user(user):
    return {key: user[key] for key in ('email', 'display_name', 'role')}


def current_user(token: Annotated[str, Depends(bearer)]):
    try:
        claims = jwt.decode(token, secret, algorithms=['HS256'], options={'require': ['sub', 'exp']})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, '会话已失效，请重新登录') from exc
    with connect() as conn:
        user = conn.execute('SELECT email, display_name, role FROM staff WHERE email = %s', (claims['sub'],)).fetchone()
    if not user:
        raise HTTPException(401, '账号不可用')
    return user


def require(role: Role):
    def authorized(user=Depends(current_user)):
        if user['role'] != role:
            raise HTTPException(403, '当前岗位无权执行此操作')
        return user
    return authorized
