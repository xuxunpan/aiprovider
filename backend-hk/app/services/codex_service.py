"""Codex 会话服务：封装 openai-codex SDK，管理 AsyncCodex 单例与会话/对话。

认证说明：依赖 HK 机器上预先执行 `codex login`（ChatGPT 账号）产生的本地会话，
SDK 会自动复用，无需在此处再次登录。
"""

import asyncio
import traceback

from app.config import settings
from app.logger import get_logger
from app.services import workspace

logger = get_logger("codex")

# 流式保护：首个事件最长等待秒数；超过则视为 Codex 后端无响应并报错，避免前端永久转圈。
FIRST_EVENT_TIMEOUT_S = 300.0
# 相邻事件间最长间隔秒数；超过则视为流卡死并报错。
IDLE_EVENT_TIMEOUT_S = 600.0

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
        from openai_codex import AsyncCodex, CodexConfig, LocalImageInput, Sandbox, TextInput
    except ImportError as exc:
        logger.error("未安装 openai-codex SDK: %s", exc)
        raise RuntimeError(
            "未安装 openai-codex，请执行: pip install openai-codex"
        ) from exc
    _AsyncCodex, _Sandbox, _TextInput, _LocalImageInput = (
        AsyncCodex, Sandbox, TextInput, LocalImageInput,
    )

    env_overrides: dict[str, str] | None = None
    if settings.codex_proxy:
        proxy = settings.codex_proxy
        env_overrides = {
            "http_proxy": proxy,
            "https_proxy": proxy,
            "HTTP_PROXY": proxy,
            "HTTPS_PROXY": proxy,
        }
        logger.info("Codex 启用代理: %s", proxy)

    config = CodexConfig(env=env_overrides)
    _codex = AsyncCodex(config=config)
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
      {"type": "delta", "text": "..."}                  助手消息增量
      {"type": "rebuilt", "thread_id": "..."}            rollout 丢失，已新建 thread（调用方需回写）
      {"type": "done", "text": "...", "usage": {...}}    本轮完成，附带最终文本与用量
      {"type": "error", "detail": "..."}                 失败

    说明：thread_resume 要求服务端已存在该 thread 的 rollout；新建 thread 在首轮对话
    完成前没有 rollout，resume 会报 "no rollout found"。因此当 resume 失败时回退到
    thread_start，用返回的 Thread 对象直接发起 turn，并通过 rebuilt 事件回传新 thread_id。
    """
    codex = _require_codex()
    cwd = workspace.workspace_dir(user_id)

    input_items = [_TextInput(text)]
    for p in image_paths:
        input_items.append(_LocalImageInput(str(p)))

    thread = None
    try:
        thread = await codex.thread_resume(thread_id, cwd=cwd)
    except Exception as exc:
        if "no rollout found" not in str(exc).lower():
            logger.error("恢复会话失败: thread_id=%s 错误=%s", thread_id, exc)
            yield {"type": "error", "detail": f"会话不可用: {exc}"}
            return
        logger.warning(
            "会话 rollout 丢失，回退新建: user_id=%s old_thread=%s 错误=%s",
            user_id, thread_id, exc,
        )
        try:
            thread = await codex.thread_start(
                cwd=cwd,
                sandbox=_Sandbox.workspace_write,
                model=settings.codex_model or None,
            )
        except Exception as start_exc:
            logger.error(
                "回退新建会话也失败: user_id=%s old_thread=%s 错误=%s",
                user_id, thread_id, start_exc,
            )
            yield {"type": "error", "detail": f"会话不可用: {exc}"}
            return
        logger.info(
            "已重建会话: user_id=%s old_thread=%s new_thread=%s",
            user_id, thread_id, thread.id,
        )
        yield {"type": "rebuilt", "thread_id": thread.id}

    try:
        logger.info(
            "准备发起对话: thread_id=%s user_id=%s input_items=%d",
            thread.id, user_id, len(input_items),
        )
        turn = await thread.turn(input_items)
        logger.info(
            "对话已发起: thread_id=%s turn_id=%s 等待流式事件...",
            thread.id, getattr(turn, "id", "?"),
        )
    except Exception as exc:
        logger.error(
            "发起对话失败: thread_id=%s 错误=%s\n%s",
            thread.id, exc, traceback.format_exc(),
        )
        yield {"type": "error", "detail": f"发起对话失败: {exc}"}
        return

    full_text_parts: list[str] = []
    usage: dict = {}
    event_count = 0
    try:
        # 给 SDK 流加首事件/空闲超时保护，避免 next_turn_notification 永久阻塞。
        stream_iter = turn.stream()

        def _handle_event(event):
            """处理一个事件，返回 (kind, value)。
            kind: "delta" -> value=delta 文本；"usage" -> value=usage dict；
                  "completed" -> 流结束；"error" -> value=错误信息(流终止)；
                  "other" -> 忽略。
            """
            nonlocal usage
            method = getattr(event, "method", None)
            payload = getattr(event, "payload", None)
            logger.info(
                "收到事件: thread_id=%s turn_id=%s method=%s payload=%s",
                thread.id, getattr(turn, "id", "?"), method,
                payload,
            )
            # Codex 后端主动报错（配额超限、内部错误等）
            if method == "error":
                err = getattr(payload, "error", None) if payload else None
                msg = getattr(err, "message", None) if err else None
                detail = msg or str(payload) or "Codex 后端错误"
                will_retry = getattr(err, "will_retry", False) if err else False
                if will_retry:
                    return ("other", None)
                logger.error(
                    "Codex 后端报错: thread_id=%s turn_id=%s 错误=%s",
                    thread.id, getattr(turn, "id", "?"), detail,
                )
                return ("error", detail)
            if method == "item/agentMessage/delta":
                delta = getattr(payload, "delta", None) if payload else None
                if delta:
                    full_text_parts.append(delta)
                    return ("delta", delta)
                return ("other", None)
            if method == "turn/completed":
                turn_obj = getattr(payload, "turn", None) if payload else None
                if turn_obj is not None:
                    # 优先检查 turn.error（失败场景）
                    turn_err = getattr(turn_obj, "error", None)
                    if turn_err is not None:
                        err_msg = (
                            getattr(turn_err, "message", None)
                            or str(turn_err)
                            or "对话失败"
                        )
                        logger.error(
                            "对话以失败结束: thread_id=%s turn_id=%s 错误=%s",
                            thread.id, getattr(turn, "id", "?"), err_msg,
                        )
                        return ("error", err_msg)
                    u = getattr(turn_obj, "usage", None)
                    if u is not None:
                        usage = _usage_to_dict(u)
                return ("completed", None)
            return ("other", None)

        try:
            first_event = await asyncio.wait_for(
                stream_iter.__anext__(), timeout=FIRST_EVENT_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            logger.error(
                "等待首事件超时(%ds)，Codex 后端无响应: thread_id=%s turn_id=%s",
                int(FIRST_EVENT_TIMEOUT_S), thread.id, getattr(turn, "id", "?"),
            )
            yield {"type": "error", "detail": "Codex 后端无响应，请稍后重试"}
            return
        except StopAsyncIteration:
            logger.error(
                "流式迭代器立即结束(无事件): thread_id=%s turn_id=%s",
                thread.id, getattr(turn, "id", "?"),
            )
            yield {"type": "error", "detail": "对话未产生任何输出"}
            return

        kind, value = _handle_event(first_event)
        event_count += 1
        if kind == "delta":
            yield {"type": "delta", "text": value}
        elif kind == "error":
            yield {"type": "error", "detail": value}
            return
        elif kind == "completed":
            logger.info(
                "对话完成(首事件即结束): thread_id=%s turn_id=%s 总事件数=%d",
                thread.id, getattr(turn, "id", "?"), event_count,
            )
            yield {"type": "done", "text": "".join(full_text_parts), "usage": usage}
            return

        while True:
            try:
                event = await asyncio.wait_for(
                    stream_iter.__anext__(), timeout=IDLE_EVENT_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                logger.error(
                    "等待事件空闲超时(%ds): thread_id=%s turn_id=%s 已收事件数=%d",
                    int(IDLE_EVENT_TIMEOUT_S), thread.id,
                    getattr(turn, "id", "?"), event_count,
                )
                yield {"type": "error", "detail": "对话生成超时，已退还积分"}
                return
            except StopAsyncIteration:
                logger.info(
                    "流式结束(迭代器终止): thread_id=%s turn_id=%s 总事件数=%d",
                    thread.id, getattr(turn, "id", "?"), event_count,
                )
                break
            event_count += 1
            kind, value = _handle_event(event)
            if kind == "delta":
                yield {"type": "delta", "text": value}
            elif kind == "error":
                yield {"type": "error", "detail": value}
                return
            elif kind == "completed":
                logger.info(
                    "对话完成: thread_id=%s turn_id=%s 总事件数=%d",
                    thread.id, getattr(turn, "id", "?"), event_count,
                )
                break

        yield {"type": "done", "text": "".join(full_text_parts), "usage": usage}
    except Exception as exc:
        logger.error(
            "流式读取对话失败: thread_id=%s 错误=%s\n%s",
            thread_id, exc, traceback.format_exc(),
        )
        yield {"type": "error", "detail": f"对话生成失败: {exc}"}


def _usage_to_dict(u) -> dict:
    """把 ThreadTokenUsage 转为可序列化字典（字段缺失时容错）。"""
    out: dict = {}
    for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
        val = getattr(u, key, None)
        if isinstance(val, (int, float)):
            out[key] = val
    return out
