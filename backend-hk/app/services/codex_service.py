"""Codex 会话服务：封装 openai-codex SDK，管理 AsyncCodex 单例与会话/对话。

认证说明：依赖 HK 机器上预先执行 `codex login`（ChatGPT 账号）产生的本地会话，
SDK 会自动复用，无需在此处再次登录。
"""

from app.config import settings
from app.logger import get_logger
from app.services import workspace

logger = get_logger("codex")

# AsyncCodex 单例（在 lifespan 中初始化与关闭）。
_codex = None
_AsyncCodex = None
_Sandbox = None
_TextInput = None
_LocalImageInput = None


class CodexServiceError(Exception):
    """Codex 调用失败。"""


async def init_codex() -> None:
    """启动时初始化 AsyncCodex 单例。延迟导入以便未安装 SDK 时模块仍可导入。"""
    global _codex, _AsyncCodex, _Sandbox, _TextInput, _LocalImageInput
    try:
        from openai_codex import AsyncCodex, LocalImageInput, Sandbox, TextInput
    except ImportError as exc:
        logger.error("未安装 openai-codex SDK: %s", exc)
        raise RuntimeError(
            "未安装 openai-codex，请执行: pip install openai-codex"
        ) from exc
    _AsyncCodex, _Sandbox, _TextInput, _LocalImageInput = (
        AsyncCodex, Sandbox, TextInput, LocalImageInput,
    )
    _codex = AsyncCodex()
    logger.info("Codex 单例已初始化")


async def close_codex() -> None:
    global _codex
    if _codex is not None:
        try:
            await _codex.close()
        except Exception as exc:
            logger.warning("关闭 Codex 单例时出错: %s", exc)
        _codex = None


def _require_codex():
    if _codex is None:
        raise CodexServiceError("Codex 尚未初始化")
    return _codex


async def start_thread(user_id: str) -> str:
    """为用户创建新的 Codex 会话（thread），返回 thread_id。"""
    codex = _require_codex()
    cwd = workspace.workspace_dir(user_id)
    try:
        thread = await codex.thread_start(
            cwd=cwd,
            sandbox=_Sandbox.workspace_write,
            model=settings.codex_model or None,
        )
    except Exception as exc:
        logger.error("创建 Codex 会话失败: user_id=%s 错误=%s", user_id, exc)
        raise CodexServiceError(f"创建会话失败: {exc}") from exc
    logger.info("已创建 Codex 会话: user_id=%s thread_id=%s", user_id, thread.id)
    return thread.id


async def archive_thread(thread_id: str) -> None:
    """归档 Codex 会话（删除会话时调用，失败仅告警）。"""
    codex = _require_codex()
    try:
        await codex.thread_archive(thread_id)
        logger.info("已归档 Codex 会话: thread_id=%s", thread_id)
    except Exception as exc:
        logger.warning("归档 Codex 会话失败(忽略): thread_id=%s 错误=%s", thread_id, exc)


async def stream_turn(thread_id, user_id, text, image_paths):
    """恢复会话并发起一轮对话，异步产出事件字典。

    产出的事件形如：
      {"type": "delta", "text": "..."}        助手消息增量
      {"type": "done", "text": "...", "usage": {...}}  本轮完成，附带最终文本与用量
      {"type": "error", "detail": "..."}      失败
    """
    codex = _require_codex()
    cwd = workspace.workspace_dir(user_id)

    input_items = [_TextInput(text)]
    for p in image_paths:
        input_items.append(_LocalImageInput(str(p)))

    try:
        thread = await codex.thread_resume(thread_id, cwd=cwd)
    except Exception as exc:
        logger.error("恢复会话失败: thread_id=%s 错误=%s", thread_id, exc)
        yield {"type": "error", "detail": f"会话不可用: {exc}"}
        return

    try:
        turn = await thread.turn(input_items)
    except Exception as exc:
        logger.error("发起对话失败: thread_id=%s 错误=%s", thread_id, exc)
        yield {"type": "error", "detail": f"发起对话失败: {exc}"}
        return

    full_text_parts: list[str] = []
    usage: dict = {}
    try:
        async for event in turn.stream():
            method = getattr(event, "method", None)
            payload = getattr(event, "payload", None)
            if method == "item/agentMessage/delta":
                delta = getattr(payload, "delta", None) if payload else None
                if delta:
                    full_text_parts.append(delta)
                    yield {"type": "delta", "text": delta}
            elif method == "turn/completed":
                turn_obj = getattr(payload, "turn", None) if payload else None
                if turn_obj is not None:
                    u = getattr(turn_obj, "usage", None)
                    if u is not None:
                        usage = _usage_to_dict(u)
        yield {"type": "done", "text": "".join(full_text_parts), "usage": usage}
    except Exception as exc:
        logger.error("流式读取对话失败: thread_id=%s 错误=%s", thread_id, exc)
        yield {"type": "error", "detail": f"对话生成失败: {exc}"}


def _usage_to_dict(u) -> dict:
    """把 ThreadTokenUsage 转为可序列化字典（字段缺失时容错）。"""
    out: dict = {}
    for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
        val = getattr(u, key, None)
        if isinstance(val, (int, float)):
            out[key] = val
    return out
