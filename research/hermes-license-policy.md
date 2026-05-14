# Research: Hermes 차용 라이선스 정책

## 목적

본 프로젝트는 Hermes Agent (NousResearch, MIT License) 코드를 적극적으로 차용한다. MIT 라이선스 조건을 정확히 준수하면서, 차용 출처를 추적 가능하게 유지하기 위한 정책을 정의한다.

## 메타

- 작성일: 2026-05-13
- 적용 범위: `sandbox/`, `engine/` 아래 차용 코드 전부
- Hermes 원본 라이선스: MIT (`.hermes-clone/LICENSE` 참조)
- Hermes copyright holder: Nous Research (2025)

---

## 1. MIT 라이선스가 요구하는 것

MIT는 매우 관대한 라이선스다. 핵심 의무는 **단 하나**:

> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

번역하면:
1. **저작권 표기** ("Copyright (c) 2025 Nous Research") 유지
2. **MIT 라이선스 전문** (PERMISSION NOTICE) 차용 코드와 함께 보존

본 프로젝트는 이 두 가지를 **파일 단위 헤더 + 저장소 단위 NOTICE.md** 두 층으로 보존한다.

---

## 2. 파일 단위 헤더 템플릿

### 2.1 Vendor copy (Hermes 코드 그대로 복사 + 점진 수정)

```python
# Copyright (c) 2025 Nous Research
# Copyright (c) 2026 Ubion ax center (modifications)
#
# Adapted from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/<COMMIT_SHA>/<ORIGINAL_PATH>
# Modifications:
#   - <한 줄 요약. 자세한 내역은 git log>
#
# This file is licensed under the MIT License. See NOTICE.md for the full
# license text and attribution.
"""
<원본 docstring 또는 우리가 추가한 docstring>
"""
```

**예시 — `engine/learning/curator.py`**:

```python
# Copyright (c) 2025 Nous Research
# Copyright (c) 2026 Ubion ax center (modifications)
#
# Adapted from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/a3f29c1/agent/curator.py
# Modifications:
#   - Removed Honcho integration (Phase 1 out of scope)
#   - Replaced HERMES_HOME with UBION_AGENT_HOME
#   - Replaced direct skills-dir scan with our SkillStore abstraction
#
# This file is licensed under the MIT License. See NOTICE.md for the full
# license text and attribution.
"""Curator — background skill maintenance orchestrator.

The curator is an auxiliary-model task that periodically reviews agent-created
skills and maintains the collection. ...
"""
```

### 2.2 Port (알고리즘 동일, 우리 스타일로 재작성)

Port는 *알고리즘과 사상*을 차용한 것이므로 MIT 의무가 적용된다고 보수적으로 본다 (저작권법상 "substantial portion"의 경계가 모호하므로 안전한 쪽으로).

```python
# Ported from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/<COMMIT_SHA>/<ORIGINAL_PATH>
# Rewritten in Ubion conventions; algorithm + behavior preserved.
#
# Copyright (c) 2025 Nous Research (original algorithm)
# Copyright (c) 2026 Ubion ax center (implementation)
#
# This file is licensed under the MIT License. See NOTICE.md for the full
# license text and attribution.
"""<우리 docstring>"""
```

### 2.3 Reference (원리만 보고 새로 작성)

Reference는 원본 코드를 보지 않고 docstring/README만 참고한 경우. 엄밀하게는 MIT 의무 없음. 하지만 *공로 인정(credit)* 차원에서 헤더에 출처는 남긴다.

```python
# Inspired by NousResearch/hermes-agent (MIT License) — original idea only,
# implementation is independent.
#
# Copyright (c) 2026 Ubion ax center
"""<우리 docstring>"""
```

### 2.4 자체 작성 (Hermes 무관)

```python
# Copyright (c) 2026 Ubion ax center
"""<docstring>"""
```

---

## 3. 저장소 단위 NOTICE 파일

각 차용 작업 디렉터리(`sandbox/skill-loop-port/`, 추후 `engine/`)에는 `NOTICE.md` 파일을 둔다.

### 3.1 `NOTICE.md` 템플릿

```markdown
# Third-Party Attribution

This directory contains code adapted from the following projects:

## Hermes Agent

- **Source**: https://github.com/NousResearch/hermes-agent
- **License**: MIT
- **Copyright**: Copyright (c) 2025 Nous Research
- **Reference commit**: <COMMIT_SHA> (cloned on 2026-05-13)
- **Files adapted from this source**:
  - `<our_path_1>` ← `<their_path_1>`
  - `<our_path_2>` ← `<their_path_2>`

### MIT License (verbatim from upstream)

\`\`\`
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
\`\`\`
```

---

## 4. 운영 규칙

### 4.1 차용 시점 기록

- **Hermes 기준 커밋 SHA**를 차용 작업 시작 시 기록 (모든 차용 파일이 같은 커밋 기준일 필요는 없지만, 가능하면 일관되게 유지)
- 본 프로젝트 차용 기준 커밋은 PROJECT_SPEC §6.1과 본 문서에 명시

### 4.2 수정 내역 기록 방식

- 헤더에는 **한 줄 요약**만
- **자세한 변경**은 git log에 맡김 (commit message로 추적)
- 헤더에 "Modifications:" 항목을 비워두지 말 것 — 최소 "Initial vendor copy" 라도 적기

### 4.3 차용 후 우리 자산 원칙

- 차용된 파일이 우리 트리에 들어오면 **우리 코드**다.
- Hermes 후속 변경을 자동 백포트하지 않는다 (PROJECT_SPEC v0.2 결정).
- 버그 수정은 우리 코드에서 직접. PR 보내고 싶으면 별도 trivial change로 separate (의무 아님, 호의).

### 4.4 부분 차용 (함수 단위)

한 파일 안에서 일부 함수만 차용한 경우:

```python
# Copyright (c) 2026 Ubion ax center
"""<our docstring>"""

# ... 우리 코드 ...

def _curator_prompt_template() -> str:
    """Adapted from NousResearch/hermes-agent agent/curator.py:_curator_prompt_template
    (MIT License). See NOTICE.md.
    """
    return """..."""
```

### 4.5 출처 URL 형식

- GitHub permalink 사용 (커밋 SHA 고정)
- 형식: `https://github.com/NousResearch/hermes-agent/blob/<SHA>/<PATH>`
- shallow clone이라 SHA가 partial일 수 있음 — 그럴 땐 다음 작업 시 full SHA로 갱신 (또는 작업 시작 시 full SHA 확보)

### 4.6 비 코드 파일 (markdown, YAML 등)

- SKILL.md 형식 등 *컨벤션*을 차용한 경우: MIT 의무 없음 (사실/형식은 저작권 대상 아님). 단, 본 프로젝트 README나 `research/`에서 "이 형식은 OpenClaw/Hermes의 SKILL.md 컨벤션을 따른다"고 출처 표기.
- Hermes의 SKILL.md *내용*을 그대로 가져온 경우: §3 NOTICE에 추가.

---

## 5. CI 강제 (Phase 1)

본 정책의 강제는 Phase 1 시작 시 다음 형태로 CI에 넣는다:

1. **헤더 누락 체크** — `engine/` 아래 .py 파일이 위 4종 헤더 중 하나를 가지고 있는지 확인하는 간단한 스크립트
2. **NOTICE.md 존재 확인** — `engine/` 디렉터리에 `NOTICE.md` 존재 확인
3. **NOTICE.md ↔ 헤더 일관성** — 헤더에 "Adapted from"/"Ported from"이 있는 파일이 NOTICE.md에도 등록되어 있는지

Phase 0 단계에서는 수동 점검으로 충분.

---

## 6. 추가 고려 사항

### 6.1 다른 third-party 코드

본 프로젝트가 Hermes 외 다른 OSS 코드를 차용할 일이 있다면 동일한 정책을 확장 적용한다 (라이선스 조건 확인 + 헤더 + NOTICE.md 추가).

### 6.2 Hermes가 차용한 third-party

Hermes 자체가 다른 라이선스 코드를 포함했을 수 있다. Hermes README/NOTICE를 확인하고, 만약 우리가 그 부분을 함께 차용한다면 추가 의무가 발생할 수 있음. **차용 작업 시 해당 파일 상단 헤더와 Hermes 저장소 NOTICE를 1차 확인**.

### 6.3 사내 배포

본 프로젝트는 *사내* 시스템이므로 외부 배포 의무는 없다 (MIT는 배포 시점에 NOTICE 동반을 요구). 단, 향후 OSS 공개나 협력사 제공 가능성을 고려해 처음부터 정책을 지킨다.

---

## 7. 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-13 | 초안 작성. PROJECT_SPEC v0.2 옵션 C 결정 직후 |
