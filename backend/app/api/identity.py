import hashlib
import re

from fastapi import Header, HTTPException


def practice_owner(x_practice_token: str = Header(default='')) -> str:
    if not re.fullmatch(r'[a-fA-F0-9]{64}', x_practice_token):
        raise HTTPException(status_code=401, detail='缺少本机练习身份，请重新打开页面')
    return hashlib.sha256(x_practice_token.encode()).hexdigest()
