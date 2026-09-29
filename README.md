# 师范生 AI 虚拟教学实训平台

面向师范生教学实训的 MVP 项目，采用 React + Vite + TypeScript 前端、FastAPI 后端和 SQLite 数据库。

## 当前状态

当前代码除原有实训与评价功能外，已接入 `StudentResponsePlan → Renderer → Validator` 回答流程：一次函数和完全平方公式共用计划、渲染校验及有界重试；失败时保留来源和错误类别，确定性备用回答/澄清不会推进虚拟学生的认知学习证据。新报告使用第二版证据评分；浏览器练习身份隔离、消息幂等、会话版本检查、服务端历史分页与旧记录显式导入均已实现。真实模型调用需在本机配置 API Key；第二版评分仍是待专业教师校准的训练参考规则。

最近一次真实课堂验收记录（2026-09-24，DeepSeek V4 Flash）包含 A/B/C 共 15 轮：只有 **2/15 轮**成功使用真实 Renderer，发生 14 次校验拒绝、13 轮降级；47 次为报告中的**调用估算值**，不是精确账单。详见 [`backend/audits/real_classroom_acceptance_20260924T015113Z.json`](backend/audits/real_classroom_acceptance_20260924T015113Z.json)。这说明 Plan/Validator/降级链路已接通，但真实 Renderer 的可靠性尚未达标，不能把这次验收描述为自然度或稳定性通过。

2026-09-29 离线回归：后端 **541 passed**；前端 production build 成功，仍有一个大 chunk 提示。该结果验证本地代码构建与测试，不替代真实模型验收。

### 升级与数据兼容

- 后端首次打开旧 SQLite 数据库时，会在原目录创建 `*.v1.bak` 备份，再执行事务迁移；旧报告保留第一版分数，不自动重算。
- 旧会话先保持未归属。在首页点击“将旧记录导入当前浏览器”后，当前浏览器可以查看历史并继续原有实训。请保留浏览器站点数据，清除站点数据会丢失该浏览器的练习访问令牌；这不是多人账号系统。
- 新会话接口要求 `X-Practice-Token` 请求头，内容为浏览器生成的 64 位十六进制随机令牌；数据库仅保存其 SHA-256 哈希。前端自动附加，无需手动配置。
- 发言请求支持 `request_id` 和 `expected_version`；前端固定使用它们进行重试与冲突恢复。旧调用者省略时仍按服务端读取版本保护保存。
- `GET /api/sessions/history?page=1&page_size=10&student_id=…` 返回 `{items,total,page,page_size}`；`GET /api/sessions/growth?rubric_version=2&student_id=…` 返回对应版本最近 20 条记录。
- 评价新增 `rubric_version` 和 `evidence`，分数允许为空；未评估不等于零分。新旧评分曲线分别展示。
- 前端默认通过同源 `/api` 请求后端，开发代理默认指向 `127.0.0.1:8000`。可用 `VITE_BACKEND_PROXY` 修改开发代理，或用 `VITE_API_BASE_URL` 显式指定 API 地址；生产部署应配置同源反向代理。

### 本轮验证入口

`backend/tests/conftest.py` 为所有测试建立独立临时数据库，阻止外网连接；正常 `pytest` 不再复用正式实训库。

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m audits.run_reliability_review
.\.venv\Scripts\python.exe -m audits.run_real_api_smoke
```

第二条命令通过实际会话 API 运行 12 段、72 轮独立课堂案例，强制使用临时数据库和 Mock；第三条命令仅在本机已配置密钥时执行三轮真实 API 验收，否则记录跳过。转录、检查结果和完整实例输出到 `backend/audits/`。

历史验收记录（2026-09-21）：534 项后端测试通过，72 轮独立课堂检查通过，前端构建及桌面/390px 交互验收通过。完整清单见 `backend/audits/reliability_fix_report.md`，完整实例见 `backend/audits/reliability_test_example.md`。其中“未配置真实模型密钥、实际调用尚未执行”仅描述该次验收当时的情况；后续真实课堂验收见上文。

MVP 基础模块 0～17 已完成；模块 19 的学生回答计划与渲染流程已接入，真实 Renderer 验收仍需继续改进；模块 18 的第二真实模型跨模型验证暂缓。当前产品演示仍以“初中数学·一次函数 k 与 b 的意义”为主场景。

- 前端 React/Vite/TypeScript 首页
- 后端 FastAPI `/api/health` 健康检查
- SQLAlchemy + SQLite 数据库初始化和核心实体模型
- Pydantic 响应 Schema
- 初始化教学场景、虚拟学生、知识状态和认知错误数据
- `/api/scenarios`、`/api/virtual-students` 查询接口
- LLM 抽象层、离线 Mock 模式和通用 Real HTTP 封装
- `POST /api/llm/respond` 教师文本到学生文本测试接口
- 规则约束下的虚拟学生状态引擎和动态 Prompt
- 完整模拟教学会话：创建/复用、发送消息、刷新恢复、结束实训
- 可解释教学行为分析：规则优先、结构化 LLM 增强和失败安全降级
- 教学评价引擎：五维可解释评分、集中权重、质性报告和真实教学证据
- 实训结束报告：ECharts 五维雷达图、行为统计、历史列表和成长曲线
- `POST /api/sessions`、`GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/messages`、`POST /api/sessions/{session_id}/end`
- `GET /api/sessions/{session_id}/evaluation`、`POST /api/sessions/{session_id}/evaluation`
- `GET /api/sessions/history`
- 会话详情返回逐轮行为分析和教学行为统计
- 前端模拟课堂页面和有限训练状态展示
- 仅允许本地前端开发地址的 CORS
- 认知过程可视化：当前状态、误解演化、状态轨迹和教学行为时间线
- 会话级学生画像、引擎状态和认知轨迹快照，历史结果不受后续种子或规则调整影响
- Mock 学生按当前认知状态和 A/B/C 画像差异化回答，并支持一次函数常见同义问法与具体函数解析
- 学生回答计划与渲染：根据课堂任务、学生状态和知识边界生成结构化回答计划；Mock/Real Renderer 共用校验流程，最多重试一次，备用回答与澄清带来源及降级原因，并不推进虚拟学生的认知学习证据
- 通用课堂多意图识别：确定性规则结合离线组合语义评分、会话上下文和开放集拒绝，支持未收录的课堂同义表达并对跑题采用高门槛判定
- 比赛 Demo 启动脚本：`start-demo.cmd`，固定使用本地 Mock 模式
- 独立的虚拟学生一致性验证框架：案例、规则指标、Mock/Real 验证和 JSON 报告
- 支持一次函数 `linear_kb` 与完全平方公式 `binomial_square` 两类认知错误验证，并提供 Student A / Student B / Student C 验证画像

## 启动后端

Windows 环境统一使用 Python 3.12：

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

后端地址：<http://127.0.0.1:8000>

健康检查：<http://127.0.0.1:8000/api/health>

## 从全新终端启动并演示

比赛演示可直接双击仓库根目录的 `start-demo.cmd`。脚本会打开两个终端，固定使用 `DEMO MODE / MOCK`，启动本地 Mock 后端和前端，不调用真实 LLM。

终端 1：启动后端 Mock 演示模式。

```powershell
# 将 <repo-path> 替换为本地仓库路径
cd "<repo-path>"
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:LLM_PROVIDER = "mock"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

终端 2：启动前端。

```powershell
cd "<repo-path>\frontend"
npm ci
npm run dev
```

如果 PowerShell 阻止 npm 入口，将两条 npm 命令替换为 `npm.cmd ci` 和 `npm.cmd run dev`。

打开 <http://127.0.0.1:5173>，按以下路径演示：选择“一次函数：k 与 b 的意义” → 选择学生 A → 开始实训 → 输入“老师，b 越大时直线会怎样？”观察学生暴露混淆 → 输入“不对，b 不影响斜率，只改变截距位置。”完成几轮教学 → 结束实训 → 查看五维雷达图、行为统计、评价建议和实训历史。

运行测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

如果 PowerShell 阻止 npm 入口，将构建命令替换为 `npm.cmd run build`。

## 虚拟学生一致性验证

验证框架当前包含一次函数 `linear_kb` 和完全平方公式 `binomial_square` 两类认知错误，并支持 Student A / Student B / Student C 验证画像；其中 `binomial_square` 当前仅使用 Student A，Student B / Student C 用于 `linear_kb` 验证。验证覆盖角色一致性、知识边界、错误认知保持性、可纠正性、语言自然度和状态一致性。默认 Mock 验证不调用真实 API，报告写入 `backend/validation/reports/`，该目录中的生成文件不会提交 Git。

运行 Mock 验证：

```powershell
cd backend
$env:LLM_PROVIDER = "mock"
$env:RUNS_PER_CASE = "3"
.\.venv\Scripts\python.exe -m validation.runner
```

运行真实 LLM 验证前，必须同时显式设置以下开关；程序会先输出 provider、模型、重复次数和预计调用数，不会输出 API Key：

```powershell
cd backend
$env:LLM_PROVIDER = "real"
$env:RUN_REAL_LLM_VALIDATION = "true"
$env:RUNS_PER_CASE = "3"
.\.venv\Scripts\python.exe -m validation.runner --case-id trajectory_effective_correction
```

真实验证失败会保存为报告中的失败案例，不会影响正式业务测试。验证指标是虚拟学生模拟一致性检查，不代表真实教育效果或专业教师评价。

核心数据接口：

- `GET /api/scenarios`
- `GET /api/scenarios/{scenario_id}`
- `GET /api/virtual-students`
- `GET /api/virtual-students/{student_id}`

## 模拟教学流程

默认使用 Mock LLM，可在无 API Key、无网络时完整演示：

1. 前端选择教学场景和虚拟学生，点击“开始实训”。相同场景和学生已有进行中会话时，后端会复用该会话，避免重复创建。
2. 在模拟课堂输入教师话语。后端读取并释放数据库快照，分析教学行为，生成回答计划，调用并校验生成器；最后校验会话版本，将完整师生对话、行为和状态快照一次提交。
3. 刷新页面会从浏览器保存的会话 ID 恢复完整对话；结束实训后，已完成会话不能继续发送消息。

每个会话会冻结创建时的学生画像，并在每轮对话中原子保存引擎状态与完整认知轨迹。升级到该版本后，启动时会为旧会话执行一次性快照回填；此后调整种子数据或状态规则不会改写已经保存的历史轨迹。

每轮教师输入还会生成结构化教学行为记录，当前支持：讲解、提问、引导式提问、举例、反馈、纠错、理解确认、直接给答案、非评分课堂互动和非教学话题。课堂意图先通过离线组合语义特征形成多标签结果，结合会话上下文处理短句；只有明确的领域漂移或开放集拒绝才会判为跑题。行为分析采用规则统计优先、LLM 结构化增强；LLM 输出会经过 Pydantic 校验，异常时使用安全默认值并记录日志，不会中断会话。课堂管理、过渡、结束语和非教学话题均不进入知识准确率分母。

结束实训时会自动生成教学评价。五个维度为知识准确性、提问与引导、教学反馈、错误诊断能力、支架式教学，固定权重集中配置。第二版按独立任务和引用证据评分；至少三个独立实质任务、知识准确性可评估且可评估权重达到 80% 时生成总分。未评估返回空值。评价仅用于训练辅助，尚待专业教师校准。

实训结束页展示评价证据、教学行为统计和关键片段；五维均可评估时才绘制雷达图。首页和报告页均可查看分页历史并打开原报告。成长曲线独立查询同学生筛选、同评分版本的最近 20 条记录，至少两条具有总分的记录时绘制，空值不会视为零分。

## LLM 配置

默认使用无需网络和 API Key 的 Mock 模式：

```env
LLM_PROVIDER=mock
```

Real 模式使用后端环境变量，API Key 只放在未提交的 `.env` 中：

```env
LLM_PROVIDER=real
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=your-key
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=15
```

测试接口示例：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/llm/respond `
  -ContentType 'application/json' `
  -Body '{"teacher_text":"请比较 k 和 b 分别会改变什么。"}'
```

前端地址：<http://127.0.0.1:5173>
