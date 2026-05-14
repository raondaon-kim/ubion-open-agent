# macOS 빌드 가이드

> **요약**: 현재 코드는 Mac 빌드를 받아들이도록 정리되어 있지만, **실제
> dmg/app 산출물은 macOS 머신에서만 만들어집니다**. Tauri 가 크로스 플랫폼
> 크로스 컴파일을 지원하지 않기 때문입니다 (공식: [Tauri Distribution
> – macOS Application Bundle](https://v2.tauri.app/distribute/macos-application-bundle)).
> 이 문서는 macOS 빌드 머신을 새로 셋업하는 사람을 위한 체크리스트입니다.

## 0. 사전 조건

| 항목 | 필요 버전 | 비고 |
|------|----------|------|
| macOS | 11.0 이상 | `bundle.macOS.minimumSystemVersion` 와 동일 |
| Xcode CLI tools | 최신 | `xcode-select --install` |
| Rust | 1.77 이상 | `rustup default stable` |
| Node.js | 20 이상 | `pnpm` 추천 |
| Tauri CLI | 2.x | `cargo install tauri-cli --version "^2"` |

Apple Silicon + Intel 양쪽 지원이 필요하면:

```bash
rustup target add aarch64-apple-darwin x86_64-apple-darwin
```

## 1. 임베디드 Python 페이로드 준비

Windows 빌드와 같은 절차이지만 macOS 용 트리플로 받아야 합니다.
[python-build-standalone 릴리스](https://github.com/astral-sh/python-build-standalone/releases)
에서:

- Apple Silicon: `cpython-3.13.x-aarch64-apple-darwin-install_only.tar.gz`
- Intel: `cpython-3.13.x-x86_64-apple-darwin-install_only.tar.gz`
- Universal: 둘 다 받아 합쳐야 함 (수동)

압축을 풀어 `src-tauri/python/` 트리로 옮깁니다. 결과 구조:

```
src-tauri/python/
├── bin/python3
├── lib/python3.13/
│   ├── site-packages/    # 여기로 pip install
│   └── ...stdlib...
└── include/...
```

필요한 파이썬 의존성 설치 (예: anthropic, openai, fastapi, uvicorn 등):

```bash
src-tauri/python/bin/python3 -m pip install \
  -r engine/requirements.txt \
  --target src-tauri/python/lib/python3.13/site-packages
```

> ⚠️ macOS 의 python-build-standalone 은 zip 내부에 *symlink* 가 있습니다.
> Tauri 번들러가 symlink 를 자기 방식으로 재배치하므로 압축 해제 시
> `tar -xzf` 의 기본 동작에 맡기면 됩니다. Finder 로 풀면 깨질 수 있으니
> 터미널에서 푸세요.

## 2. engine/ 페이로드 + `.env.bundled` 확인

루트 `engine/` 의 스냅샷을 `src-tauri/engine/` 으로 복사:

```bash
rsync -a --delete --exclude __pycache__ --exclude '*.pyc' \
  engine/ src-tauri/engine/
```

`engine/.env.bundled` 안에 LiteLLM 키 등이 채워져 있는지 확인.
이 파일은 `.gitignore` 에 의해 저장소에 안 올라가므로, 빌드 머신에서
새로 작성해야 합니다 (Windows 빌드 머신의 카피본을 안전한 채널로
공유하는 게 일반적).

## 3. macOS 빌드

```bash
pnpm install
cd web && pnpm build && cd ..
cargo tauri build
```

기본은 호스트 아키텍처 (Apple Silicon Mac 이면 aarch64).
유니버설 바이너리가 필요하면:

```bash
cargo tauri build --target universal-apple-darwin
```

산출물:

- `src-tauri/target/release/bundle/macos/Ubion 에이전트.app` — 실행 가능 app
- `src-tauri/target/release/bundle/dmg/Ubion 에이전트_0.1.0_aarch64.dmg`

## 4. 서명 / 공증 (배포 시)

사내 분배만 한다면 서명 없이도 됩니다. 단 사용자는 첫 실행 시
"확인되지 않은 개발자" 경고를 봅니다. Right-click → Open 으로
회피 가능.

App Store 외부 배포(다운로드 링크) 의 경우 *Developer ID 인증서* 와
*Notarization* 이 필요:

1. Apple Developer Program 가입 ($99/년)
2. `security find-identity -v -p codesigning` 로 identity 확인
3. `tauri.conf.json` 의 `bundle.macOS.signingIdentity` 를 채움
4. `xcrun notarytool submit ...` 로 공증 (필요 시)

자세한 절차는 공식 가이드 참조:
- [Signing macOS apps](https://v2.tauri.app/distribute/sign/macos)
- [App Store distribution](https://v2.tauri.app/distribute/app-store)

## 5. 알려진 차이점

| 항목 | Windows | macOS |
|------|---------|-------|
| Python 인터프리터 경로 | `python/python.exe` | `python/bin/python3` |
| `PYTHONHOME` | `python/` (python.exe 의 부모) | `python/` (bin 의 부모) |
| 콘솔 창 숨김 | `CREATE_NO_WINDOW` 플래그 | 불필요 (app 번들은 LSUIElement 이거나 stdio 가 inherit 됨) |
| 작업 폴더 기본값 | `~/Documents/Ubion 에이전트` | `~/Documents/Ubion 에이전트` |
| 자동 실행 권한 | N/A | supervisor.rs 가 `chmod 755 python3` 자동 처리 |
| 설치 모드 | NSIS, 현재 사용자만 | dmg 드래그 → /Applications |

## 6. 검증 체크리스트

빌드 후 dmg 마운트 → /Applications 로 드래그 → 실행:

- [ ] 콘솔 창 안 뜸 (Activity Monitor 로 python3 자식 프로세스 확인)
- [ ] 첫 부팅에 `~/.ubion-agent/.env` 자동 시드 (LITELLM_* 포함)
- [ ] 작업 폴더 자동 생성: `~/Documents/Ubion 에이전트/`
- [ ] Debug Drawer (Ctrl+Shift+D / Cmd+Shift+D) 에 `LITELLM_API_KEY set` 표시
- [ ] 채팅 한 번 보내서 LiteLLM 프록시로 라우팅되는지 확인 (사내망 필요)
- [ ] Settings → 작업 폴더 → "📁 폴더 선택" → 다른 폴더 고름 → 저장 → 다음 채팅이 새 폴더에 파일 만드는지 확인
