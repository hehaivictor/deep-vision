# Tests 局部入口

这个目录承载 DeepVision 的单元回归、harness 场景语料和 evaluator 校准样本。

## 先看什么

- 仓库总入口：[../AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)
- Harness 索引：[../docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)
- Evaluator 校准样本说明：[../docs/agent/evaluator-calibration.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/evaluator-calibration.md)

## 当前测试层次

- `test_scripts_comprehensive.py`：harness 脚本与文档入口回归
- `test_api_comprehensive.py`：主接口与运行态回归
- `test_security_regression.py`：权限、分享、License 门禁与实例隔离
- `test_solution_payload.py`：方案页 payload 与文案语义回归
- `harness_scenarios/`：nightly evaluator 场景
- `harness_calibration/`：evaluator 评分标尺样本

## 局部边界

- 新测试优先使用临时目录隔离 `DATA_DIR`、鉴权库和索引库，不要污染仓库下的 `data/`
- 不要为了让测试变绿而削弱真实不变量；如果是 wording drift，优先进 calibration，而不是放松业务边界
- 业务回归、场景语料和校准样本分层维护，不要混成同一类资产

## 改动后先跑

- 最小脚本回归：`python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`
- 主接口回归：`python3 -m unittest tests.test_api_comprehensive`
- 安全与权限回归：`python3 -m unittest tests.test_security_regression`
- 方案页载荷回归：`python3 -m unittest tests.test_solution_payload`
- 场景 evaluator：`python3 scripts/agent_eval.py --tag nightly`

## 不要做什么

- 不要把 CI 偶发误红直接当成业务回归，先区分是 calibration 问题还是功能问题
- 不要把本地产物、latest.json 或临时 artifact 提交进仓库
