import { useCallback, useEffect, useState } from "react";
import { fetchServerWorkspace, fsList, type FsEntry } from "../api/client";

interface Props {
  open: boolean;
  initialPath?: string;
  onClose: () => void;
  onPick: (path: string) => void;
}

/**
 * 서버 측 폴더 트리를 탐색해 워크스페이스 폴더를 고른다.
 * 브라우저가 임의 절대경로를 직접 알 수 없기 때문에 백엔드의
 * /v1/ubion/fs/list 를 거쳐 디렉터리를 한 단계씩 내려간다.
 */
export function FolderPicker({ open, initialPath, onClose, onPick }: Props) {
  const [current, setCurrent] = useState<string>("");
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [roots, setRoots] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const navigate = useCallback(async (target?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fsList(target);
      setCurrent(res.path);
      setParent(res.parent);
      setEntries(res.entries);
      setRoots(res.roots);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // 다이얼로그가 열릴 때 한 번만 초기 경로 결정.
  // 우선순위: 호출자 지정 initialPath → 서버의 UBION_WORKSPACE → 홈.
  useEffect(() => {
    if (!open) return;
    (async () => {
      let start = initialPath ?? "";
      if (!start) {
        try {
          start = await fetchServerWorkspace();
        } catch {
          start = "";
        }
      }
      await navigate(start || undefined);
    })();
  }, [open, initialPath, navigate]);

  if (!open) return null;

  const onlyDirs = entries.filter((e) => e.is_dir);
  const files = entries.filter((e) => !e.is_dir);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.45)" }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl rounded-lg shadow-xl flex flex-col"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-border)",
          maxHeight: "min(80vh, 640px)",
        }}
      >
        {/* 헤더 */}
        <div
          className="px-4 py-3 flex items-center justify-between"
          style={{ borderBottom: "1px solid var(--color-border)" }}
        >
          <h3 className="text-base font-medium">작업 폴더 선택</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-sm px-2 py-1 rounded hover:opacity-70"
            style={{ color: "var(--color-text-muted)" }}
          >
            ✕
          </button>
        </div>

        {/* 현재 경로 + 상위 폴더 */}
        <div
          className="px-4 py-2 flex items-center gap-2 text-sm"
          style={{ borderBottom: "1px solid var(--color-border)" }}
        >
          <button
            type="button"
            disabled={!parent || loading}
            onClick={() => parent && navigate(parent)}
            className="px-2 py-1 rounded border text-xs disabled:opacity-40"
            style={{
              borderColor: "var(--color-border)",
              color: "var(--color-text-muted)",
            }}
          >
            ↑ 상위
          </button>
          <code
            className="flex-1 truncate text-xs px-2 py-1 rounded"
            style={{
              background: "var(--color-surface)",
              color: "var(--color-text)",
            }}
            title={current}
          >
            {current || "..."}
          </code>
        </div>

        {/* 드라이브 루트 (Windows) */}
        {roots.length > 0 && (
          <div
            className="px-4 py-2 flex flex-wrap gap-1.5"
            style={{ borderBottom: "1px solid var(--color-border)" }}
          >
            <span
              className="text-xs self-center mr-1"
              style={{ color: "var(--color-text-dim)" }}
            >
              드라이브:
            </span>
            {roots.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => navigate(r)}
                className="px-2 py-0.5 rounded border text-xs"
                style={{
                  borderColor: "var(--color-border)",
                  color: "var(--color-text-muted)",
                }}
              >
                {r}
              </button>
            ))}
          </div>
        )}

        {/* 목록 */}
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {loading && (
            <p
              className="text-xs px-3 py-2"
              style={{ color: "var(--color-text-dim)" }}
            >
              불러오는 중…
            </p>
          )}
          {error && (
            <p
              className="text-xs px-3 py-2"
              style={{ color: "var(--color-danger)" }}
            >
              {error}
            </p>
          )}
          {!loading && !error && onlyDirs.length === 0 && files.length === 0 && (
            <p
              className="text-xs px-3 py-2"
              style={{ color: "var(--color-text-dim)" }}
            >
              비어 있는 폴더입니다.
            </p>
          )}

          {onlyDirs.map((e) => (
            <button
              key={e.path}
              type="button"
              onDoubleClick={() => navigate(e.path)}
              onClick={() => navigate(e.path)}
              className="w-full text-left px-3 py-1.5 rounded text-sm flex items-center gap-2 hover:opacity-90"
              style={{ color: "var(--color-text)" }}
            >
              <span style={{ color: "var(--color-accent)" }}>📁</span>
              <span className="truncate">{e.name}</span>
            </button>
          ))}
          {files.map((e) => (
            <div
              key={e.path}
              className="px-3 py-1 text-sm flex items-center gap-2 opacity-50"
              style={{ color: "var(--color-text-muted)" }}
            >
              <span>📄</span>
              <span className="truncate">{e.name}</span>
            </div>
          ))}
        </div>

        {/* 액션 */}
        <div
          className="px-4 py-3 flex items-center justify-end gap-2"
          style={{ borderTop: "1px solid var(--color-border)" }}
        >
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded text-sm"
            style={{ color: "var(--color-text-muted)" }}
          >
            취소
          </button>
          <button
            type="button"
            disabled={!current}
            onClick={() => {
              if (current) {
                onPick(current);
                onClose();
              }
            }}
            className="px-4 py-1.5 rounded text-sm font-medium disabled:opacity-40"
            style={{ background: "var(--color-accent)", color: "white" }}
          >
            이 폴더 선택
          </button>
        </div>
      </div>
    </div>
  );
}
