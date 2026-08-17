"""Quản trị tenant/API key cho các công ty tích hợp External API."""
import hashlib
import secrets
import time
import uuid
import unicodedata
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from backend.config import require_admin, SEPAY_BANK_CODE, SEPAY_ACCOUNT_NUMBER
from backend.database import db
from backend.services.quota_service import usage_summary
from backend.routers.auth import hash_password, verify_password
from backend.services.enterprise_auth_service import create_session, current_account
router = APIRouter(prefix="/admin/companies", tags=["Companies"])

class CreateCompanyRequest(BaseModel):
    name: str
    slug: str
    key_name: str = "Khóa tích hợp chính"

class CreateKeyRequest(BaseModel):
    name: str = "Khóa tích hợp"
class QuotaRequest(BaseModel):
    cv_limit: int
    interview_limit: int
class EnterpriseRegisterRequest(BaseModel):
    company_name: str
    tax_code: str
    company_size: str
    email: str
    phone: str
    password: str
class OnboardingRequest(BaseModel):
    token: str
    password: str
class EnterpriseLoginRequest(BaseModel):
    account: str
    password: str
class TopUpRequest(BaseModel):
    bucket: str
    units: int

def _slug(value: str) -> str:
    import re
    result = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    if not result:
        raise HTTPException(422, "slug chỉ gồm chữ thường, số và dấu gạch ngang")
    return result

def _new_key(company_slug: str) -> str:
    return f"pai_{company_slug}_{secrets.token_urlsafe(32)}"


def _registration_slug(company_name: str, tax_code: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", company_name).encode("ascii", "ignore").decode("ascii")
    base = _slug(ascii_name or "doanh-nghiep")
    suffix = "".join(char for char in tax_code if char.isalnum())[-8:].lower()
    return _slug(f"{base}-{suffix}" if suffix else f"{base}-{uuid.uuid4().hex[:6]}")

def _store_key(company_id: str, company_slug: str, name: str) -> str:
    raw_key = _new_key(company_slug)
    with db() as conn:
        conn.execute(
            "INSERT INTO company_api_keys (id,company_id,name,key_prefix,key_hash,is_active,created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), company_id, name.strip() or "Khóa tích hợp", raw_key[:16], hashlib.sha256(raw_key.encode()).hexdigest(), 1, time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
    return raw_key

@router.get("")
def list_companies(x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        rows = conn.execute("""SELECT c.id,c.slug,c.name,c.is_active,c.created_at,c.quota_cv,c.quota_interview,
                COUNT(k.id) AS key_count,
                (SELECT COALESCE(SUM(units),0) FROM api_usage_ledger u WHERE u.company_id=c.id AND u.endpoint='score-cv' AND u.outcome='charged') AS cv_used,
                (SELECT COALESCE(SUM(units),0) FROM api_usage_ledger u WHERE u.company_id=c.id AND u.endpoint='schedule' AND u.outcome='charged') AS interview_used
            FROM companies c LEFT JOIN company_api_keys k ON k.company_id=c.id AND k.is_active=1
            GROUP BY c.id ORDER BY c.created_at DESC""").fetchall()
    return {"companies": [dict(row) for row in rows]}

@router.post("")
def create_company(body: CreateCompanyRequest, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    name = body.name.strip()
    slug = _slug(body.slug)
    if not name:
        raise HTTPException(422, "Tên công ty không được để trống")
    company_id = str(uuid.uuid4())
    with db() as conn:
        try:
            conn.execute("INSERT INTO companies (id,slug,name,is_active,created_at) VALUES (?,?,?,?,?)", (company_id, slug, name, 1, time.strftime("%Y-%m-%dT%H:%M:%S")))
        except Exception:
            raise HTTPException(409, "Slug công ty đã tồn tại")
    return {"company": {"id": company_id, "slug": slug, "name": name}, "api_key": _store_key(company_id, slug, body.key_name), "warning": "API key chỉ hiển thị một lần. Hãy lưu ở secret manager của công ty."}

@router.post("/{company_id}/keys")
def create_company_key(company_id: str, body: CreateKeyRequest, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        company = conn.execute("SELECT id,slug FROM companies WHERE id=? AND is_active=1", (company_id,)).fetchone()
    if not company:
        raise HTTPException(404, "Không tìm thấy công ty đang hoạt động")
    return {"company_id": company_id, "api_key": _store_key(company_id, company["slug"], body.name), "warning": "API key chỉ hiển thị một lần."}

@router.patch("/{company_id}/quota")
def update_company_quota(company_id: str, body: QuotaRequest, x_admin_key: str = Header(None)):
    """Platform admin configures the account-wide quota, never the company."""
    require_admin(x_admin_key)
    if not 0 <= body.cv_limit <= 1_000_000 or not 0 <= body.interview_limit <= 1_000_000:
        raise HTTPException(422, "Hạn mức phải nằm trong khoảng 0 đến 1.000.000")
    with db() as conn:
        found = conn.execute("SELECT id FROM companies WHERE id=? AND id!='company_default'", (company_id,)).fetchone()
        if not found:
            raise HTTPException(404, "Không tìm thấy tài khoản doanh nghiệp")
        conn.execute("UPDATE companies SET quota_cv=?, quota_interview=? WHERE id=?", (body.cv_limit, body.interview_limit, company_id))
    return {"success": True, "quota": usage_summary(company_id)}

@router.get("/pending/list")
def pending_companies(x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        rows=conn.execute("SELECT c.id,c.name,c.slug,c.tax_code,c.company_size,c.technical_email AS email,c.contact_phone AS phone,c.created_at FROM companies c WHERE c.is_active=0 AND c.id!='company_default' ORDER BY c.created_at DESC").fetchall()
    return {"companies":[dict(row) for row in rows]}

@router.get("/orders/pending")
def pending_quota_orders(x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        rows = conn.execute("""SELECT o.*, c.name AS company_name
            FROM company_quota_orders o JOIN companies c ON c.id=o.company_id
            WHERE o.status IN ('pending_payment','payment_submitted')
            ORDER BY o.created_at DESC""").fetchall()
    return {"orders": [dict(row) for row in rows]}

@router.get("/api-applications")
def admin_api_applications(limit: int = 200, x_admin_key: str = Header(None)):
    """Platform-only queue of applications received through company API keys."""
    require_admin(x_admin_key)
    limit = max(1, min(limit, 500))
    with db() as conn:
        rows = conn.execute("""SELECT a.id,a.name,a.email,a.phone,a.job_id,a.level,a.status,a.applied_at,
                    a.interview_link,a.interview_link_sent_at,a.application_source,c.id AS company_id,c.name AS company_name
                FROM cv_applications a JOIN companies c ON c.id=a.company_id
                WHERE a.application_source='api'
                ORDER BY a.applied_at DESC LIMIT ?""", (limit,)).fetchall()
    return {"total": len(rows), "applications": [dict(row) for row in rows]}

@router.post("/orders/{order_id}/approve")
def approve_quota_order(order_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with db() as conn:
        order = conn.execute("SELECT * FROM company_quota_orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(404, "Không tìm thấy yêu cầu mua lượt")
        if order["status"] not in ("pending_payment", "payment_submitted"):
            raise HTTPException(409, "Yêu cầu này đã được xử lý")
        column = "quota_cv" if order["bucket"] == "cv" else "quota_interview"
        conn.execute(f"UPDATE companies SET {column}=COALESCE({column},0)+? WHERE id=?", (order["units"], order["company_id"]))
        conn.execute("UPDATE company_quota_orders SET status='approved',approved_at=?,approved_by='platform_admin' WHERE id=?", (now, order_id))
    return {"success": True, "quota": usage_summary(order["company_id"])}

@router.post("/orders/{order_id}/reject")
async def reject_quota_order(order_id: str, request: Request, x_admin_key: str = Header(None)):
    """Close an unpaid/incorrect payment request without ever crediting quota."""
    require_admin(x_admin_key)
    try:
        body = await request.json()
    except Exception:
        body = {}
    reason = str(body.get("reason") or "Yêu cầu thanh toán bị từ chối bởi quản trị viên").strip()[:500]
    with db() as conn:
        order = conn.execute("SELECT id,status FROM company_quota_orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(404, "Không tìm thấy yêu cầu mua lượt")
        if order["status"] not in ("pending_payment", "payment_submitted"):
            raise HTTPException(409, "Yêu cầu này đã được xử lý")
        conn.execute("UPDATE company_quota_orders SET status='rejected',note=?,approved_at=?,approved_by='platform_admin' WHERE id=?", (reason, time.strftime("%Y-%m-%dT%H:%M:%S"), order_id))
    return {"success": True}

@router.post("/{company_id}/approve")
def approve_company(company_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        company=conn.execute("SELECT id,name,technical_email,contact_phone FROM companies WHERE id=?",(company_id,)).fetchone()
        if not company: raise HTTPException(404,"Không tìm thấy doanh nghiệp")
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("UPDATE companies SET is_active=1,approved_at=? WHERE id=?",(now,company_id))
        account = conn.execute("SELECT id FROM enterprise_accounts WHERE company_id=?", (company_id,)).fetchone()
        if account:
            conn.execute("UPDATE enterprise_accounts SET status='active',approved_at=? WHERE id=?", (now,account['id']))
        else:
            # Existing registrations from before enterprise accounts were
            # separated: create a one-time fallback only for those records.
            account_id = "EAC-"+uuid.uuid4().hex[:12].upper(); raw = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO enterprise_accounts (id,company_id,email,password_hash,status,created_at,approved_at) VALUES (?,?,?,?,?,?,?)", (account_id,company_id,company['technical_email'],hash_password(raw),'active',now,now))
            onboarding_token = raw
            return {"success":True,"onboarding_token":onboarding_token,"warning":"Tài khoản cũ chưa có mật khẩu; liên hệ quản trị viên để đặt lại mật khẩu."}
    return {"success":True,"warning":"Tài khoản doanh nghiệp đã được duyệt. Doanh nghiệp đăng nhập bằng email và mật khẩu đã đăng ký."}

# Keep API routes separate from browser routes. Nginx serves /enterprise/* as
# the React SPA, while /api/enterprise/* is always proxied to this router.
public_router=APIRouter(prefix="/api/enterprise",tags=["Enterprise"])
# A short-lived compatibility route for cached frontend bundles which posted
# directly to /enterprise/register before APIs moved under /api/enterprise.
legacy_public_router=APIRouter(tags=["Enterprise legacy"])
@public_router.post("/register")
def enterprise_register(body: EnterpriseRegisterRequest):
    company_name = body.company_name.strip()
    tax_code = body.tax_code.strip()
    company_size = body.company_size.strip()
    email = body.email.strip().lower()
    phone = body.phone.strip()
    password = body.password or ""
    if not all((company_name, tax_code, company_size, email, phone, password)):
        raise HTTPException(422, "Vui lòng điền đủ thông tin doanh nghiệp và liên hệ")
    if len(password) < 10:
        raise HTTPException(422, "Mật khẩu phải có ít nhất 10 ký tự")
    slug = _registration_slug(company_name, tax_code)
    company_id=str(uuid.uuid4()); now=time.strftime("%Y-%m-%dT%H:%M:%S")
    with db() as conn:
        duplicate = conn.execute("SELECT 1 FROM companies WHERE tax_code=?", (tax_code,)).fetchone()
        if duplicate:
            raise HTTPException(409, "Mã số thuế này đã có yêu cầu đăng ký")
        existing_enterprise = conn.execute("SELECT c.name,a.status FROM enterprise_accounts a JOIN companies c ON c.id=a.company_id WHERE LOWER(a.email)=LOWER(?)", (email,)).fetchone()
        if existing_enterprise:
            state = "đang chờ duyệt" if existing_enterprise["status"] == "pending" else "đã được duyệt"
            raise HTTPException(409, f"Email này đã có tài khoản doanh nghiệp {state} ({existing_enterprise['name']}).")
        while conn.execute("SELECT 1 FROM companies WHERE slug=?", (slug,)).fetchone():
            slug = _registration_slug(company_name, f"{tax_code}-{uuid.uuid4().hex[:4]}")
        conn.execute("INSERT INTO companies (id,slug,name,is_active,created_at,tax_code,company_size,technical_email,contact_phone) VALUES (?,?,?,?,?,?,?,?,?)", (company_id,slug,company_name,0,now,tax_code,company_size,email,phone))
        conn.execute("INSERT INTO enterprise_accounts (id,company_id,email,password_hash,status,created_at) VALUES (?,?,?,?,?,?)", ("EAC-"+uuid.uuid4().hex[:12].upper(),company_id,email,hash_password(password),"pending",now))
    return {"success":True,"message":"Đăng ký đã được ghi nhận. Sau khi CTPAI duyệt, bạn đăng nhập bằng email và mật khẩu vừa tạo để quản lý API key."}

@legacy_public_router.post("/enterprise/register", include_in_schema=False)
def legacy_enterprise_register(body: EnterpriseRegisterRequest):
    return enterprise_register(body)

def _company_user(request: Request, authorization: str | None, x_user_id: str | None):
    # Browser portal uses an HttpOnly cookie.  The Authorization header stays
    # supported for scripts and API clients; cookie avoids reverse proxies
    # accidentally dropping the header during a normal browser navigation.
    if not authorization and request.cookies.get("pai_enterprise_session"):
        authorization = f"Bearer {request.cookies['pai_enterprise_session']}"
    return current_account(authorization)

def _portal_payload(company_id: str, company_name: str | None = None, company_slug: str | None = None) -> dict:
    with db() as conn:
        if not company_name or not company_slug:
            company = conn.execute("SELECT name,slug FROM companies WHERE id=?", (company_id,)).fetchone()
            if not company:
                raise HTTPException(404, "Không tìm thấy doanh nghiệp")
            company_name, company_slug = company["name"], company["slug"]
        keys = conn.execute("SELECT id,name,key_prefix,created_at,last_used_at FROM company_api_keys WHERE company_id=? AND is_active=1 ORDER BY created_at DESC", (company_id,)).fetchall()
        orders = conn.execute("SELECT id,bucket,units,unit_price_vnd,amount_vnd,status,created_at,approved_at FROM company_quota_orders WHERE company_id=? ORDER BY created_at DESC LIMIT 12", (company_id,)).fetchall()
    return {"company":{"id":company_id,"name":company_name,"slug":company_slug},"keys":[dict(k) for k in keys],"usage":usage_summary(company_id),"orders":[dict(o) for o in orders]}

@public_router.post("/login")
def enterprise_login(body: EnterpriseLoginRequest, response: Response):
    account = body.account.strip().lower()
    with db() as conn:
        row = conn.execute("SELECT * FROM enterprise_accounts WHERE LOWER(email)=LOWER(?)", (account,)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401,"Email hoặc mật khẩu doanh nghiệp không chính xác")
    if row["status"] != "active":
        raise HTTPException(403,"Tài khoản doanh nghiệp đang chờ CTPAI phê duyệt")
    token = create_session(row["id"])
    response.set_cookie(
        key="pai_enterprise_session", value=token, max_age=60 * 60 * 24 * 14,
        httponly=True, secure=True, samesite="lax", path="/",
    )
    return {"success":True,"token":token,"account":{"email":row["email"]},"user":{"name":row["email"],"email":row["email"],"role":"company_admin"},"portal":_portal_payload(row["company_id"])}

@legacy_public_router.post("/enterprise/login", include_in_schema=False)
def legacy_enterprise_login(body: EnterpriseLoginRequest, response: Response):
    return enterprise_login(body, response)

@public_router.post("/onboarding")
def enterprise_onboarding(body: OnboardingRequest):
    if len(body.password) < 10:
        raise HTTPException(422, "Mật khẩu phải có ít nhất 10 ký tự")
    with db() as conn:
        row = conn.execute("SELECT * FROM company_onboarding_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?", (hashlib.sha256(body.token.strip().encode()).hexdigest(), int(time.time()))).fetchone()
        if not row: raise HTTPException(400, "Token khởi tạo không hợp lệ hoặc đã hết hạn")
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.password), row['user_id']))
        conn.execute("UPDATE company_onboarding_tokens SET used_at=? WHERE id=?", (int(time.time()),row['id']))
    return {"success":True,"message":"Đã thiết lập mật khẩu. Bạn có thể đăng nhập tài khoản doanh nghiệp."}
@public_router.get("/portal")
def enterprise_portal(request: Request, authorization: str = Header(None), x_user_id: str = Header(None)):
    user=_company_user(request, authorization, x_user_id)
    return _portal_payload(user['company_id'], user['name'], user['slug'])

@public_router.post("/portal/topups")
def enterprise_create_topup(body: TopUpRequest, request: Request, authorization: str = Header(None), x_user_id: str = Header(None)):
    user = _company_user(request, authorization, x_user_id)
    bucket = body.bucket.strip().lower()
    if bucket not in {"cv", "interview"}:
        raise HTTPException(422, "Loại lượt không hợp lệ")
    if not 10 <= body.units <= 100_000:
        raise HTTPException(422, "Số lượt mua phải từ 10 đến 100.000")
    # Prices are displayed transparently and are not a payment confirmation.
    # Public self-service pricing. Quota is only credited after a verified
    # payment webhook or an explicit platform-admin approval.
    unit_price = 1_000 if bucket == "cv" else 3_000
    amount = body.units * unit_price
    order_id = "ORD-" + uuid.uuid4().hex[:12].upper()
    # VietinBank only reports balance changes to SePay when the transfer
    # content starts with SEVQR. Keep this prefix in every generated QR.
    payment_code = "SEVQR" + uuid.uuid4().hex[:12].upper()
    if not SEPAY_BANK_CODE or not SEPAY_ACCOUNT_NUMBER:
        raise HTTPException(503, "Chưa cấu hình tài khoản nhận thanh toán. Vui lòng liên hệ CTPAI.")
    with db() as conn:
        conn.execute("INSERT INTO company_quota_orders (id,company_id,bucket,units,unit_price_vnd,amount_vnd,status,created_at,payment_code,provider) VALUES (?,?,?,?,?,?,?,?,?,?)", (order_id,user['company_id'],bucket,body.units,unit_price,amount,"pending_payment",time.strftime("%Y-%m-%dT%H:%M:%S"),payment_code,"sepay"))
    qr_url = "https://vietqr.app/img?" + urlencode({"acc": SEPAY_ACCOUNT_NUMBER, "bank": SEPAY_BANK_CODE, "amount": amount, "des": payment_code})
    return {"success": True, "order_id": order_id, "payment_code": payment_code, "amount_vnd": amount, "qr_url": qr_url, "message": "Quét mã QR và giữ nguyên nội dung chuyển khoản. Lượt sẽ tự cộng sau khi SePay xác nhận giao dịch."}

@public_router.get("/portal/topups/{order_id}")
def enterprise_topup_status(order_id: str, request: Request, authorization: str = Header(None), x_user_id: str = Header(None)):
    user = _company_user(request, authorization, x_user_id)
    with db() as conn:
        row = conn.execute("SELECT id,status,amount_vnd,payment_code,paid_at FROM company_quota_orders WHERE id=? AND company_id=?", (order_id, user["company_id"])).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy yêu cầu thanh toán")
    return dict(row)

@public_router.get("/portal/applications")
def enterprise_api_applications(request: Request, authorization: str = Header(None), x_user_id: str = Header(None), limit: int = 100):
    """Only applications originated by this tenant's API keys are visible."""
    user = _company_user(request, authorization, x_user_id)
    limit = max(1, min(limit, 200))
    with db() as conn:
        rows = conn.execute("""SELECT id,name,email,phone,job_id,level,status,applied_at,
                    interview_link,interview_link_sent_at
                FROM cv_applications
                WHERE company_id=? AND application_source='api'
                ORDER BY applied_at DESC LIMIT ?""", (user['company_id'], limit)).fetchall()
    return {"total": len(rows), "applications": [dict(row) for row in rows]}

@public_router.get("/portal/applications/{app_id}")
def enterprise_api_application_detail(app_id: str, request: Request, authorization: str = Header(None), x_user_id: str = Header(None)):
    """Read-only detail for the owning enterprise; never exposes another tenant."""
    user = _company_user(request, authorization, x_user_id)
    with db() as conn:
        row = conn.execute("""SELECT id,name,email,phone,job_id,level,status,applied_at,
                    cv_score,score_breakdown,ai_summary,cv_extracted_info,
                    interview_link,interview_link_sent_at
                FROM cv_applications
                WHERE id=? AND company_id=? AND application_source='api'""", (app_id, user['company_id'])).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy hồ sơ API của doanh nghiệp")
    result = dict(row)
    for field in ("score_breakdown", "cv_extracted_info"):
        if result.get(field):
            try:
                result[field] = __import__('json').loads(result[field])
            except Exception:
                pass
    return result

# Explicit preflight keeps POST routes usable behind corporate gateways and
# reverse proxies that send OPTIONS before key creation/top-up requests.
@public_router.options("/portal/keys")
@public_router.options("/portal/topups")
def enterprise_portal_preflight():
    return Response(status_code=204)
@public_router.post("/portal/keys")
def enterprise_create_key(body: CreateKeyRequest, request: Request, authorization: str = Header(None), x_user_id: str = Header(None)):
    user=_company_user(request, authorization, x_user_id)
    return {"api_key":_store_key(user['company_id'],user['slug'],body.name),"warning":"API key chỉ hiển thị một lần."}

@public_router.delete("/portal/keys/{key_id}")
def enterprise_revoke_key(key_id: str, request: Request, authorization: str = Header(None), x_user_id: str = Header(None)):
    user=_company_user(request, authorization, x_user_id)
    with db() as conn:
        cur=conn.execute("UPDATE company_api_keys SET is_active=0,revoked_at=?,revoked_reason='owner_revoked' WHERE id=? AND company_id=? AND is_active=1",(time.strftime("%Y-%m-%dT%H:%M:%S"),key_id,user['company_id']))
    if not cur.rowcount: raise HTTPException(404,"Không tìm thấy API key đang hoạt động")
    return {"success":True}
