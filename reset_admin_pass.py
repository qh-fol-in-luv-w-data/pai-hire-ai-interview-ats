"""Emergency local admin reset. Never embeds a password in source."""
import argparse
import getpass
import hashlib
import os
import sqlite3
from pathlib import Path

def hash_password(password: str) -> str:
    salt_bytes = os.urandom(16)
    salt_hex = salt_bytes.hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        100000
    ).hex()
    return f"{salt_hex}:{pwd_hash}"

parser = argparse.ArgumentParser(description="Đặt lại mật khẩu tài khoản quản trị cục bộ")
parser.add_argument("--email", required=True)
parser.add_argument("--db", default=str(Path(__file__).with_name("ats_phongvan.db")))
args = parser.parse_args()
password = getpass.getpass("Mật khẩu mới (tối thiểu 10 ký tự): ")
if len(password) < 10:
    raise SystemExit("Mật khẩu phải có ít nhất 10 ký tự")
with sqlite3.connect(args.db) as conn:
    updated = conn.execute("UPDATE users SET password_hash=? WHERE LOWER(email)=LOWER(?) AND role IN ('admin','platform_admin')", (hash_password(password), args.email)).rowcount
if not updated:
    raise SystemExit("Không tìm thấy tài khoản quản trị cần đặt lại")
print("Đã đặt lại mật khẩu quản trị.")
