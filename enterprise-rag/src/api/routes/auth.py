from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user, get_current_workspace
from src.auth.security import create_access_token, hash_password, verify_password
from src.core.logger import get_logger
from src.api.models import LoginRequest, SignupRequest, TokenResponse, UserResponse
from src.db.models import User, Workspace
from src.db.session import get_db

logger = get_logger(__name__)
router = APIRouter()


@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    user = User(
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
    )
    db.add(user)
    try:
        db.flush()  # assign user.id without committing yet
        db.add(Workspace(owner_id=user.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    logger.info(f"[/auth/signup] new user: {user.email}")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email.lower()).first()

    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    logger.info(f"[/auth/login] user: {user.email}")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/auth/me", response_model=UserResponse)
def me(
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
):
    return UserResponse(
        id=user.id,
        email=user.email,
        workspace_id=workspace.id,
        created_at=user.created_at,
    )
