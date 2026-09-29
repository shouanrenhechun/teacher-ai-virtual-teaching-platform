# Real Renderer Smoke

本报告不保存 API Key、Authorization header、完整 system prompt 或供应商敏感 metadata。

- status: skipped
- reason: REAL_LLM_SMOKE_SKIPPED_NO_KEY
- provider: real
- model: gpt-4o-mini
- endpoint host: api.openai.com
- temperature: 0.7
- max tokens: 180

## Call summary

- Phase A: 0 / 21
- Phase B: 0 / 24
- API calls: 0
- successful calls: 0
- retries: 0
- fallbacks: 0
- validator rejects: 0

## Review status

Mock vs Real 的 1～5 人工评分需要在真实转录生成后由评审者填写；脚本不伪造主观评分。
核心认知状态由原有 Engine 负责，本脚本只传递预设状态给 Renderer，不修改状态。
