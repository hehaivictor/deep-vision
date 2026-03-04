#!/usr/bin/env python3
"""DeepVision 列表接口压测脚本。

特性：
- 并发压测 /api/sessions 与 /api/reports
- 自动走短信登录（测试环境可直接用 test_code）
- 输出状态码分布、错误原因、p95/p99
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * p))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return float(sorted_vals[idx])


class EndpointStats:
    def __init__(self) -> None:
        self.total = 0
        self.success = 0
        self.latencies_ms: list[float] = []
        self.status_codes: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)

    def record(
        self,
        *,
        latency_ms: float,
        status_code: int | None,
        error: str,
    ) -> None:
        self.total += 1
        if latency_ms >= 0:
            self.latencies_ms.append(latency_ms)
        if status_code is not None:
            key = str(status_code)
            self.status_codes[key] += 1
            if 200 <= status_code < 300 or status_code == 304:
                self.success += 1
        elif error:
            self.errors[error] += 1

    def to_dict(self) -> dict[str, Any]:
        success_rate = (self.success / self.total * 100.0) if self.total else 0.0
        avg_ms = (sum(self.latencies_ms) / len(self.latencies_ms)) if self.latencies_ms else 0.0
        return {
            "total": int(self.total),
            "success": int(self.success),
            "success_rate": round(success_rate, 3),
            "latency_ms": {
                "avg": round(avg_ms, 3),
                "p50": round(percentile(self.latencies_ms, 0.50), 3),
                "p95": round(percentile(self.latencies_ms, 0.95), 3),
                "p99": round(percentile(self.latencies_ms, 0.99), 3),
                "max": round(max(self.latencies_ms), 3) if self.latencies_ms else 0.0,
            },
            "status_codes": dict(sorted(self.status_codes.items(), key=lambda x: int(x[0]))),
            "errors": dict(sorted(self.errors.items(), key=lambda x: x[0])),
        }


class LoadRunner:
    def __init__(
        self,
        base_url: str,
        concurrency: int,
        duration_seconds: int,
        timeout_seconds: float,
        page_size: int,
        account: str,
        skip_login: bool,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.concurrency = max(1, int(concurrency))
        self.duration_seconds = max(1, int(duration_seconds))
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.page_size = max(1, int(page_size))
        self.account = account.strip()
        self.skip_login = bool(skip_login)

        self.session = requests.Session()
        self.endpoints = [
            f"/api/sessions?page=1&page_size={self.page_size}",
            f"/api/reports?page=1&page_size={self.page_size}",
        ]

        self.lock = threading.Lock()
        self.stats: dict[str, EndpointStats] = {ep: EndpointStats() for ep in self.endpoints}

    def login(self) -> None:
        if self.skip_login:
            return

        account = self.account or f"1{int(time.time() * 1000) % 10**10:010d}"
        send_url = f"{self.base_url}/api/auth/sms/send-code"
        login_url = f"{self.base_url}/api/auth/login/code"

        send_resp = self.session.post(
            send_url,
            json={"account": account, "scene": "login"},
            timeout=self.timeout_seconds,
        )
        send_resp.raise_for_status()
        payload = send_resp.json() if send_resp.content else {}
        code = str(payload.get("test_code") or "").strip()
        if not code:
            raise RuntimeError("未拿到 test_code，请确认服务启用测试短信模式或使用 --skip-login")

        login_resp = self.session.post(
            login_url,
            json={"account": account, "code": code, "scene": "login"},
            timeout=self.timeout_seconds,
        )
        login_resp.raise_for_status()

    def _record(self, endpoint: str, latency_ms: float, status_code: int | None, error: str) -> None:
        with self.lock:
            self.stats[endpoint].record(latency_ms=latency_ms, status_code=status_code, error=error)

    def _worker(self, end_at: float, seed: int) -> None:
        rnd = random.Random(seed)
        local_session = requests.Session()
        local_session.cookies.update(self.session.cookies)
        while time.time() < end_at:
            endpoint = self.endpoints[rnd.randrange(0, len(self.endpoints))]
            url = f"{self.base_url}{endpoint}"
            started = time.perf_counter()
            try:
                resp = local_session.get(url, timeout=self.timeout_seconds)
                latency_ms = (time.perf_counter() - started) * 1000
                self._record(endpoint, latency_ms, resp.status_code, "")
            except requests.Timeout:
                latency_ms = (time.perf_counter() - started) * 1000
                self._record(endpoint, latency_ms, None, "timeout")
            except requests.RequestException as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                self._record(endpoint, latency_ms, None, f"request_error:{type(exc).__name__}")

    def run(self) -> dict[str, Any]:
        self.login()
        started_at = utc_now_iso()
        begin = time.time()
        end_at = begin + self.duration_seconds

        with ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix="dv-loadtest") as pool:
            futures = [pool.submit(self._worker, end_at, idx + 1) for idx in range(self.concurrency)]
            for f in futures:
                f.result()

        finished_at = utc_now_iso()
        elapsed = max(0.0, time.time() - begin)

        endpoint_result = {ep: stat.to_dict() for ep, stat in self.stats.items()}
        total_requests = sum(item["total"] for item in endpoint_result.values())
        total_success = sum(item["success"] for item in endpoint_result.values())
        total_success_rate = (total_success / total_requests * 100.0) if total_requests else 0.0

        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": round(elapsed, 3),
            "config": {
                "base_url": self.base_url,
                "concurrency": self.concurrency,
                "duration_seconds": self.duration_seconds,
                "timeout_seconds": self.timeout_seconds,
                "page_size": self.page_size,
                "skip_login": self.skip_login,
            },
            "summary": {
                "total_requests": int(total_requests),
                "total_success": int(total_success),
                "total_success_rate": round(total_success_rate, 3),
                "qps": round((total_requests / elapsed), 3) if elapsed > 0 else 0.0,
            },
            "endpoints": endpoint_result,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepVision 列表接口压测脚本")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001", help="服务地址，默认 http://127.0.0.1:5001")
    parser.add_argument("--concurrency", type=int, default=20, help="并发线程数，默认 20")
    parser.add_argument("--duration", type=int, default=30, help="压测时长（秒），默认 30")
    parser.add_argument("--timeout", type=float, default=5.0, help="单请求超时（秒），默认 5")
    parser.add_argument("--page-size", type=int, default=20, help="分页大小，默认 20")
    parser.add_argument("--account", default="", help="登录手机号（测试环境可不填，自动生成）")
    parser.add_argument("--skip-login", action="store_true", help="跳过登录（仅用于无需鉴权接口）")
    parser.add_argument("--output", default="", help="输出 JSON 文件路径")
    return parser.parse_args()


def resolve_output_path(raw_output: str) -> Path:
    if raw_output:
        target = Path(raw_output).expanduser()
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = Path("data/operations") / f"loadtest-list-endpoints-{ts}.json"
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def main() -> int:
    args = parse_args()
    runner = LoadRunner(
        base_url=args.base_url,
        concurrency=args.concurrency,
        duration_seconds=args.duration,
        timeout_seconds=args.timeout,
        page_size=args.page_size,
        account=args.account,
        skip_login=args.skip_login,
    )

    result = runner.run()
    output_path = resolve_output_path(args.output)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("压测完成")
    print(f"输出文件: {output_path}")
    print(f"总请求: {result['summary']['total_requests']}")
    print(f"总成功率: {result['summary']['total_success_rate']}%")
    for endpoint, data in result["endpoints"].items():
        latency = data.get("latency_ms", {})
        print(
            f"- {endpoint}: total={data.get('total', 0)}, success_rate={data.get('success_rate', 0)}%, "
            f"p95={latency.get('p95', 0)}ms, p99={latency.get('p99', 0)}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
