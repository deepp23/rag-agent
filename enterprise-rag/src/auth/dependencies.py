import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.auth.security import decode_access_token
from src.db.models import User, Workspace
from src.db.session import get_db

bearer_scheme = HTTPBearer()

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _CREDENTIALS_ERROR

    user_id = payload.get("sub")
    if user_id is None:
        raise _CREDENTIALS_ERROR

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR

    return user


def get_current_workspace(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
    if workspace is None:
        # Shouldn't happen — every user gets a workspace at signup — but
        # fail loudly rather than silently scoping to nothing.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User has no workspace",
        )
    return workspace
