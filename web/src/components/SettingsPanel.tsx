import { useEffect, useState } from "react";
import { useTheme } from "../hooks/useTheme";
import {
  fetchHealth,
  fetchServerWorkspace,
  getApiBaseOverride,
  getBearerToken,
  setApiBase,
  setBearerToken,
} from "../api/client";
import { FolderPicker } from "./FolderPicker";

export function SettingsPanel() {
  const { theme, setTheme } = useTheme();
  const [token, setToken] = useState(getBearerToken());
  const [base, setBase] = useState(getApiBaseOverride());
  const [workspace, setWorkspace] = useState(
    localStorage.getItem("ubion.workspace") ?? "",
  );
  const [health, setHealth] = useState<"unknown" | "ok" | "down">("unknown");
  const [saved, setSaved] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [serverWorkspace, setServerWorkspace] = useState<string>("");

  useEffect(() => {
    fetchHealth()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("down"));
  }, [base, token]);

  // 서버가 인식 중인 UBION_WORKSPACE 를 한 번 끌어와 표시.
  // 사용자가 한 번도 picker 를 쓰지 않은 상태라면 이게 효과값.
  useEffect(() => {
    fetchServerWorkspace()
      .then(setServerWorkspace)
      .catch(() => setServerWorkspace(""));
  }, [base, token]);

  function handleSave() {
    setBearerToken(token);
    setApiBase(base);
    localStorage.setItem("ubion.workspace", workspace);
    setSaved(true);
    setTimeout(() => setSaved(false), 1600);
  }

    return (
    <div className="flex-1 overflow-y-auto pl-14 pr-3 sm:pl-6 sm:pr-6 py-6">
      <div className="max-w-2xl mx-auto">
        <header className="mb-6">
          <h2 className="text-2xl font-medium tracking-tight">설정</h2>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--color-text-muted)" }}
          >
            연결 정보와 외관을 조정합니다. 모든 값은 브라우저에만 저장됩니다.
          </p>
        </header>

        {/* 테마 */}
        <Section title="외관">
          <Row label="테마">
            <div className="flex gap-2">
              {(["light", "dark"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTheme(t)}
                  className="px-3 py-1.5 text-sm rounded-md border"
                  style={{
                    background:
                      theme === t
                        ? "var(--color-accent-bg)"
                        : "transparent",
                    borderColor:
                      theme === t
                        ? "var(--color-accent)"
                        : "var(--color-border)",
                    color:
                      theme === t
                        ? "var(--color-accent)"
                        : "var(--color-text-muted)",
                  }}
                >
                  {t === "light" ? "라이트" : "다크"}
                </button>
              ))}
            </div>
          </Row>
        </Section>

        {/* 연결 */}
        <Section title="서버 연결">
          <Row label="API base URL">
            <input
              type="text"
              value={base}
              onChange={(e) => setBase(e.target.value)}
              placeholder="(비워두면 같은 origin)"
              className="w-full rounded-md border px-3 py-1.5 text-sm bg-transparent outline-none"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            />
          </Row>
          <Row label="Bearer 토큰">
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="UBION_API_TOKEN 이 설정된 경우 입력"
              className="w-full rounded-md border px-3 py-1.5 text-sm bg-transparent outline-none"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            />
          </Row>
          <Row label="상태">
            <span
              className="inline-flex items-center gap-2 text-sm"
              style={{
                color:
                  health === "ok"
                    ? "var(--color-success)"
                    : health === "down"
                    ? "var(--color-danger)"
                    : "var(--color-text-muted)",
              }}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{
                  background:
                    health === "ok"
                      ? "var(--color-success)"
                      : health === "down"
                      ? "var(--color-danger)"
                      : "var(--color-text-dim)",
                }}
              />
              {health === "ok"
                ? "서버 정상"
                : health === "down"
                ? "서버 응답 없음"
                : "확인 중..."}
            </span>
          </Row>
        </Section>

        {/* 작업 폴더 */}
        <Section title="작업 폴더">
          <Row label="UBION_WORKSPACE">
            <div className="flex items-center gap-2">
              <code
                className="flex-1 truncate text-xs px-3 py-1.5 rounded border"
                style={{
                  background: "var(--color-surface)",
                  borderColor: "var(--color-border)",
                  color: workspace
                    ? "var(--color-text)"
                    : "var(--color-text-dim)",
                }}
                title={workspace || serverWorkspace}
              >
                {workspace || serverWorkspace || "선택된 폴더 없음"}
              </code>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="px-3 py-1.5 rounded-md border text-sm whitespace-nowrap"
                style={{
                  borderColor: "var(--color-border)",
                  color: "var(--color-text-muted)",
                }}
              >
                📁 폴더 선택
              </button>
              {workspace && (
                <button
                  type="button"
                  onClick={() => setWorkspace("")}
                  className="px-2 py-1.5 rounded-md text-xs"
                  style={{ color: "var(--color-text-dim)" }}
                  title="UI 선택 초기화"
                >
                  ✕
                </button>
              )}
            </div>
          </Row>
          <p
            className="text-xs"
            style={{ color: "var(--color-text-dim)" }}
          >
            서버 프로세스의 <code>UBION_WORKSPACE</code> 환경변수가 우선합니다.
            UI 에서 고른 값은 표시용이며 다음 대화 컨텍스트에 반영됩니다.
            {serverWorkspace && (
              <>
                {" "}현재 서버 인식 폴더: <code>{serverWorkspace}</code>
              </>
            )}
          </p>
        </Section>

        <FolderPicker
          open={pickerOpen}
          initialPath={workspace || serverWorkspace}
          onClose={() => setPickerOpen(false)}
          onPick={(p) => setWorkspace(p)}
        />

        {/* API 키 (참고용) */}
        <Section title="LLM API 키">
          <p
            className="text-sm"
            style={{ color: "var(--color-text-muted)" }}
          >
            API 키는 사용자별 에이전트 홈의 <code>.env</code> 에 저장하세요:
          </p>
          <pre
            className="text-xs mt-2 px-3 py-2 rounded-md font-mono whitespace-pre-wrap"
            style={{ background: "var(--color-bg-card)", color: "var(--color-text-muted)" }}
          >
{`# %LOCALAPPDATA%\\.ubion-agent\\.env  (Windows)
# ~/.ubion-agent/.env                  (macOS/Linux)
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...`}
          </pre>
          <p
            className="text-xs mt-2"
            style={{ color: "var(--color-text-dim)" }}
          >
            저장 후 트레이 메뉴에서 한 번 종료/재실행하면 반영됩니다.
            개발 모드 (cargo tauri dev) 에서는 프로젝트 루트 <code>.env</code> 도
            인식합니다.
          </p>
        </Section>

        <div className="flex items-center justify-end gap-3 mt-6">
          {saved && (
            <span
              className="text-xs"
              style={{ color: "var(--color-success)" }}
            >
              저장됨
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-1.5 rounded-md text-sm font-medium"
            style={{
              background: "var(--color-accent)",
              color: "white",
            }}
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <h3
        className="text-sm font-medium mb-3"
        style={{ color: "var(--color-text-muted)" }}
      >
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div
        className="text-xs mb-1"
        style={{ color: "var(--color-text-muted)" }}
      >
        {label}
      </div>
      {children}
    </label>
  );
}
