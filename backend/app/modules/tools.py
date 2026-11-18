"""M-06 scam check, M-07 domain check, M-08 image integrity."""
from __future__ import annotations

import base64
import io
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from PIL import ExifTags, Image, ImageChops, ImageStat
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters import registry
from app.adapters.base import SourceUnavailable
from app.ai.provider import ask
from app.core import ratelimit
from app.core.deps import current_user
from app.core.errors import ApiError
from app.core.guard import check_text
from app.core.plans import limit
from app.core.usage import consume
from app.db import get_db
from app.models import User
from app.modules.scam_rules import REASON_TEXT_DE, SUMMARY_DE, evaluate, registrable

router = APIRouter(tags=["tools"])
DOMAIN_RE = re.compile(r"^(?=.{3,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")


def _domain_age_days(rdap: dict) -> int | None:
    if not rdap.get("registered"):
        return None
    try:
        reg = datetime.fromisoformat(rdap["registered"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - reg).days
    except ValueError:
        return None


# ------------------------------------------------------------------ M-06
class ScamIn(BaseModel):
    url: str | None = Field(default=None, max_length=2000)
    text: str | None = Field(default=None, max_length=10000)
    use_ai: bool = False


@router.post("/scam/check")
def scam_check(body: ScamIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.url and not body.text:
        raise ApiError(400, "nothing_to_check")
    if body.text and (ref := check_text(body.text)) and ref.category != "third_party":
        raise ApiError(400, "hard_limit", **ref.as_dict())
    consume(db, user, "scam_check", "scam_check_per_day")
    db.commit()
    base = evaluate(body.text or "", body.url)
    extra: list[tuple[str, int]] = []
    sources: list[str] = ["rules"]
    checks: list[dict] = []
    for u in base.urls[:3]:
        host = (re.sub(r"^https?://", "", u).split("/")[0].split(":")[0]).lower()
        dom = registrable(host)
        rd = registry.get("rdap")
        if rd.enabled() and DOMAIN_RE.match(dom):
            try:
                info = rd.lookup(dom)
                sources.append("rdap")
                if not info.get("found"):
                    extra.append(("no_dns", 3))
                age = _domain_age_days(info)
                if age is not None and age < 30:
                    extra.append(("young_domain", 4))
                elif age is not None and age < 180:
                    extra.append(("fairly_new_domain", 2))
                checks.append({"url": u, "domain": dom, "age_days": age, "registrar": info.get("registrar")})
            except SourceUnavailable as e:
                checks.append({"url": u, "domain": dom, "error": e.reason})
        for name in ("safe_browsing", "urlhaus"):
            a = registry.get(name)
            if a.enabled():
                try:
                    r = a.check(u)
                    sources.append(name)
                    if r.get("listed"):
                        extra.append(("blocklisted", 10))
                except SourceUnavailable:
                    pass
    res = evaluate(body.text or "", body.url, extra)
    if "blocklisted" in res.reasons:
        res.light, res.score = "red", 100
    ai_text = None
    if body.use_ai and body.text and limit(user, "ai_per_day"):
        ai_text = ask(db, user, "Bewerte kurz, ob diese Nachricht Betrug sein könnte (grün/gelb/rot) und warum:\n\n" + body.text,
                      [], int(limit(user, "ai_per_day")))
    return {"light": res.light, "score": res.score, "summary": SUMMARY_DE[res.light],
            "reasons": [{"key": r, "text": REASON_TEXT_DE.get(r, r)} for r in res.reasons], "urls": res.urls,
            "checks": checks, "sources": sorted(set(sources)), "ai": ai_text,
            "missing_sources": [n for n in ("safe_browsing", "urlhaus") if not registry.get(n).enabled()]}


# ------------------------------------------------------------------ M-07
class DomainIn(BaseModel):
    domain: str = Field(max_length=253)


@router.post("/domain/check")
def domain_check(body: DomainIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = re.sub(r"^https?://", "", body.domain.strip().lower()).split("/")[0].split(":")[0].removeprefix("www.")
    if not DOMAIN_RE.match(d):
        raise ApiError(400, "invalid_domain")
    ratelimit.hit(f"domain:{user.id}", 10, 60)
    consume(db, user, "domain_check", "domain_check_per_day")
    db.commit()
    out: dict = {"domain": d, "errors": []}

    def run(key: str, fn):
        try:
            out[key] = fn()
        except SourceUnavailable as e:
            out["errors"].append({"source": e.source, "reason": e.reason})

    if registry.get("rdap").enabled():
        run("rdap", lambda: registry.get("rdap").lookup(d))
        if out.get("rdap"):
            out["rdap"]["age_days"] = _domain_age_days(out["rdap"])
    if registry.get("dns_doh").enabled():
        run("dns", lambda: registry.get("dns_doh").records(d))
    web = registry.get("web_passive")
    if web.enabled():
        out["tls"] = web.tls(d)
        run("page", lambda: web.page(d))
        page = out.get("page") or {}
        page.pop("html", None)
        if page.get("imprint_url"):
            run("imprint", lambda: web.imprint(page["imprint_url"]))
        hdr = page.get("headers") or {}
        out["header_score"] = {"present": sum(1 for v in hdr.values() if v), "total": len(hdr)}
    if registry.get("wayback").enabled():
        run("wayback", lambda: registry.get("wayback").first_capture(d))
    if out.get("dns") is not None:
        txt = " ".join(out["dns"].get("TXT", []))
        out["email_security"] = {"spf": "v=spf1" in txt, "dmarc": None}
        try:
            dm = registry.get("dns_doh").http("GET", "https://cloudflare-dns.com/dns-query", params={"name": f"_dmarc.{d}", "type": "TXT"},
                                               headers={"Accept": "application/dns-json"}, retries=0)
            out["email_security"]["dmarc"] = any("v=DMARC1" in a.get("data", "") for a in dm.json().get("Answer", []) or [])
        except SourceUnavailable:
            pass
    return out


# ------------------------------------------------------------------ M-08
MAX_IMG = 15 * 1024 * 1024
GPS_TAG = 34853


def _load_image(data: bytes) -> Image.Image:
    if len(data) > MAX_IMG:
        raise ApiError(413, "file_too_large")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img
    except Exception as e:  # noqa: BLE001
        raise ApiError(400, "invalid_image") from e


def _exif(img: Image.Image) -> dict:
    out: dict = {}
    ex = img.getexif()
    for k, v in ex.items():
        name = ExifTags.TAGS.get(k, str(k))
        if k == GPS_TAG:
            continue
        out[name] = str(v)[:200]
    gps = ex.get_ifd(GPS_TAG) if GPS_TAG in ex else {}
    if gps:
        def conv(vals, ref):
            d, m, s = (float(x) for x in vals)
            val = d + m / 60 + s / 3600
            return -val if ref in ("S", "W") else val

        try:
            out["GPS"] = {"lat": round(conv(gps[2], gps[1]), 5), "lon": round(conv(gps[4], gps[3]), 5)}
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            out["GPS"] = {"present": True}
    for key in ("XMP", "xmp"):
        if key in img.info:
            out["XMP"] = "present"
    return out


def _ela(img: Image.Image, quality: int = 90) -> tuple[str, float]:
    rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=quality)
    re_img = Image.open(io.BytesIO(buf.getvalue()))
    diff = ImageChops.difference(rgb, re_img)
    stat = ImageStat.Stat(diff)
    mean = sum(stat.mean) / 3
    extrema = max(e[1] for e in diff.getextrema()) or 1
    diff = diff.point(lambda p: min(255, p * (255.0 / extrema)))
    diff.thumbnail((640, 640))
    out = io.BytesIO()
    diff.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode(), round(mean, 2)


def _ai_hints(img: Image.Image, exif: dict, raw: bytes) -> list[dict]:
    hints = []
    blob = raw[:200_000].lower()
    for marker, text in ((b"c2pa", "Content-Credentials (C2PA) gefunden – Herkunftsangaben vorhanden."),
                         (b"stable diffusion", "Metadaten nennen „Stable Diffusion“."), (b"midjourney", "Metadaten nennen „Midjourney“."),
                         (b"dall", "Metadaten nennen möglicherweise „DALL·E“."), (b"trainedalgorithmicmedia", "IPTC-Kennzeichnung „KI-generiert“.")):
        if marker in blob:
            hints.append({"signal": text, "weight": "strong"})
    if "parameters" in img.info:
        hints.append({"signal": "PNG enthält Generator-Parameter (typisch für KI-Bildwerkzeuge).", "weight": "strong"})
    if not any(k in exif for k in ("Make", "Model")):
        hints.append({"signal": "Keine Kamera-Angaben. Das ist bei bearbeiteten, gescreenshotteten oder KI-Bildern üblich – aber kein Beweis.",
                      "weight": "weak"})
    w, h = img.size
    if w % 64 == 0 and h % 64 == 0 and max(w, h) <= 2048:
        hints.append({"signal": f"Bildmaße {w}×{h} sind Vielfache von 64 (häufig bei KI-Generatoren, aber auch sonst).", "weight": "weak"})
    return hints


@router.post("/image/analyze")
async def image_analyze(file: UploadFile = File(...), own_image: bool = Form(...), user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    """Processed in memory only – nothing is written to disk, so nothing must be deleted later."""
    if not own_image:
        raise ApiError(400, "own_image_required")
    consume(db, user, "image", "image_per_day")
    db.commit()
    raw = await file.read()
    img = _load_image(raw)
    exif = _exif(img)
    ela, ela_mean = _ela(img)
    hints = _ai_hints(img, exif, raw)
    return {"format": img.format, "size": img.size, "exif": exif, "has_gps": "GPS" in exif, "ela_image": ela, "ela_mean": ela_mean,
            "ai_hints": hints, "uncertainty": "Diese Hinweise sind Heuristiken. Sie können weder beweisen, dass ein Bild echt ist, "
                                              "noch dass es KI-generiert ist.",
            "reverse_search": reverse_links(None), "stored": False}


@router.post("/image/strip")
async def image_strip(file: UploadFile = File(...), user: User = Depends(current_user)):
    raw = await file.read()
    img = _load_image(raw)
    fmt = (img.format or "PNG").upper()
    # Rebuild from raw pixels → no EXIF/XMP/ICC metadata survives.
    clean = Image.frombytes(img.mode, img.size, img.tobytes())
    out = io.BytesIO()
    if fmt in ("JPEG", "MPO"):
        clean.convert("RGB").save(out, "JPEG", quality=95)
        mime, ext = "image/jpeg", "jpg"
    else:
        clean.save(out, "PNG")
        mime, ext = "image/png", "png"
    return StreamingResponse(io.BytesIO(out.getvalue()), media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="ohne-metadaten.{ext}"'})


def reverse_links(public_url: str | None) -> list[dict]:
    from urllib.parse import quote

    if public_url:
        u = quote(public_url, safe="")
        return [{"name": "Google Lens", "url": f"https://lens.google.com/uploadbyurl?url={u}"},
                {"name": "Bing", "url": f"https://www.bing.com/images/search?q=imgurl:{u}&view=detailv2&iss=sbi"},
                {"name": "Yandex", "url": f"https://yandex.com/images/search?rpt=imageview&url={u}"},
                {"name": "TinEye", "url": f"https://tineye.com/search?url={u}"}]
    return [{"name": "Google Lens", "url": "https://lens.google.com/"}, {"name": "Bing", "url": "https://www.bing.com/visualsearch"},
            {"name": "Yandex", "url": "https://yandex.com/images/"}, {"name": "TinEye", "url": "https://tineye.com/"}]


class ReverseIn(BaseModel):
    public_url: str = Field(max_length=2000, pattern=r"^https://")
    own_image: bool


@router.post("/image/reverse-links")
def image_reverse(body: ReverseIn, user: User = Depends(current_user)):
    if not body.own_image:
        raise ApiError(400, "own_image_required")
    return {"links": reverse_links(body.public_url),
            "note": "Nur für deine eigenen Bilder. Fadeprint führt keine Gesichtserkennung durch."}
