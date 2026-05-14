# Research: Hermes Message Interface

## 목적

Phase 1 진입 전에 Hermes를 헤드리스로 실행하고 외부에서 메시지를 주고받을 수 있는 정확한 인터페이스를 확인한다.

## 메타

- 우선순위: High
- 조사일: 2026-05-13
- 조사자: ax 센터 + Claude (Opus 4.7)
- 조사 대상 commit: `main` HEAD (2026-05-13 shallow clone)
- 조사 위치: `d:\Self-Evolving Agent Platform\.hermes-clone\` (조사 종료 후 삭제 가능)
- 결론 상태: **🟢 1안 확정. Phase 1 진입 가능.**

---

## 🟢 결론 한 줄

**Hermes는 `API_SERVER_ENABLED=true` 환경변수만 켜면 OpenAI 호환 HTTP 서버(`POST /v1/chat/completions` 등)를 노출한다. 별도 thin wrapper를 작성할 필요가 없다.** Phase 1 dispatcher는 컨테이너 안의 `http://localhost:8642/v1`로 표준 OpenAI 클라이언트로 호출하면 된다.

---

## 1. 외부 진입점 5종 비교

조사로 확인된 외부 진입점은 5개이며, 본 프로젝트에 적합한 순으로 정리.

| # | 진입점 | 전송 방식 | 동기/스트림 | 세션 | 우리 용도 적합성 |
|---|--------|---------|-----------|------|---------------|
| **1** | **API Server (OpenAI 호환)** | **HTTP/SSE** | 동기 + 스트리밍 | 양쪽 다 지원 | **🟢 최우선** |
| 2 | ACP Server | stdio JSON-RPC | 스트리밍 | 영속 세션 | 🟡 보조 |
| 3 | `AIAgent` Python 라이브러리 import | in-process | 양쪽 | 양쪽 | 🟡 동일 컨테이너 안에서만 |
| 4 | `hermes -z` oneshot CLI | argv → stdout | 동기, 최종 텍스트만 | 없음 | 🟢 디버깅 / 검증용 |
| 5 | Webhook adapter | HTTP POST | 비동기 (fire-and-forget) | 없음 | 🔴 사용 안 함 |
| ❌ | `hermes mcp serve` | stdio MCP | — | — | 🔴 외부 메시지 주입 도구가 없음 |
| ❌ | `hermes web` dashboard | HTTP | — | — | 🔴 admin UI 전용 (chat endpoint 없음) |

---

## 2. 1안: API Server (OpenAI 호환)

### 2.1 무엇인가

`gateway/` 안에 포함된 **OpenAI Chat Completions / Responses API 호환 HTTP 서버**. 어떤 OpenAI 클라이언트도 그대로 붙는다 — Open WebUI, LobeChat, LibreChat, OpenAI Python SDK, curl 등.

### 2.2 출처

- 소스: [`.hermes-clone/gateway/platforms/api_server.py`](../.hermes-clone/gateway/platforms/api_server.py) (라인 1–60)
- 공식 문서: [`.hermes-clone/website/docs/user-guide/features/api-server.md`](../.hermes-clone/website/docs/user-guide/features/api-server.md) (전체)
- docker-compose 주석: [`.hermes-clone/docker-compose.yml`](../.hermes-clone/docker-compose.yml):36–39

### 2.3 활성화 방법

`~/.hermes/.env`에 (컨테이너 안에서는 `$HERMES_HOME/.env`):

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=<bearer token>
API_SERVER_HOST=127.0.0.1     # 기본값. 컨테이너 안에서는 0.0.0.0으로 바꿔야 dispatcher가 닿음
API_SERVER_PORT=8642          # 기본값
API_SERVER_CORS_ORIGINS=      # 브라우저 직접 호출 시에만
```

이후 `hermes gateway` 실행 → 자동으로 API 서버가 같이 뜸.

### 2.4 노출 엔드포인트

| 메서드 | 경로 | 용도 |
|-------|------|------|
| POST | `/v1/chat/completions` | OpenAI Chat 표준. **stateless** — 매 요청마다 전체 messages 배열을 보냄 |
| POST | `/v1/responses` | OpenAI Responses API. **stateful** — `previous_response_id` 또는 `conversation` 이름으로 서버측 상태 유지 |
| GET | `/v1/responses/{id}` | 저장된 응답 조회 |
| DELETE | `/v1/responses/{id}` | 저장된 응답 삭제 |
| GET | `/v1/models` | 사용 가능 모델 목록 (profile 이름이 model 이름으로 노출됨) |
| GET | `/v1/capabilities` | 기능 감지용 메타데이터 |
| POST | `/v1/runs` | 비동기 run 시작 — `run_id` 반환 |
| GET | `/v1/runs/{run_id}` | run 상태 폴링 |
| GET | `/v1/runs/{run_id}/events` | SSE로 lifecycle 이벤트 구독 |
| POST | `/v1/runs/{run_id}/stop` | run 인터럽트 |
| GET | `/health` / `/v1/health` | 헬스체크 |
| GET | `/health/detailed` | 활성 세션/리소스 사용량 포함 헬스체크 |

### 2.5 인증

`Authorization: Bearer $API_SERVER_KEY`. 키가 비어있고 `API_SERVER_HOST != 127.0.0.1`이면 startup 실패함 (소스에서 강제).

### 2.6 동작 확인 (스펙 문서에서 직접 인용)

```bash
curl http://localhost:8642/v1/chat/completions \
  -H "Authorization: Bearer change-me-local-dev" \
  -H "Content-Type: application/json" \
  -d '{"model": "hermes-agent", "messages": [{"role":"user","content":"Hello!"}]}'
```

### 2.7 세션 연속성 — 본 프로젝트 핵심

**컨테이너-per-user 모델에서 세션 연속성을 어떻게 가져갈지가 가장 중요**. 두 가지 방식이 다 지원됨.

- **Stateless (Chat Completions)** + 매 요청에 전체 history 첨부 → dispatcher 또는 web UI가 history 보관 책임. Hermes 컨테이너는 stateless하게 동작.
- **Stateful (Responses API)** + `conversation: "ubion-<user_id>-<session_id>"` 같은 named conversation → Hermes 컨테이너 안의 SQLite에 자동 chain.
- **Chat Completions + `X-Hermes-Session-Id` 헤더** — 비공식 옵션이지만 소스에 존재 (`api_server.py`:5: `opt-in session continuity via X-Hermes-Session-Id header`). 본 프로젝트에서는 `user_id`별로 1개 컨테이너이므로 굳이 안 쓰는 편이 깔끔.

**Phase 1 권장**: Responses API + named conversation을 1차로 시도. 이슈가 생기면 Chat Completions + dispatcher-side history로 fallback.

### 2.8 컨테이너 안 동작 모델 (본 프로젝트 매핑)

```
사용자 A의 컨테이너
├── HERMES_HOME=/home/agent/.hermes  ← 볼륨 마운트
├── API_SERVER_ENABLED=true
├── API_SERVER_HOST=0.0.0.0          ← dispatcher가 접근 가능하도록
├── API_SERVER_PORT=8642
├── API_SERVER_KEY=<per-user random>
└── hermes gateway 가 entrypoint
    ↑
    │ HTTP POST /v1/chat/completions
    │
[Dispatcher] —— Docker network ——> 사용자 A 컨테이너:8642
```

Dispatcher는 `user_id`로부터 `(container_name, api_key)`를 룩업해서 컨테이너 안의 API 서버로 그대로 요청 포워딩.

### 2.9 보안 메모

- 키 없이 `0.0.0.0` 바인딩은 코드 레벨에서 금지 (`api-server.md` 보안 경고 인용).
- 본 프로젝트에서는 컨테이너 네트워크를 Docker가 격리하므로 `0.0.0.0`이라도 호스트 LAN에는 안 보임 — 단, **Docker network에 dispatcher만 들어와야 한다**. 다른 사용자의 컨테이너에서 같은 네트워크면 키 알면 접근 가능 → **per-user Docker network 또는 per-user API key 필수**.

---

## 3. 2안: ACP (Agent Client Protocol) Server

### 3.1 무엇인가

Zed 에디터가 표준화한 [Agent Client Protocol](https://github.com/zed-industries/agent-client-protocol) 의 서버 구현. **stdio JSON-RPC** 기반.

### 3.2 출처

- 진입점: [`.hermes-clone/acp_adapter/entry.py`](../.hermes-clone/acp_adapter/entry.py):110–148
- 서버 본체: [`.hermes-clone/acp_adapter/server.py`](../.hermes-clone/acp_adapter/server.py) (1714 라인)
- CLI 등록: [`.hermes-clone/hermes_cli/main.py`](../.hermes-clone/.hermes-clone/hermes_cli/main.py):11414–11423 (`hermes acp` subcommand)

### 3.3 동작 방식

- `hermes acp` → 표준입출력으로 JSON-RPC. stdout = JSON-RPC, stderr = 로그.
- 핵심 메서드: `prompt(prompt, session_id, ...)` (server.py:1071–1162)
- 멀티모달 입력 지원 (text, image, audio, resource link 등)
- 영속 세션: `new_session()`, `load_session()`, `resume_session()`
- 스트리밍 콜백: `stream_delta_cb`, `tool_progress_cb`, `reasoning_cb`

### 3.4 본 프로젝트에서의 위치

- 장점: 공식 프로토콜, 멀티모달, 세션 모델이 깔끔.
- 단점: stdio 기반 → 컨테이너 1개에 dispatcher가 stdio attach 해야 함 (`docker exec -i`). 다중 동시 메시지 지원이 1안보다 까다로움.
- **판단**: 1안(HTTP)이 안 되거나 ACP가 더 안정적이라는 증거가 나오면 그때 전환. Phase 1에서는 1안 사용.

---

## 4. 3안: `AIAgent` Python 라이브러리 import

### 4.1 무엇인가

`run_agent.py:1094-15550`의 `AIAgent` 클래스를 그대로 import해서 in-process로 호출.

```python
from run_agent import AIAgent
agent = AIAgent(model="claude-opus-4-7", api_key="...", base_url="...")
response = agent.chat("프롬프트")
```

### 4.2 본 프로젝트에서의 위치

- 컨테이너 안에서 작은 Python wrapper (`entrypoint.py`)를 만들고 거기서 사용 가능.
- 하지만 1안(API server)이 이미 같은 일을 더 표준적으로 해주므로 **별도 wrapper 불필요**.
- 디버그용으로 직접 코드를 호출할 때만 의미 있음.

---

## 5. 4안: `hermes -z` oneshot CLI

### 5.1 무엇인가

```bash
hermes -z "프롬프트 한 줄"
# stdout: 최종 응답 텍스트
# exit code: 0 또는 2 (validation error)
```

### 5.2 출처

- 구현: [`.hermes-clone/hermes_cli/oneshot.py`](../.hermes-clone/hermes_cli/oneshot.py):124–199
- CLI 등록: [`.hermes-clone/hermes_cli/main.py`](../.hermes-clone/hermes_cli/main.py):9213 (플래그), 11841–11853 (디스패치)
- `run_oneshot(prompt, model, provider, toolsets) -> int`

### 5.3 특징

- 세션 없음. 매 호출이 독립.
- 스트리밍 없음. 최종 텍스트 1회만 stdout.
- `HERMES_YOLO_MODE=1`, `HERMES_ACCEPT_HOOKS=1`이 자동 설정됨 → tool 승인 프롬프트 우회.
- stderr는 devnull로 묻힘.

### 5.4 본 프로젝트에서의 위치

- **Phase 0 검증용으로 가장 빠르게 끝까지 확인하기 좋다.** `docker exec -i <container> hermes -z "Hello"` 한 번으로 사용자별 격리, 비용, 응답 품질을 다 잴 수 있음.
- 프로덕션 dispatcher에서는 매 호출마다 별도 Python 프로세스가 떴다 죽음 → 비용/지연이 큼. 1안으로 가야 함.

---

## 6. 5안 (사용 안 함): Webhook Adapter

- 동작: `gateway/platforms/webhook.py`. 외부 시스템이 `POST /webhooks/{name}` 으로 임의 payload를 보내면 → 미리 등록한 prompt 템플릿이 렌더되어 → 에이전트 실행 → **응답은 별도 채널(Telegram/Slack/log)로 비동기 delivery**.
- 동기 응답이 아니라서 dispatcher 용도로 부적합.
- GitHub Webhook 같은 이벤트 트리거 자동화용.

---

## 7. ❌ 사용 불가: `hermes mcp serve`

- 동작: Hermes를 **MCP 서버로 노출** (stdio JSON-RPC). Claude Desktop/Cursor/Codex가 이걸 붙여서 Hermes의 메신저 conversation을 조작.
- 노출하는 tool 10개: `conversations_list`, `messages_send`, `events_poll` 등 — **모두 "이미 존재하는 메신저 대화를 다루는 도구"**.
- 임의의 새 프롬프트를 에이전트에 던지고 답을 받는 tool이 **없음** (`mcp_serve.py:1–897` 전수 확인).
- 본 프로젝트에는 부적합.

---

## 8. ❌ 사용 불가: `hermes web` Dashboard

- 동작: FastAPI 기반 admin UI. config, env, session 관리.
- chat endpoint **없음**. 본 프로젝트에는 부적합.

---

## 9. 컨테이너 격리 키 (`HERMES_HOME`)

본 프로젝트의 per-user 격리에 결정적인 부분.

### 9.1 정의

- 단일 진실의 원천: [`hermes_constants.py:get_hermes_home()`](../.hermes-clone/hermes_constants.py):14–68
- 동작: `os.environ["HERMES_HOME"]`이 있으면 그 경로, 없으면 `~/.hermes`.

### 9.2 공식 Docker 이미지

- [`Dockerfile`](../.hermes-clone/Dockerfile):110: `ENV HERMES_HOME=/opt/data`
- [`Dockerfile`](../.hermes-clone/Dockerfile):112: `VOLUME [ "/opt/data" ]`
- [`docker-compose.yml`](../.hermes-clone/docker-compose.yml):32: `~/.hermes:/opt/data` 마운트
- 권장: 본 프로젝트는 컨테이너 안에서 `HERMES_HOME=/home/agent/.hermes`로 두고, 호스트의 `/var/lib/ubion-agents/<user_id>/`를 거기 마운트.

### 9.3 프로파일 시스템

- Hermes 자체에 `~/.hermes/profiles/<name>/` 구조가 있음 (`api-server.md` 392–425 인용).
- `hermes profile create alice` → 격리된 config/memory/skills.
- **본 프로젝트에서는 굳이 profile 안 씀.** 컨테이너 자체가 더 강한 격리 + 프로파일은 Hermes 한 인스턴스 안에서의 격리 개념이라 우리 모델과 중복.

---

## 10. Phase 1에서 dispatcher가 사용할 정확한 인터페이스

### 10.1 컨테이너 내부 설정

`~/.hermes/.env` (호스트의 `/var/lib/ubion-agents/<user_id>/.env`):

```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=<per-user random 32 chars>
HERMES_HOME=/home/agent/.hermes
```

### 10.2 컨테이너 entrypoint

공식 이미지를 그대로 사용 + command 오버라이드:

```yaml
# docker-compose-per-user.yml.tmpl (예시)
services:
  agent-${USER_ID}:
    image: hermes-agent:pinned-${VERSION}
    container_name: agent-${USER_ID}
    volumes:
      - /var/lib/ubion-agents/${USER_ID}:/home/agent/.hermes
    environment:
      - HERMES_HOME=/home/agent/.hermes
      - API_SERVER_ENABLED=true
      - API_SERVER_HOST=0.0.0.0
      - API_SERVER_KEY_FILE=/run/secrets/api-key
    networks:
      - dispatcher-net  # dispatcher만 들어오는 격리망
    command: ["gateway", "run"]
```

### 10.3 Dispatcher 호출

Phase 1 dispatcher(언어 미정)는 OpenAI 호환 클라이언트 라이브러리(예: `openai-node`, `openai` Python SDK)를 그대로 사용:

```js
import OpenAI from "openai";

async function forward(userId, sessionId, messages) {
  const { containerHost, apiKey } = await lookupUser(userId);
  const client = new OpenAI({
    baseURL: `http://${containerHost}:8642/v1`,
    apiKey,
  });
  const stream = await client.chat.completions.create({
    model: "hermes-agent",
    messages,
    stream: true,
  });
  for await (const chunk of stream) {
    yield chunk.choices[0]?.delta?.content ?? "";
  }
}
```

### 10.4 Cold start 처리

- 컨테이너가 `stopped` → dispatcher가 `docker start <container>` → API server가 listen 시작할 때까지 health check 폴링 (`GET /health`).
- Hermes gateway 부팅 시간: 미측정. Phase 0에서 실측 필요.

---

## 11. 조사 과정에서 확인한 추가 사실

| 항목 | 내용 |
|---|---|
| Hermes 라이선스 | MIT |
| 주 언어 | Python 87.9%, TypeScript 8.9% |
| 의존성 | aiohttp (API server), fastapi+uvicorn (dashboard만, lazy install) |
| 공식 Docker | 있음. `network_mode: host` 사용. 본 프로젝트는 격리 위해 bridge network로 변경 필요 |
| Docker 사용자 | UID 10000 hermes (HERMES_UID 환경변수로 오버라이드) |
| 멀티 인스턴스 안전성 | 같은 머신에 여러 컨테이너 동시 실행은 docker-compose dashboard+gateway가 이미 시연. `HERMES_HOME`만 다르면 안전 (조사 5.3에서 별도 확인 권장) |
| 비용 통제 | API_SERVER 자체에는 cost cap 없음. 모델 선택과 monthly limit은 별도 구현 필요 |

---

## 12. Phase 1 진입 전 남은 검증 (필수)

1. [ ] **Cold-start latency 측정** — `docker start` → `/health 200 OK`까지 시간. 목표 < 10s.
2. [ ] **격리 검증** — 2명의 컨테이너 동시 운영, 한쪽 memory가 다른 쪽에 누수 안 되는지 (Phase 0 task).
3. [ ] **API server + 자기진화 루프 상호작용** — `/v1/chat/completions` 경로로 들어온 메시지에서도 skill 자동 생성, memory curation이 동작하는지 (Phase 0 사용 로그에서 확인).
4. [ ] **per-user API key 회전** — 침해 시 키 회전 절차.
5. [ ] **컨테이너 외부에서 토큰 사용량 조회** — `/health/detailed`가 충분한지, 별도 cost endpoint가 있는지 추가 조사 (현 단계에선 미확인).

---

## 13. 결정 매트릭스 영향

PROJECT_SPEC.md 섹션 7 (기술 결정 매트릭스)에 다음 항목 갱신 제안:

| 결정 항목 | 기존 | 갱신안 |
|---|---|---|
| Hermes 외부 진입점 | TBD | **API Server (OpenAI 호환, HTTP)** ✅ 확정 |
| thin wrapper 작성 부담 | 1~2일 예상 | **불필요. 0일** ✅ 해소 |
| dispatcher ↔ container 프로토콜 | TBD | **OpenAI Chat Completions + Responses API** ✅ 확정 |

R1 리스크 (Hermes 외부 진입점 부재로 wrapper 작성 부담) → **🟢 해소**.

---

## 14. 후속 조사 항목

- **5.2 학습 루프 메커니즘** — API 경로로 들어온 메시지가 skill/memory 진화 루프와 같은 LLM 비용을 발생시키는지.
- **5.3 멀티 인스턴스 안전성** — 같은 호스트에 컨테이너 5+ 동시 실행 시 충돌. `HERMES_HOME`을 다르게 잡았을 때 OS 레벨 자원 충돌은 없는지.
- **컨테이너 build pinning** — 어느 Hermes commit으로 lock 할지. 현재 `main` HEAD = 2026-05-13 기준이지만, 안정 release tag로 고정 권장.

---

## 15. 부록: 진입점 한눈 비교 (소스 인용)

| 진입점 | 소스 파일 | 핵심 라인 |
|--------|----------|---------|
| API Server | `gateway/platforms/api_server.py` | 1–60 (헤더 docstring) |
| API Server 문서 | `website/docs/user-guide/features/api-server.md` | 전체 |
| ACP entry | `acp_adapter/entry.py` | 110–148 |
| ACP server | `acp_adapter/server.py` | 1071–1162 (`prompt` method) |
| oneshot CLI | `hermes_cli/oneshot.py` | 124–199 |
| oneshot CLI 등록 | `hermes_cli/main.py` | 9213, 11841–11853 |
| webhook adapter | `gateway/platforms/webhook.py` + `hermes_cli/webhook.py` | — |
| MCP server (부적합) | `mcp_serve.py` | 1–897 (전수 확인) |
| web dashboard (부적합) | `hermes_cli/web_server.py` | — |
| HERMES_HOME 정의 | `hermes_constants.py` | 14–68 |
| Docker entrypoint | `Dockerfile` | 109–113 |
| Docker compose | `docker-compose.yml` | 24–71 |

---

*조사 종료. 이 결과는 PROJECT_SPEC.md 섹션 5.1의 🔴 HIGH 우선순위 항목을 Green 상태로 전환시킨다.*
