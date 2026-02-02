#!/usr/bin/env python3
"""
场景配置加载器

负责加载、缓存和管理访谈场景配置。
支持内置场景和用户自定义场景。
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class ScenarioLoader:
    """场景配置加载器"""

    # 默认维度配置（向后兼容）
    DEFAULT_DIMENSIONS = {
        "customer_needs": {
            "name": "客户需求",
            "description": "核心痛点、期望价值、使用场景、用户角色",
            "key_aspects": ["核心痛点", "期望价值", "使用场景", "用户角色"]
        },
        "business_process": {
            "name": "业务流程",
            "description": "关键流程节点、角色分工、触发事件、异常处理",
            "key_aspects": ["关键流程", "角色分工", "触发事件", "异常处理"]
        },
        "tech_constraints": {
            "name": "技术约束",
            "description": "现有技术栈、集成接口要求、性能指标、安全合规",
            "key_aspects": ["部署方式", "系统集成", "性能要求", "安全合规"]
        },
        "project_constraints": {
            "name": "项目约束",
            "description": "预算范围、时间节点、资源限制、其他约束",
            "key_aspects": ["预算范围", "时间节点", "资源限制", "优先级"]
        }
    }

    DEFAULT_SCENARIO_ID = "product-requirement"

    def __init__(self, scenarios_dir: Path):
        """
        初始化场景加载器

        Args:
            scenarios_dir: 场景配置目录路径
        """
        self.scenarios_dir = Path(scenarios_dir)
        self.builtin_dir = self.scenarios_dir / "builtin"
        self.custom_dir = self.scenarios_dir / "custom"
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._keywords_index: Dict[str, List[str]] = {}  # keyword -> [scenario_ids]
        self._load_all_scenarios()

    def _load_all_scenarios(self) -> None:
        """加载所有场景配置到缓存"""
        # 加载内置场景
        if self.builtin_dir.exists():
            for json_file in self.builtin_dir.glob("*.json"):
                scenario = self._load_json(json_file)
                if scenario and "id" in scenario:
                    scenario["builtin"] = True
                    scenario["custom"] = False
                    self._cache[scenario["id"]] = scenario
                    self._index_keywords(scenario)

        # 加载自定义场景
        if self.custom_dir.exists():
            for json_file in self.custom_dir.glob("*.json"):
                scenario = self._load_json(json_file)
                if scenario and "id" in scenario:
                    scenario["builtin"] = False
                    scenario["custom"] = True
                    self._cache[scenario["id"]] = scenario
                    self._index_keywords(scenario)

        print(f"[ScenarioLoader] 已加载 {len(self._cache)} 个场景配置")

    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        """
        加载单个 JSON 配置文件

        Args:
            path: JSON 文件路径

        Returns:
            解析后的配置字典，加载失败返回 None
        """
        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception as e:
            print(f"[ScenarioLoader] 加载场景配置失败: {path}, 错误: {e}")
            return None

    def _index_keywords(self, scenario: Dict[str, Any]) -> None:
        """
        为场景建立关键词索引

        Args:
            scenario: 场景配置
        """
        scenario_id = scenario.get("id")
        keywords = scenario.get("keywords", [])

        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower not in self._keywords_index:
                self._keywords_index[keyword_lower] = []
            if scenario_id not in self._keywords_index[keyword_lower]:
                self._keywords_index[keyword_lower].append(scenario_id)

    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定场景配置

        Args:
            scenario_id: 场景ID

        Returns:
            场景配置字典，不存在返回 None
        """
        return self._cache.get(scenario_id)

    def get_all_scenarios(self) -> List[Dict[str, Any]]:
        """
        获取所有场景列表

        Returns:
            场景配置列表，按内置优先、名称排序
        """
        scenarios = list(self._cache.values())
        # 内置场景在前，按名称排序
        scenarios.sort(key=lambda s: (not s.get("builtin", False), s.get("name", "")))
        return scenarios

    def get_builtin_scenarios(self) -> List[Dict[str, Any]]:
        """
        获取所有内置场景

        Returns:
            内置场景列表
        """
        return [s for s in self._cache.values() if s.get("builtin", False)]

    def get_custom_scenarios(self) -> List[Dict[str, Any]]:
        """
        获取所有自定义场景

        Returns:
            自定义场景列表
        """
        return [s for s in self._cache.values() if s.get("custom", False)]

    def get_default_scenario(self) -> Dict[str, Any]:
        """
        获取默认场景配置

        Returns:
            默认场景配置（product-requirement）
        """
        default = self._cache.get(self.DEFAULT_SCENARIO_ID)
        if default:
            return default

        # 如果默认场景不存在，返回第一个内置场景或构造一个
        builtin = self.get_builtin_scenarios()
        if builtin:
            return builtin[0]

        # 兜底：返回硬编码的默认配置
        return self._create_fallback_scenario()

    def _create_fallback_scenario(self) -> Dict[str, Any]:
        """创建兜底的默认场景配置"""
        return {
            "id": "product-requirement",
            "name": "产品需求",
            "name_en": "Product Requirement",
            "description": "适用于产品需求访谈、功能规划、PRD编写",
            "icon": "clipboard-list",
            "keywords": ["需求", "产品", "功能", "PRD"],
            "builtin": True,
            "custom": False,
            "dimensions": [
                {
                    "id": dim_id,
                    "name": dim_info["name"],
                    "description": dim_info["description"],
                    "key_aspects": dim_info["key_aspects"],
                    "min_questions": 2,
                    "max_questions": 4
                }
                for dim_id, dim_info in self.DEFAULT_DIMENSIONS.items()
            ],
            "report": {
                "type": "standard",
                "template": "default"
            }
        }

    def get_default_dimensions(self) -> Dict[str, Dict[str, Any]]:
        """
        获取默认维度配置（向后兼容）

        Returns:
            默认的4维度配置字典
        """
        return self.DEFAULT_DIMENSIONS.copy()

    def match_by_keywords(self, topic: str) -> Dict[str, Any]:
        """
        基于关键词匹配场景

        Args:
            topic: 用户输入的访谈主题

        Returns:
            匹配结果 {"scenario_id": str, "confidence": float, "alternatives": list}
        """
        topic_lower = topic.lower()
        scores: Dict[str, int] = {}

        # 计算每个场景的匹配分数
        for keyword, scenario_ids in self._keywords_index.items():
            if keyword in topic_lower:
                for scenario_id in scenario_ids:
                    scores[scenario_id] = scores.get(scenario_id, 0) + 1

        if not scores:
            # 无匹配，返回默认场景
            return {
                "scenario_id": self.DEFAULT_SCENARIO_ID,
                "confidence": 0.3,
                "matched_keywords": [],
                "alternatives": []
            }

        # 按分数排序
        sorted_scenarios = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_id, best_score = sorted_scenarios[0]

        # 计算置信度（基于匹配关键词数量）
        scenario = self._cache.get(best_id, {})
        total_keywords = len(scenario.get("keywords", []))
        confidence = min(0.9, 0.4 + (best_score / max(total_keywords, 1)) * 0.5)

        # 获取匹配的关键词
        matched_keywords = [
            kw for kw in scenario.get("keywords", [])
            if kw.lower() in topic_lower
        ]

        # 获取备选方案
        alternatives = [
            {"scenario_id": sid, "score": sc}
            for sid, sc in sorted_scenarios[1:4]
        ]

        return {
            "scenario_id": best_id,
            "confidence": round(confidence, 2),
            "matched_keywords": matched_keywords,
            "alternatives": alternatives
        }

    def get_dimension_info(self, session: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        从会话配置获取维度信息（兼容旧版 DIMENSION_INFO 用法）

        Args:
            session: 会话数据

        Returns:
            维度信息字典 {dim_id: {name, description, key_aspects}}
        """
        scenario_config = session.get("scenario_config")

        if scenario_config and "dimensions" in scenario_config:
            return {
                dim["id"]: {
                    "name": dim.get("name", dim["id"]),
                    "description": dim.get("description", ""),
                    "key_aspects": dim.get("key_aspects", []),
                    "weight": dim.get("weight"),
                    "scoring_criteria": dim.get("scoring_criteria")
                }
                for dim in scenario_config["dimensions"]
            }

        # 尝试从 scenario_id 加载
        scenario_id = session.get("scenario_id")
        if scenario_id:
            scenario = self.get_scenario(scenario_id)
            if scenario and "dimensions" in scenario:
                return {
                    dim["id"]: {
                        "name": dim.get("name", dim["id"]),
                        "description": dim.get("description", ""),
                        "key_aspects": dim.get("key_aspects", []),
                        "weight": dim.get("weight"),
                        "scoring_criteria": dim.get("scoring_criteria")
                    }
                    for dim in scenario["dimensions"]
                }

        # 返回默认维度
        return self.get_default_dimensions()

    def get_dimension_order(self, session: Dict[str, Any]) -> List[str]:
        """
        获取维度顺序列表

        Args:
            session: 会话数据

        Returns:
            维度 ID 列表
        """
        scenario_config = session.get("scenario_config")

        if scenario_config and "dimensions" in scenario_config:
            return [dim["id"] for dim in scenario_config["dimensions"]]

        # 默认顺序
        return list(self.DEFAULT_DIMENSIONS.keys())

    def create_dimensions_for_session(self, scenario_id: str) -> Dict[str, Dict[str, Any]]:
        """
        为新会话创建维度数据结构

        Args:
            scenario_id: 场景ID

        Returns:
            维度数据字典 {dim_id: {coverage, items, score}}
        """
        scenario = self.get_scenario(scenario_id) or self.get_default_scenario()

        dimensions = {}
        for dim in scenario.get("dimensions", []):
            dimensions[dim["id"]] = {
                "coverage": 0,
                "items": [],
                "score": None  # 用于评估型场景
            }

        return dimensions

    def is_assessment_scenario(self, scenario_id: str) -> bool:
        """
        判断是否为评估型场景

        Args:
            scenario_id: 场景ID

        Returns:
            是否为评估型场景
        """
        scenario = self.get_scenario(scenario_id)
        if scenario:
            report_config = scenario.get("report", {})
            return report_config.get("type") == "assessment"
        return False

    def reload(self) -> None:
        """重新加载所有场景配置"""
        self._cache.clear()
        self._keywords_index.clear()
        self._load_all_scenarios()

    def save_custom_scenario(self, scenario: Dict[str, Any]) -> str:
        """
        保存自定义场景

        Args:
            scenario: 场景配置

        Returns:
            场景ID
        """
        # 确保有ID
        if "id" not in scenario:
            scenario["id"] = f"custom-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        scenario_id = scenario["id"]
        scenario["builtin"] = False
        scenario["custom"] = True

        # 保存到文件
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.custom_dir / f"{scenario_id}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(scenario, f, ensure_ascii=False, indent=2)

        # 更新缓存
        self._cache[scenario_id] = scenario
        self._index_keywords(scenario)

        return scenario_id

    def delete_custom_scenario(self, scenario_id: str) -> bool:
        """
        删除自定义场景

        Args:
            scenario_id: 场景ID

        Returns:
            是否删除成功
        """
        scenario = self._cache.get(scenario_id)
        if not scenario or scenario.get("builtin", False):
            return False

        # 删除文件
        file_path = self.custom_dir / f"{scenario_id}.json"
        if file_path.exists():
            file_path.unlink()

        # 从缓存移除
        del self._cache[scenario_id]

        # 从关键词索引移除
        for keyword, scenario_ids in list(self._keywords_index.items()):
            if scenario_id in scenario_ids:
                scenario_ids.remove(scenario_id)
                if not scenario_ids:
                    del self._keywords_index[keyword]

        return True


# 创建全局实例（延迟初始化）
_scenario_loader: Optional[ScenarioLoader] = None


def get_scenario_loader(scenarios_dir: Optional[Path] = None) -> ScenarioLoader:
    """
    获取场景加载器单例

    Args:
        scenarios_dir: 场景配置目录（首次调用时必须提供）

    Returns:
        ScenarioLoader 实例
    """
    global _scenario_loader

    if _scenario_loader is None:
        if scenarios_dir is None:
            # 默认路径
            scenarios_dir = Path(__file__).parent.parent / "data" / "scenarios"
        _scenario_loader = ScenarioLoader(scenarios_dir)

    return _scenario_loader


# 便捷函数
def get_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    """获取场景配置"""
    return get_scenario_loader().get_scenario(scenario_id)


def get_all_scenarios() -> List[Dict[str, Any]]:
    """获取所有场景"""
    return get_scenario_loader().get_all_scenarios()


def match_scenario(topic: str) -> Dict[str, Any]:
    """匹配场景"""
    return get_scenario_loader().match_by_keywords(topic)
