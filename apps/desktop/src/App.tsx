import { useEffect, useState } from "react";
import type { DashboardConfig, SkillManifest } from "./api/client";
import { fetchDashboardConfig, fetchSkills, saveDashboardConfig } from "./api/client";
import { ALL_WIDGET_IDS, WIDGET_REGISTRY } from "./widgets/registry";
import type { WidgetId } from "./widgets/registry";
import { useEventToasts } from "./notifications/useEventToasts";
import { ToastContainer } from "./notifications/ToastContainer";
import { BriefPanel } from "./components/BriefPanel";
import { CapabilitiesPanel } from "./components/CapabilitiesPanel";

function CustomizePanel({
  config,
  onSave,
  onCancel,
}: {
  config: DashboardConfig;
  onSave: (config: DashboardConfig) => void;
  onCancel: () => void;
}) {
  const [order, setOrder] = useState<WidgetId[]>(() => {
    const savedOrder = (config.widget_order as WidgetId[]).filter((id) => id in WIDGET_REGISTRY);
    const missing = ALL_WIDGET_IDS.filter((id) => !savedOrder.includes(id));
    return [...savedOrder, ...missing];
  });
  const [hidden, setHidden] = useState<Set<WidgetId>>(() => {
    const savedOrder = (config.widget_order as WidgetId[]).filter((id) => id in WIDGET_REGISTRY);
    const missing = ALL_WIDGET_IDS.filter((id) => !savedOrder.includes(id));
    const fullOrder = new Set([...savedOrder, ...missing]);
    return new Set(
      (config.hidden_widgets as WidgetId[]).filter((id) => id in WIDGET_REGISTRY && fullOrder.has(id))
    );
  });
  const [error, setError] = useState<string | null>(null);

  const toggleHidden = (id: WidgetId) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const move = (id: WidgetId, direction: -1 | 1) => {
    setOrder((prev) => {
      const index = prev.indexOf(id);
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });
  };

  const handleSave = async () => {
    setError(null);
    try {
      const saved = await saveDashboardConfig({ widget_order: order, hidden_widgets: [...hidden] });
      onSave(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div
      data-testid="customize-panel"
      className="animate-rise rounded-card border border-edge-soft bg-surface px-5 py-4"
    >
      <h2 className="mb-2 text-sm font-semibold">Customize dashboard</h2>
      <div className="space-y-1">
        {order.map((id, index) => (
          <div key={id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              aria-label={WIDGET_REGISTRY[id].label}
              checked={!hidden.has(id)}
              onChange={() => toggleHidden(id)}
              className="accent-(--color-primary)"
            />
            <span className="flex-1">{WIDGET_REGISTRY[id].label}</span>
            <button
              onClick={() => move(id, -1)}
              disabled={index === 0}
              aria-label={`Move ${WIDGET_REGISTRY[id].label} up`}
              className="rounded px-2 py-0.5 text-ink-mute transition-colors duration-150 hover:text-ink disabled:opacity-30"
            >
              ↑
            </button>
            <button
              onClick={() => move(id, 1)}
              disabled={index === order.length - 1}
              aria-label={`Move ${WIDGET_REGISTRY[id].label} down`}
              className="rounded px-2 py-0.5 text-ink-mute transition-colors duration-150 hover:text-ink disabled:opacity-30"
            >
              ↓
            </button>
          </div>
        ))}
      </div>
      {error && (
        <p data-testid="customize-error" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <button
          onClick={handleSave}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-ink transition-colors duration-150 hover:opacity-90"
        >
          Save
        </button>
        <button
          onClick={onCancel}
          className="rounded-md border border-edge px-3 py-1.5 text-sm transition-colors duration-150 hover:border-primary"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function App() {
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customizing, setCustomizing] = useState(false);
  const [showCapabilities, setShowCapabilities] = useState(false);
  const [skills, setSkills] = useState<SkillManifest[]>([]);
  const [online, setOnline] = useState<boolean | null>(null);
  const toasts = useEventToasts();

  useEffect(() => {
    fetchDashboardConfig()
      .then(setConfig)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
    fetchSkills()
      .then((loaded) => {
        setSkills(loaded);
        setOnline(true);
      })
      .catch(() => setOnline(false));
  }, []);

  const visibleOrderedWidgets: WidgetId[] = config
    ? (config.widget_order as WidgetId[])
        .filter((id) => id in WIDGET_REGISTRY)
        .filter((id) => !config.hidden_widgets.includes(id))
    : [];

  return (
    <main className="mx-auto max-w-5xl px-6 py-6">
      <ToastContainer toasts={toasts} />
      <header className="mb-5 flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Jarvis</h1>
          <span
            data-testid="backend-status"
            className="flex items-center gap-1.5 font-mono text-xs text-ink-faint"
          >
            <span
              aria-hidden="true"
              className={
                online === null
                  ? "h-1.5 w-1.5 rounded-full bg-ink-faint"
                  : online
                    ? "h-1.5 w-1.5 animate-pulse-dot rounded-full bg-ok"
                    : "h-1.5 w-1.5 rounded-full bg-danger"
              }
            />
            {online === null ? "connecting" : online ? "online" : "backend offline"}
          </span>
        </div>
        <nav className="flex items-center gap-2">
          <button
            onClick={() => setShowCapabilities((prev) => !prev)}
            className="rounded-md border border-edge px-3 py-1.5 text-sm transition-colors duration-150 hover:border-primary"
          >
            What can Jarvis do?
          </button>
          <button
            onClick={() => setCustomizing((prev) => !prev)}
            className="rounded-md border border-edge px-3 py-1.5 text-sm text-ink-mute transition-colors duration-150 hover:border-primary hover:text-ink"
          >
            Customize
          </button>
        </nav>
      </header>
      {error && (
        <p data-testid="app-error" className="mb-4 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-col gap-4">
        {showCapabilities && (
          <CapabilitiesPanel skills={skills} onClose={() => setShowCapabilities(false)} />
        )}
        {customizing && config && (
          <CustomizePanel
            config={config}
            onSave={(saved) => {
              setConfig(saved);
              setCustomizing(false);
            }}
            onCancel={() => setCustomizing(false)}
          />
        )}
        <BriefPanel />
        <div className="grid gap-4 md:grid-cols-2">
          {visibleOrderedWidgets.map((id) => {
            const Widget = WIDGET_REGISTRY[id].component;
            const fullWidth = id === "skills" || id === "notes";
            return (
              <div key={id} className={fullWidth ? "md:col-span-2" : ""}>
                <Widget />
              </div>
            );
          })}
        </div>
      </div>
    </main>
  );
}

export default App;
