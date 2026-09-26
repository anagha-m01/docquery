from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import create_user, get_user_by_email, DuplicateEmailError, DatabaseError
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister):
    try:
        user_id = create_user(payload.email, hash_password(payload.password))
    except DuplicateEmailError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    token = create_access_token(user_id, payload.email)
    return TokenResponse(
        access_token=token,
        user=UserOut(id=user_id, email=payload.email),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    try:
        user = get_user_by_email(payload.email)
    except DatabaseError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = create_access_token(user["id"], user["email"])
    return TokenResponse(
        access_token=token,
        user=UserOut(id=user["id"], email=user["email"]),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    return UserOut(id=current_user["id"], email=current_user["email"])
