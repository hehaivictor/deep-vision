import copy
import os
import re
import threading
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence


def parse_env_assignment(line: str) -> Optional[tuple[str, str]]:
    text = str(line or "").strip()
    if not text or text.startswith("#"):
        return None

    if text.startswith("export "):
        text = text[len("export "):].strip()

    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", text)
    if not match:
        return None

    key = match.group(1).strip()
    raw_value = match.group(2).strip()

    if not raw_value:
        return key, ""

    if (raw_value.startswith('"') and raw_value.endswith('"')) or (raw_value.startswith("'") and raw_value.endswith("'")):
        return key, raw_value[1:-1]

    if " #" in raw_value:
        raw_value = raw_value.split(" #", 1)[0].rstrip()
    return key, raw_value


def load_env_files(project_dir: Path) -> dict[str, Any]:
    explicit_env_file = os.environ.get("DEEPVISION_ENV_FILE", "").strip()
    override_existing = str(os.environ.get("DEEPVISION_ENV_OVERRIDE", "")).strip().lower() in {"1", "true", "yes", "on", "y"}
    preexisting_env_keys = set(os.environ.keys())

    candidates: list[Path] = []
    if explicit_env_file:
        for raw_path in [part.strip() for part in explicit_env_file.split(os.pathsep) if part.strip()]:
            explicit_path = Path(raw_path).expanduser()
            if not explicit_path.is_absolute():
                explicit_path = (project_dir / explicit_path).resolve()
            candidates.append(explicit_path)

    loaded_any = False
    loaded_files: list[str] = []
    loaded_keys: set[str] = set()

    for env_path in candidates:
        if not env_path.exists() or not env_path.is_file():
            continue

        try:
            applied_keys = 0
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                parsed = parse_env_assignment(raw_line)
                if not parsed:
                    continue
                key, value = parsed
                if not override_existing and key in preexisting_env_keys:
                    continue
                os.environ[key] = value
                loaded_keys.add(key)
                applied_keys += 1
            loaded_any = True
            loaded_files.append(str(env_path))
            print(f"✅ 已加载环境变量文件: {env_path}")
            if applied_keys <= 0:
                print("ℹ️  环境变量文件已读取，但未写入新键")
        except Exception as exc:
            print(f"⚠️  读取环境变量文件失败: {env_path}, 错误: {exc}")

    if explicit_env_file and not loaded_any:
        print(f"⚠️  指定的环境变量文件不存在或不可读: {explicit_env_file}")

    return {
        "loaded_any_file": bool(loaded_any),
        "loaded_files": loaded_files,
        "loaded_keys": loaded_keys,
        "loaded_key_count": len(loaded_keys),
        "override_existing": bool(override_existing),
        "explicit_env_file": explicit_env_file,
        "explicit_env_files": [str(path) for path in candidates] if explicit_env_file else [],
    }


def default_runtime_startup_state() -> dict[str, Any]:
    return {
        "initialized": False,
        "reason": "",
        "started_at": "",
        "completed_at": "",
        "total_ms": 0.0,
        "phases": [],
        "failed_phase": "",
        "error": "",
    }


def format_runtime_startup_summary(summary: dict[str, Any]) -> str:
    phase_items = []
    for phase in list(summary.get("phases", []) or []):
        name = str(phase.get("name") or "").strip()
        elapsed_ms = float(phase.get("elapsed_ms", 0.0) or 0.0)
        if not name:
            continue
        phase_items.append(f"{name}={elapsed_ms:.1f}ms")
    phase_text = "，".join(phase_items) if phase_items else "无阶段明细"
    total_ms = float(summary.get("total_ms", 0.0) or 0.0)
    reason = str(summary.get("reason") or "").strip() or "startup"
    return f"reason={reason}，total={total_ms:.1f}ms，{phase_text}"


def log_runtime_startup_summary(summary: dict[str, Any], printer: Callable[[str], None] = print) -> None:
    if summary.get("initialized"):
        printer(f"启动初始化完成：{format_runtime_startup_summary(summary)}")
        return
    failed_phase = str(summary.get("failed_phase") or "").strip() or "unknown"
    error_text = str(summary.get("error") or "").strip() or "未知错误"
    printer(
        "启动初始化失败："
        + format_runtime_startup_summary(summary)
        + f"，failed_phase={failed_phase}，error={error_text}"
    )


class RuntimeStartupCoordinator:
    def __init__(self) -> None:
        self._state = default_runtime_startup_state()
        self._lock = threading.Lock()

    def is_initialized(self) -> bool:
        return bool(self._state.get("initialized"))

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)

    def ensure(
        self,
        *,
        steps: Sequence[tuple[str, Callable[[], None]]],
        force: bool = False,
        reason: str = "startup",
        emit_logs: bool = False,
        persist_callback: Optional[Callable[[dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._state.get("initialized") and not force:
                return copy.deepcopy(self._state)

            started_at_iso = datetime.now(timezone.utc).isoformat()
            started_at = _time.perf_counter()
            phases: list[dict[str, object]] = []
            current_phase = ""
            startup_error: Exception | None = None

            try:
                for phase_name, phase_func in steps:
                    current_phase = phase_name
                    phase_started_at = _time.perf_counter()
                    phase_func()
                    phases.append(
                        {
                            "name": phase_name,
                            "elapsed_ms": round((_time.perf_counter() - phase_started_at) * 1000.0, 2),
                        }
                    )
            except Exception as exc:
                startup_error = exc
                summary = {
                    "initialized": False,
                    "reason": str(reason or "startup"),
                    "started_at": started_at_iso,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "total_ms": round((_time.perf_counter() - started_at) * 1000.0, 2),
                    "phases": phases,
                    "failed_phase": current_phase,
                    "error": str(exc),
                }
                self._state.update(summary)
            else:
                summary = {
                    "initialized": True,
                    "reason": str(reason or "startup"),
                    "started_at": started_at_iso,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "total_ms": round((_time.perf_counter() - started_at) * 1000.0, 2),
                    "phases": phases,
                    "failed_phase": "",
                    "error": "",
                }
                self._state.update(summary)

        if persist_callback is not None:
            persist_callback(summary)
        if emit_logs:
            (log_callback or log_runtime_startup_summary)(summary)
        if startup_error is not None:
            raise startup_error
        return copy.deepcopy(summary)
