from pathlib import Path
from typing import Any, Callable, Optional


class AdminConfigCenterService:
    def __init__(
        self,
        *,
        config_resolution_mode: str,
        loaded_env_files: list[str],
        env_load_metadata: dict[str, Any],
        groups_by_source: dict[str, list[dict[str, Any]]],
        group_index: dict[str, dict[str, dict[str, Any]]],
        field_index: dict[str, dict[str, dict[str, Any]]],
        get_runtime_config: Callable[[], Any],
        get_admin_env_file_path: Callable[[], Path],
        get_admin_config_file_path: Callable[[], Path],
        get_admin_site_config_file_path: Callable[[], Path],
        get_meta_index_db_target: Callable[[], Any],
        read_env_file_map: Callable[[Path], dict[str, str]],
        read_admin_managed_config_values: Callable[[Path], dict[str, Any]],
        load_runtime_site_config_values: Callable[[], dict[str, Any]],
        format_admin_setting_form_value: Callable[[dict[str, Any], object], str],
        format_admin_setting_display_value: Callable[[dict[str, Any], object], str],
        coerce_admin_env_storage_value: Callable[[dict[str, Any], str], Any],
        coerce_admin_request_value: Callable[[dict[str, Any], object], Any],
        write_admin_env_updates: Callable[[dict[str, Any]], Path],
        write_admin_config_updates: Callable[[dict[str, Any]], Path],
        write_admin_site_config_updates: Callable[[dict[str, Any]], Path],
        runtime_source_label_getter: Callable[[str, str], str],
        runtime_setting_value_getter: Callable[..., Any],
    ) -> None:
        self._config_resolution_mode = str(config_resolution_mode or "").strip() or "auto"
        self._loaded_env_files = list(loaded_env_files or [])
        self._env_load_metadata = env_load_metadata if isinstance(env_load_metadata, dict) else {}
        self._groups_by_source = groups_by_source
        self._group_index = group_index
        self._field_index = field_index
        self._get_runtime_config = get_runtime_config
        self._get_admin_env_file_path = get_admin_env_file_path
        self._get_admin_config_file_path = get_admin_config_file_path
        self._get_admin_site_config_file_path = get_admin_site_config_file_path
        self._get_meta_index_db_target = get_meta_index_db_target
        self._read_env_file_map = read_env_file_map
        self._read_admin_managed_config_values = read_admin_managed_config_values
        self._load_runtime_site_config_values = load_runtime_site_config_values
        self._format_admin_setting_form_value = format_admin_setting_form_value
        self._format_admin_setting_display_value = format_admin_setting_display_value
        self._coerce_admin_env_storage_value = coerce_admin_env_storage_value
        self._coerce_admin_request_value = coerce_admin_request_value
        self._write_admin_env_updates = write_admin_env_updates
        self._write_admin_config_updates = write_admin_config_updates
        self._write_admin_site_config_updates = write_admin_site_config_updates
        self._runtime_source_label_getter = runtime_source_label_getter
        self._runtime_setting_value_getter = runtime_setting_value_getter

    @staticmethod
    def _get_nested_setting_value(container: Any, dotted_key: str) -> Any:
        current = container
        for segment in [part.strip() for part in str(dotted_key or "").split(".") if part.strip()]:
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current.get(segment)
        return current

    def _get_file_setting_value(
        self,
        source: str,
        key: str,
        *,
        env_values: dict[str, str],
        config_managed_values: dict[str, Any],
        site_values: dict[str, Any],
    ) -> Any:
        if source == "env":
            if key not in env_values:
                return None
            setting_meta = self._field_index["env"].get(key, {})
            return self._coerce_admin_env_storage_value(setting_meta, env_values.get(key, ""))

        if source == "site":
            return self._get_nested_setting_value(site_values, key)

        runtime_config = self._get_runtime_config()
        if key in config_managed_values:
            return config_managed_values.get(key)
        if runtime_config and hasattr(runtime_config, key):
            return getattr(runtime_config, key)
        return None

    def _build_setting_payload(
        self,
        source: str,
        setting_meta: dict[str, Any],
        *,
        env_values: dict[str, str],
        config_managed_values: dict[str, Any],
        site_values: dict[str, Any],
    ) -> dict[str, Any]:
        key = str(setting_meta.get("key") or "").strip()
        file_value = self._get_file_setting_value(
            source,
            key,
            env_values=env_values,
            config_managed_values=config_managed_values,
            site_values=site_values,
        )
        runtime_value = self._runtime_setting_value_getter(source, key, site_values=site_values)
        return {
            **setting_meta,
            "value": self._format_admin_setting_form_value(setting_meta, file_value),
            "file_value_display": self._format_admin_setting_display_value(setting_meta, file_value, mask_secret=True),
            "runtime_value_display": self._format_admin_setting_display_value(setting_meta, runtime_value, mask_secret=True),
            "runtime_source_label": self._runtime_source_label_getter(source, key),
            "value_in_file": file_value is not None,
            "runtime_matches_file": runtime_value == file_value,
        }

    def _build_source_payload(self, source: str) -> dict[str, Any]:
        source = source if source in {"env", "config", "site"} else "env"
        env_path = self._get_admin_env_file_path()
        config_path = self._get_admin_config_file_path()
        site_config_path = self._get_admin_site_config_file_path()
        env_values = self._read_env_file_map(env_path)
        config_managed_values = self._read_admin_managed_config_values(config_path)
        site_values = self._load_runtime_site_config_values()
        groups_payload = []
        for group in self._groups_by_source[source]:
            groups_payload.append(
                {
                    "id": group["id"],
                    "title": group["title"],
                    "description": group.get("description", ""),
                    "source": source,
                    "items": [
                        self._build_setting_payload(
                            source,
                            item,
                            env_values=env_values,
                            config_managed_values=config_managed_values,
                            site_values=site_values,
                        )
                        for item in group.get("items", [])
                    ],
                }
            )

        if source == "env":
            file_meta = {
                "path": str(env_path),
                "exists": env_path.exists(),
                "loaded_files": list(self._loaded_env_files),
                "override_existing": bool(self._env_load_metadata.get("override_existing")),
            }
        elif source == "config":
            runtime_config = self._get_runtime_config()
            file_meta = {
                "path": str(config_path),
                "exists": config_path.exists(),
                "has_runtime_config": bool(runtime_config),
                "managed_block_keys": sorted(config_managed_values.keys()),
            }
        else:
            file_meta = {
                "path": str(self._get_meta_index_db_target()),
                "exists": True,
                "storage": "site_config_store",
                "fallback_path": str(site_config_path),
                "top_level_keys": sorted(site_values.keys()),
            }

        return {
            "file": file_meta,
            "groups": groups_payload,
        }

    def build_payload(self) -> dict[str, Any]:
        return {
            "meta": {
                "config_resolution_mode": self._config_resolution_mode,
                "restart_hint": "配置会写入 .env / config.py。除少量动态读取项外，大多数改动需要重启服务后完全生效。",
                "source_meta": {
                    "env": {
                        "mode_label": self._config_resolution_mode,
                        "hint": "配置会写入 .env。除少量动态读取项外，大多数改动需要重启服务后完全生效。",
                    },
                    "config": {
                        "mode_label": self._config_resolution_mode,
                        "hint": "配置会写入 config.py 的托管区块。大多数改动需要重启服务后完全生效。",
                    },
                    "site": {
                        "mode_label": "共享数据库配置",
                        "hint": "配置会写入共享数据库，并由 /site-config.js 动态输出。保存后请刷新浏览器页面以应用最新前端配置。",
                    },
                },
            },
            "env": self._build_source_payload("env"),
            "config": self._build_source_payload("config"),
            "site": self._build_source_payload("site"),
        }

    def save_group(self, source: str, group_id: str, values: Optional[dict[str, Any]]) -> dict[str, Any]:
        normalized_source = str(source or "").strip().lower()
        if normalized_source not in {"env", "config", "site"}:
            normalized_source = "env"
        group = self._group_index.get(normalized_source, {}).get(str(group_id or "").strip())
        if not group:
            raise ValueError("未知的配置分组")
        if not isinstance(values, dict):
            raise ValueError("values 必须为对象")

        parsed_updates: dict[str, Any] = {}
        for item in group.get("items", []):
            key = str(item.get("key") or "").strip()
            if not key or key not in values:
                continue
            parsed_updates[key] = self._coerce_admin_request_value(item, values.get(key))

        if not parsed_updates:
            raise ValueError("至少需要提交一个配置项")

        if normalized_source == "env":
            target_path = self._write_admin_env_updates(parsed_updates)
            source_label = ".env"
        elif normalized_source == "config":
            target_path = self._write_admin_config_updates(parsed_updates)
            source_label = "config.py"
        else:
            target_path = self._write_admin_site_config_updates(parsed_updates)
            source_label = "共享数据库 site_config_store"

        return {
            "success": True,
            "message": (
                f"已写入 {source_label}，刷新浏览器页面后生效"
                if normalized_source == "site"
                else f"已写入 {source_label}，建议按需重启服务"
            ),
            "saved_keys": sorted(parsed_updates.keys()),
            "source": normalized_source,
            "group_id": group["id"],
            "target_path": str(target_path),
            "config_center": self.build_payload(),
        }
