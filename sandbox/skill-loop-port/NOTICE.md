# Third-Party Attribution

This directory contains code adapted from the following projects.

---

## Hermes Agent

- **Source**: https://github.com/NousResearch/hermes-agent
- **License**: MIT
- **Copyright**: Copyright (c) 2025 Nous Research
- **Reference commit**: `b06e9993021a8eebd891fc60d52372446315b2f0` (2026-05-12)
- **Clone date**: 2026-05-13

### Files adapted from this source

차용 강도는 [`../../research/hermes-license-policy.md`](../../research/hermes-license-policy.md) §2 정의를 따른다.

| 우리 파일 | 차용 강도 | 원본 (commit `b06e999`) | 비고 |
|----------|---------|--------------------|------|
| `agent_home.py` | Port | `hermes_constants.py` | `get_hermes_home`만 차용. `UBION_AGENT_HOME` env로 재명명 |
| `skill_usage.py` | Vendor copy | `tools/skill_usage.py` | 0줄 수정. MIT 헤더만 prepend |
| `curator.py` | Vendor copy | `agent/curator.py` | 0줄 수정. MIT 헤더만 prepend |

### 새로 작성한 파일 (Hermes 무관, Copyright 2026 Ubion ax center)

| 파일 | 역할 |
|------|------|
| `hermes_constants.py` | shim — `agent_home.get_hermes_home`을 재export하여 vendored 코드의 import 경로 유지 |
| `tools/__init__.py` | shim — `from tools import skill_usage`를 top-level `skill_usage`로 라우팅 |
| `run_agent.py` | shim — `mock_agent.AIAgent`을 재export하여 curator의 lazy import 만족 |
| `mock_agent.py` | curator가 fork하는 `AIAgent`의 최소 mock. Anthropic API 직접 호출 |
| `run_demo.py` | end-to-end 실행 스크립트 |
| `fixtures/skills/*/SKILL.md` | 5개 시범용 agent-created skill |
| `fixtures/skills/.usage.json` | provenance 데이터 (created_by=agent) |

### 우리가 차용하지 않은 부분 (참고)

- `run_agent.py`의 `AIAgent` — Mock으로 대체 ([skill-loop-port-feasibility.md §2.2](../../research/skill-loop-port-feasibility.md) 옵션 α)
- Hermes의 나머지 모듈 — 본 시범 범위 외

### MIT License (verbatim from upstream)

```
MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 본 디렉터리 자체의 라이선스

본 디렉터리에 새로 작성된 코드 (`mock_agent.py`, `run_demo.py`, fixtures 등)는:

```
Copyright (c) 2026 Ubion ax center
```

배포 시점에는 별도 결정. Phase 0 단계에서는 사내 사용 전용이므로 외부 배포 의무 없음.
