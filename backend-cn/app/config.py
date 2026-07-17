from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "aiprovider"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    # 积分参数(可配置)
    initial_credits: int = 20
    cost_per_image: int = 1
    cost_per_chat: int = 1            # 每条聊天消息消耗积分
    max_chat_images: int = 4          # 单条消息最多上传图片数

    # 充值套餐(后端权威定义，前端不可篡改金额)
    # 格式: "package_id:credits:price" 逗号分隔
    recharge_packages: str = "p50:50:9,p120:120:19,p300:300:39"

    # 香港 AI 网关
    hk_base_url: str = "http://127.0.0.1:9000"
    hk_internal_secret: str = "change-me"
    hk_timeout_seconds: int = 120

    max_upload_mb: int = 10
    max_image_dimension: int = 2000  # 上传图片宽高超此值自动等比缩放

    cors_origins: str = "http://localhost:5173"

    log_level: str = "INFO"

    # 本地图片存储目录
    cn_storage_dir: str = "./storage"

    # 单用户同时进行中的生成任务上限
    max_concurrent_generations: int = 5

    # 是否允许新用户注册
    enable_registration: bool = True

    # 微信支付(Native 支付)
    # 以下全部留空时充值功能保持占位提示，配置后自动启用
    # APP_ID: 微信公众号/小程序 AppID，在公众平台后台获取
    # MCH_ID: 商户号(10位数字)，在商户平台→账户中心→商户信息查看
    # API_V3_KEY: API v3 密钥(32位)，在商户平台设置，用于回调通知 AES-256-GCM 解密
    # PRIVATE_KEY_PATH: 商户私钥 .pem 文件路径，用于签名 API 请求
    # CERT_SERIAL_NO: 商户证书序列号(40位十六进制)，在商户平台→API安全→管理证书处查看
    # NOTIFY_URL: 支付成功回调 URL，需 https 公网可达
    wechat_app_id: str = ""
    wechat_mch_id: str = ""
    wechat_api_v3_key: str = ""
    wechat_private_key_path: str = ""
    wechat_cert_serial_no: str = ""
    wechat_notify_url: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def recharge_package_list(self) -> list[dict]:
        """解析充值套餐配置为 [{id, credits, price}, ...]。"""
        packages: list[dict] = []
        for item in self.recharge_packages.split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split(":")
            if len(parts) != 3:
                continue
            pid, credits_str, price_str = parts
            try:
                packages.append(
                    {"id": pid.strip(), "credits": int(credits_str), "price": float(price_str)}
                )
            except ValueError:
                continue
        return packages

    @property
    def recharge_package_map(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.recharge_package_list}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def wechat_configured(self) -> bool:
        return bool(
            self.wechat_app_id
            and self.wechat_mch_id
            and self.wechat_api_v3_key
            and self.wechat_private_key_path
            and self.wechat_cert_serial_no
            and self.wechat_notify_url
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
