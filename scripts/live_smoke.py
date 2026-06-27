"""Run reproducible live smoke checks against a published Dify chat app."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_message(
    *,
    endpoint: str,
    api_key: str,
    user: str,
    query: str,
    timeout: float,
    conversation_id: str = "",
) -> dict[str, Any]:
    body = json.dumps(
        {
            "inputs": {},
            "query": query,
            "response_mode": "blocking",
            "conversation_id": conversation_id,
            "user": user,
            "files": [],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "status_code": response.status,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "payload": payload,
            }
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return {
            "status_code": exc.code,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "payload": payload,
        }
    except (TimeoutError, URLError) as exc:
        return {
            "status_code": 0,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": str(exc),
        }


def answer_text(result: dict[str, Any]) -> str:
    payload = result.get("payload")
    if not isinstance(payload, dict):
        return ""
    answer = payload.get("answer")
    return answer if isinstance(answer, str) else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:5001/v1",
        help="Dify Service API v1 base URL",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()

    api_key = os.environ.get("DIFY_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DIFY_API_KEY is required")

    run_id = uuid.uuid4().hex[:10]
    user = f"skill-agent-pro-154-post-switch-{run_id}"
    marker = f"NETCHAIN-{run_id.upper()}"
    endpoint = f"{args.base_url.rstrip('/')}/chat-messages"
    results: dict[str, Any] = {
        "run_id": run_id,
        "user": user,
        "started_at_epoch": int(time.time()),
        "endpoint": endpoint,
    }

    results["memory_save"] = post_message(
        endpoint=endpoint,
        api_key=api_key,
        user=user,
        query=(
            f"请把以下内容保存为我的长期学习记忆：我的验证暗号是 {marker}，"
            "当前正在复习最长前缀匹配。请实际调用持久化记忆工具保存。"
        ),
        timeout=args.timeout,
    )
    results["memory_recall"] = post_message(
        endpoint=endpoint,
        api_key=api_key,
        user=user,
        query="这是一个全新会话。请读取我的长期学习记忆，并告诉我验证暗号是什么。",
        timeout=args.timeout,
    )
    results["bilibili"] = post_message(
        endpoint=endpoint,
        api_key=api_key,
        user=user,
        query=(
            "请实际调用 Bilibili 搜索工具，搜索“计算机网络 最长前缀匹配”教学视频。"
            "返回至少 2 个结果的标题、UP 主和链接；不要只给搜索建议。"
        ),
        timeout=args.timeout,
    )
    results["text2image"] = post_message(
        endpoint=endpoint,
        api_key=api_key,
        user=user,
        query=(
            "请实际调用文生图工具生成一张简洁的中文教学配图：OSI 七层模型，"
            "蓝色扁平信息图风格，竖向七层堆叠。请返回生成的图片，不要用 Mermaid 替代。"
        ),
        timeout=args.timeout,
    )
    results["mermaid"] = post_message(
        endpoint=endpoint,
        api_key=api_key,
        user=user,
        query=(
            "请给我一条从 CIDR 到最长前缀匹配再到 OSPF 的学习路线，"
            "必须在“后续路线”部分输出可渲染的 Mermaid flowchart。"
        ),
        timeout=args.timeout,
    )
    results["citation"] = post_message(
        endpoint=endpoint,
        api_key=api_key,
        user=user,
        query=(
            "请从知识库查找《计算机网络（第8版）》中 CIDR 与最长前缀匹配的内容。"
            "必须保留完整 document_name，同时标出分卷内页码、原 PDF 页码，并展示来源整页图片。"
        ),
        timeout=args.timeout,
    )

    checks = {
        "all_http_200": all(
            result.get("status_code") == 200
            for key, result in results.items()
            if isinstance(result, dict) and key not in {"checks"}
        ),
        "memory_cross_session": marker in answer_text(results["memory_recall"]),
        "bilibili_has_results": any(
            token in answer_text(results["bilibili"]).lower()
            for token in ("bilibili.com", "b23.tv", "bv")
        ),
        "text2image_has_file": any(
            token in answer_text(results["text2image"]).lower()
            for token in ("/files/", ".png", ".jpg", ".jpeg", ".webp")
        ),
        "mermaid_render_source": "```mermaid" in answer_text(results["mermaid"]),
        "citation_has_pdf_page_image": (
            ".pdf" in answer_text(results["citation"])
            and "页" in answer_text(results["citation"])
            and "page-images" in answer_text(results["citation"])
        ),
    }
    results["checks"] = checks
    results["finished_at_epoch"] = int(time.time())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(checks, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
