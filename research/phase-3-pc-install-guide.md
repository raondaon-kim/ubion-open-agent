# Phase 3 P3-1 — PC 설치 가이드

작성일: 2026-05-14
범위: 사용자 PC 에 `.exe` 한 번 설치하면 도는 standalone 상태

---

## 한 장 요약

```
+----------------------------------------+
| 사용자 동작                              |
+----------------------------------------+
| 1. Ubion 에이전트_0.1.0_x64-setup.exe   |
|    더블클릭                              |
| 2. NSIS 가 설치 경로 묻는다 (default     |
|    %LOCALAPPDATA%\Ubion 에이전트)       |
|    → 사용자가 D:\Tools\Ubion 등         |
|      임의로 바꿔도 OK                    |
| 3. "다음" 누르면 설치 완료 (1-2초)        |
| 4. 시작 메뉴/바탕화면의 "Ubion 에이전트"  |
|    실행                                  |
| 5. (최초 1회만) %LOCALAPPDATA%\         |
|    .ubion-agent\.env 에 키 입력         |
|       DEEPSEEK_API_KEY=sk-...           |
|    트레이 메뉴 → 종료 후 재실행          |
| 6. 끝. 대화 시작                          |
+----------------------------------------+
```

## 설치 산출물 (`.exe` = 24.85 MB)

LZMA 압축된 페이로드 안에:

```
<install_dir>/
  ubion-agent.exe              # Tauri 외피 (11 MB)
  resources/
    python/                    # python-build-standalone 3.13 (94 MB)
      python.exe
      Lib/site-packages/       # anthropic, openai, fastapi, ...
      DLLs/
      ...
    engine/                    # 우리 Python 엔진 (1 MB)
  uninstall.exe
```

설치 후 **디스크 사용 ≈ 106 MB**, RAM 활성 시 **~95 MB** (Tauri 24 + Python 71).

## API 키 / 데이터 격리

| 항목                  | 위치                                  | 비고                                  |
|---------------------|-------------------------------------|--------------------------------------|
| API 키 (.env)         | `%LOCALAPPDATA%\.ubion-agent\.env` | 사용자가 직접 작성. 설치 경로 무관      |
| 대화 기록 (.md)        | `%LOCALAPPDATA%\.ubion-agent\conversations\` | 자동 저장                            |
| 스킬 (`SKILL.md`)     | `%LOCALAPPDATA%\.ubion-agent\skills\` | 명시적 install 시에만 (Hermes 식 분리) |
| SOUL.md / USER.md     | `%LOCALAPPDATA%\.ubion-agent\`     | 에이전트 페르소나 + 사용자 메모리      |
| 로그                  | (현재 stdout, P3-2 에서 파일로 분기 예정)  |                                      |

→ **다른 PC 로 옮길 때**: `.ubion-agent` 폴더만 복사. 설치 파일 .exe 는 재설치하면 됨.

## 자동 동작

- **시작**: `ubion-agent.exe` 실행 → 트레이 아이콘 + webview 1100×760 + Python 백엔드 자유 포트 spawn
- **자유 포트**: `engine.server` 가 0포트 bind → 실제 번호를 stdout 첫 줄 `PORT:<n>` 로 알림. Tauri 외피가 webview 의 base URL 을 거기로 설정
- **30 분 idle 시**: Python 백엔드 self-terminate → RAM 70 MB 회수. 다음 사용자 메시지 도착 시 (≈ 2-3 초 후) 자동 respawn
- **창 X 버튼**: 트레이로 숨김. 진짜 종료는 트레이 메뉴의 "종료"
- **자동 업데이트** (Phase 3 P3-2 후): 시작 시 endpoint 폴링 → 새 버전 있으면 사용자 동의 후 passive install + 자동 재시작

## 알려진 사전 조건

- Windows 10 1809 이상 (WebView2 자동 다운로드)
- 인터넷 (LLM API 호출용; 코디네이터 통신은 P3-2 부터)
- `.env` 의 API 키 (최초 1회만 사용자가 입력)

## 제거

NSIS `currentUser` 모드 → 관리자 권한 불필요. 설정 → 앱 및 기능 → "Ubion 에이전트" 제거.
`.ubion-agent` 폴더는 *남는다* (사용자 데이터 보호). 완전 제거하려면 `%LOCALAPPDATA%\.ubion-agent` 도 직접 삭제.

## P3-2 (코디네이터) 이후 변화

- API 키 = 사내 서버에서 단기 토큰으로 갱신 (사용자가 직접 .env 안 만져도 됨)
- 자동 업데이트 endpoint 활성화
- 모바일 PWA → 코디네이터 → PC 트레이 앱 메시지 중계

이번 P3-1 까지는 **standalone** — 사내 인프라 없이도 1인 단위로 완전 동작.
