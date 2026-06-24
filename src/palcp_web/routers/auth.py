"""Registration, login, and logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..forms import clean
from ..models import User
from ..security import (
    hash_password,
    login_session,
    logout_session,
    optional_user,
    verify_password,
)
from ..templating import flash, render

router = APIRouter()


@router.get("/register")
def register_form(request: Request, db: Session = Depends(get_db)):
    if optional_user(request, db):
        return RedirectResponse("/", status_code=303)
    return render(request, "auth/register.html")


@router.post("/register")
def register(request: Request, email: str = Form(...), password: str = Form(...),
             full_name: str = Form(""), credentials: str = Form(""),
             db: Session = Depends(get_db)):
    email = clean(email).lower()
    if not email or not password:
        flash(request, "Email and password are required.", "error")
        return RedirectResponse("/register", status_code=303)
    if len(password) < 8:
        flash(request, "Password must be at least 8 characters.", "error")
        return RedirectResponse("/register", status_code=303)
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        flash(request, "An account with that email already exists.", "error")
        return RedirectResponse("/register", status_code=303)
    user = User(email=email, password_hash=hash_password(password),
                full_name=clean(full_name), credentials=clean(credentials))
    db.add(user)
    db.commit()
    login_session(request, user)
    flash(request, "Welcome — your account is ready.", "success")
    return RedirectResponse("/", status_code=303)


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    if optional_user(request, db):
        return RedirectResponse("/", status_code=303)
    return render(request, "auth/login.html")


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    email = clean(email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        flash(request, "Invalid email or password.", "error")
        return RedirectResponse("/login", status_code=303)
    if not user.is_active:
        flash(request, "This account is disabled.", "error")
        return RedirectResponse("/login", status_code=303)
    login_session(request, user)
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_session(request)
    flash(request, "Signed out.", "info")
    return RedirectResponse("/login", status_code=303)
