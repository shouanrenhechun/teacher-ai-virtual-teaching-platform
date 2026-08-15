# 师范生 AI 虚拟教学实训平台

面向师范生教学实训的 MVP 项目，采用 React + Vite + TypeScript 前端、FastAPI 后端和 SQLite 数据库。

## 当前模块

当前已完成模块 0～8：

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

## 启动后端

Windows 环境统一使用 Python 3.12：

```powershell
# 在仓库根目录执行
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

后端地址：<http://127.0.0.1:8000>

健康检查：<http://127.0.0.1:8000/api/health>

## 从全新终端启动并演示

终端 1：启动后端 Mock 演示模式。

```powershell
cd "C:\Users\18622\Documents\ChatGPT\师范生 AI 虚拟教学实训平台"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:LLM_PROVIDER = "mock"
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

终端 2：启动前端。

```powershell
cd "C:\Users\18622\Documents\ChatGPT\师范生 AI 虚拟教学实训平台\frontend"
npm install
npm run dev
```

如果 PowerShell 阻止 npm 入口，将两条 npm 命令替换为 `npm.cmd install` 和 `npm.cmd run dev`。

打开 <http://127.0.0.1:5173>，按以下路径演示：选择“一次函数：k 与 b 的意义” → 选择学生 A → 开始实训 → 输入“老师，b 越大时直线会怎样？”观察学生暴露混淆 → 输入“不对，b 不影响斜率，只改变截距位置。”完成几轮教学 → 结束实训 → 查看五维雷达图、行为统计、评价建议和实训历史。

运行测试：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
```

核心数据接口：

- `GET /api/scenarios`
- `GET /api/scenarios/{scenario_id}`
- `GET /api/virtual-students`
- `GET /api/virtual-students/{student_id}`

## 模拟教学流程

默认使用 Mock LLM，可在无 API Key、无网络时完整演示：

1. 前端选择教学场景和虚拟学生，点击“开始实训”。相同场景和学生已有进行中会话时，后端会复用该会话，避免重复创建。
2. 在模拟课堂输入教师话语。后端依次记录教师消息、分析教学行为、更新学生状态、构造 Prompt、调用 LLM、记录学生回答。
3. 刷新页面会从浏览器保存的会话 ID 恢复完整对话；结束实训后，已完成会话不能继续发送消息。

每轮教师输入还会生成结构化教学行为记录，当前支持：讲解、提问、引导式提问、举例、反馈、纠错、理解确认和直接给答案。分析采用规则统计优先、LLM 结构化增强；LLM 输出会经过 Pydantic 校验，异常时使用安全默认值并记录日志，不会中断会话。

结束实训时会自动生成教学评价。五个维度为知识准确性、提问与引导、教学反馈、错误诊断能力、支架式教学；固定权重集中配置在评价引擎中，评价报告会返回五维分数、总分、优点、问题、改进建议和关键教学片段。评价仅用于训练辅助，不替代专业教师正式评价。

实训结束页使用 ECharts 展示五维能力雷达图；同时展示教学行为统计、评价摘要和关键片段。历史列表按完成时间展示主题、虚拟学生和总分，完成两次及以上实训后显示简洁成长曲线。

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

## 启动前端

```powershell
cd frontend
npm install
npm run dev
```

如果 PowerShell 的 npm 入口被执行策略阻止，使用 `npm.cmd install` 和 `npm.cmd run dev`。

前端地址：<http://127.0.0.1:5173>
