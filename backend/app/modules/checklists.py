"""M-09 security checklist and M-11 social privacy checklist (own accounts only; self-reported).
Content (texts, per-OS steps) lives in the frontend i18n files; the backend only stores progress."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.core.errors import ApiError
from app.core.events import timeline
from app.db import get_db
from app.models import ChecklistState, User, now
from app.modules.findings_service import snapshot

router = APIRouter(tags=["checklists"])

SECURITY_ITEMS = ["two_factor", "password_manager", "screen_lock", "updates", "app_permissions", "backup", "router_password",
                  "browser_extensions"]
SOCIAL = {
    "instagram": ["private_account", "location_off", "tag_review", "contacts_sync_off", "story_close_friends", "activity_status"],
    "tiktok": ["private_account", "suggest_account_off", "duet_stitch_limit", "downloads_off", "contacts_sync_off"],
    "facebook": ["profile_audience", "search_engine_off", "find_by_phone", "tag_review", "past_posts_limit", "off_facebook_activity"],
    "x": ["protect_posts", "location_off", "discoverability_phone", "discoverability_email", "dm_settings"],
    "linkedin": ["profile_visibility", "public_profile_edit", "contact_info", "discover_by_phone", "data_for_ai_off"],
    "youtube": ["subscriptions_private", "playlists_private", "liked_private", "channel_info"],
    "snapchat": ["snap_map_ghost", "contact_me_friends", "quick_add_off", "story_audience"],
    "whatsapp": ["last_seen", "profile_photo_contacts", "about_contacts", "groups_contacts", "read_receipts", "silence_unknown"],
}


def _state(db: Session, user: User, scope: str) -> dict[str, bool]:
    return {r.item: r.done for r in db.scalars(select(ChecklistState).where(ChecklistState.user_id == user.id, ChecklistState.scope == scope))}


@router.get("/checklist")
def get_checklist(user: User = Depends(current_user), db: Session = Depends(get_db)):
    st = _state(db, user, "security")
    items = [{"key": k, "done": st.get(k, False)} for k in SECURITY_ITEMS]
    return {"items": items, "done": sum(i["done"] for i in items), "total": len(items)}


class ItemIn(BaseModel):
    item: str
    done: bool


def _set(db: Session, user: User, scope: str, item: str, done: bool) -> None:
    row = db.scalar(select(ChecklistState).where(ChecklistState.user_id == user.id, ChecklistState.scope == scope, ChecklistState.item == item))
    if not row:
        row = ChecklistState(user_id=user.id, scope=scope, item=item)
        db.add(row)
    if row.done != done and done:
        timeline(db, user.id, "checklist", f"Erledigt: {scope}/{item}")
    row.done, row.updated_at = done, now()


@router.patch("/checklist")
def patch_checklist(body: ItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.item not in SECURITY_ITEMS:
        raise ApiError(400, "invalid_item")
    _set(db, user, "security", body.item, body.done)
    db.flush()
    risk = snapshot(db, user)
    db.commit()
    return {**get_checklist(user, db), "risk": {"score": risk["score"], "light": risk["light"]}}


@router.get("/social")
def get_social(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = {}
    for p, items in SOCIAL.items():
        st = _state(db, user, f"social:{p}")
        out[p] = {"items": [{"key": k, "done": st.get(k, False)} for k in items], "done": sum(st.get(k, False) for k in items),
                  "total": len(items)}
    return out


class SocialIn(BaseModel):
    platform: str
    item: str
    done: bool


@router.patch("/social")
def patch_social(body: SocialIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.platform not in SOCIAL or body.item not in SOCIAL[body.platform]:
        raise ApiError(400, "invalid_item")
    _set(db, user, f"social:{body.platform}", body.item, body.done)
    db.commit()
    return get_social(user, db)[body.platform]
