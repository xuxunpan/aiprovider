import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives import hashes, serialization

from app.config import settings
from app.logger import get_logger

logger = get_logger("wechat_pay")

WECHAT_API_BASE = "https://api.mch.weixin.qq.com"

_private_key = None
_platform_certs: dict[str, bytes] = {}
_platform_certs_fetched_at: float = 0.0
PLATFORM_CERT_TTL = 12 * 3600  # 平台证书刷新间隔(12小时)


def _ensure_configured() -> bool:
    if not settings.wechat_configured:
        logger.warning("微信支付未配置，跳过")
        return False
    return True


def _load_private_key():
    global _private_key
    if _private_key is not None:
        return _private_key
    path = settings.wechat_private_key_path
    if not path or not os.path.isfile(path):
        logger.error("微信支付商户私钥文件不存在: %s", path)
        return None
    with open(path, "rb") as f:
        _private_key = serialization.load_pem_private_key(f.read(), password=None)
    return _private_key


def _build_signature(method: str, url_path: str, body: str, timestamp: int, nonce_str: str) -> str:
    private_key = _load_private_key()
    if private_key is None:
        raise RuntimeError("无法加载商户私钥")

    message = f"{method.upper()}\n{url_path}\n{timestamp}\n{nonce_str}\n{body}\n"
    signed = private_key.sign(message.encode("utf-8"), hashes.SHA256())
    return base64.b64encode(signed).decode("utf-8")


def _build_auth_header(method: str, url_path: str, body: str) -> dict:
    timestamp = int(time.time())
    nonce_str = uuid.uuid4().hex[:32]
    signature = _build_signature(method, url_path, body, timestamp, nonce_str)
    auth_value = (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{settings.wechat_mch_id}",'
        f'nonce_str="{nonce_str}",signature="{signature}",'
        f'timestamp="{timestamp}",serial_no="{settings.wechat_cert_serial_no}"'
    )
    return {
        "Authorization": auth_value,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "aiprovider/1.0",
    }


async def _download_platform_certs(force: bool = False) -> dict[str, bytes]:
    global _platform_certs, _platform_certs_fetched_at
    if not force and _platform_certs and (time.time() - _platform_certs_fetched_at < PLATFORM_CERT_TTL):
        return _platform_certs

    try:
        url_path = "/v3/certificates"
        headers = _build_auth_header("GET", url_path, "")
        async with httpx.AsyncClient(timeout=settings.hk_timeout_seconds) as client:
            resp = await client.get(f"{WECHAT_API_BASE}{url_path}", headers=headers)
            resp.raise_for_status()
            data = resp.json()

        for cert_info in data.get("data", []):
            serial_no = cert_info["serial_no"]
            raw = cert_info["encrypt_certificate"]
            plain = _aes_decrypt(
                raw["associated_data"],
                raw["nonce"],
                raw["ciphertext"],
            )
            _platform_certs[serial_no] = plain.encode("utf-8")
        _platform_certs_fetched_at = time.time()
        logger.info("平台证书已下载: 共 %d 个", len(_platform_certs))
    except Exception as e:
        logger.error("下载平台证书失败: %s", e)
    return _platform_certs


def _aes_decrypt(associated_data: str, nonce: str, ciphertext: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = settings.wechat_api_v3_key.encode("utf-8")
    aesgcm = AESGCM(key)
    decrypted = aesgcm.decrypt(
        nonce.encode("utf-8"),
        base64.b64decode(ciphertext),
        associated_data.encode("utf-8"),
    )
    return decrypted.decode("utf-8")


async def create_native_order(package: dict, user_id: str) -> tuple[str | None, str | None]:
    if not _ensure_configured():
        return None, None

    out_trade_no = f"R{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"
    amount_cents = int(package["price"] * 100)

    body = {
        "appid": settings.wechat_app_id,
        "mchid": settings.wechat_mch_id,
        "description": f"充值{package['credits']}积分",
        "out_trade_no": out_trade_no,
        "notify_url": settings.wechat_notify_url,
        "amount": {"total": amount_cents, "currency": "CNY"},
    }
    body_str = json.dumps(body, ensure_ascii=False)
    url_path = "/v3/pay/transactions/native"

    try:
        headers = _build_auth_header("POST", url_path, body_str)
        async with httpx.AsyncClient(timeout=settings.hk_timeout_seconds) as client:
            resp = await client.post(
                f"{WECHAT_API_BASE}{url_path}",
                headers=headers,
                content=body_str,
            )
            logger.info(
                "微信下单响应: status=%s request_id=%s body=%s",
                resp.status_code,
                resp.headers.get("Request-ID", ""),
                resp.text[:500],
            )
            resp.raise_for_status()
            data = resp.json()
            code_url = data.get("code_url", "")
            logger.info("微信下单成功: out_trade_no=%s code_url=%s", out_trade_no, code_url)
            return out_trade_no, code_url
    except Exception as e:
        logger.error("微信下单失败: out_trade_no=%s error=%s", out_trade_no, e)
        return out_trade_no, None


async def verify_notify(
    signature: str,
    serial_no: str,
    timestamp: str,
    nonce: str,
    body_bytes: bytes,
) -> dict | None:
    if not _ensure_configured():
        return None

    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            logger.warning("回调时间戳偏差过大, 拒绝重放: timestamp=%s now=%s", timestamp, int(time.time()))
            return None
    except (ValueError, TypeError):
        logger.warning("回调时间戳格式非法: %s", timestamp)
        return None

    certs = await _download_platform_certs()
    cert_pem = certs.get(serial_no)
    if cert_pem is None:
        logger.warning("找不到序列号对应的平台证书, 尝试刷新: serial=%s", serial_no)
        certs = await _download_platform_certs(force=True)
        cert_pem = certs.get(serial_no)
    if cert_pem is None:
        logger.error("回调验签失败: 找不到序列号对应的平台证书 serial=%s", serial_no)
        return None

    try:
        from cryptography.x509 import load_pem_x509_certificate
        from cryptography.hazmat.primitives.asymmetric import padding
        cert = load_pem_x509_certificate(cert_pem)
        public_key = cert.public_key()
        message = f"{timestamp}\n{nonce}\n{body_bytes.decode('utf-8')}\n"
        public_key.verify(
            base64.b64decode(signature),
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as e:
        logger.error("回调验签异常: %s", e)
        return None

    try:
        body = json.loads(body_bytes)
    except Exception as e:
        logger.error("回调body JSON解析失败: %s", e)
        return None
    resource = body.get("resource", {})
    if resource.get("algorithm") != "AEAD_AES_256_GCM":
        logger.error("回调加密算法不匹配: %s", resource.get("algorithm"))
        return None

    try:
        plain_text = _aes_decrypt(
            resource.get("associated_data", ""),
            resource["nonce"],
            resource["ciphertext"],
        )
        decrypted = json.loads(plain_text)
    except Exception as e:
        logger.error("回调解密失败: %s", e)
        return None

    logger.info(
        "微信支付回调验证成功: out_trade_no=%s trade_state=%s",
        decrypted.get("out_trade_no"),
        decrypted.get("trade_state"),
    )
    return decrypted


async def query_order(out_trade_no: str) -> dict | None:
    if not _ensure_configured():
        return None

    url_path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={settings.wechat_mch_id}"
    try:
        headers = _build_auth_header("GET", url_path, "")
        async with httpx.AsyncClient(timeout=settings.hk_timeout_seconds) as client:
            resp = await client.get(f"{WECHAT_API_BASE}{url_path}", headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("微信查单失败: out_trade_no=%s error=%s", out_trade_no, e)
        return None
