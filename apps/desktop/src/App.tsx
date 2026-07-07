import { useEffect, useState } from "react";
import type { DashboardConfig } from "./api/client";
import { fetchDashboardConfig, saveDashboardConfig } from "./api/client";
import { ALL_WIDGET_IDS, WIDGET_REGISTRY } from "./widgets/registry";
import type { WidgetId } from "./widgets/registry";
import { useEventToasts } from "./notifications/useEventToasts";
import { ToastContainer } from "./notifications/ToastContainer";

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
    <div data-testid="customize-panel" className="rounded-lg border border-gray-300 p-4 mb-4">
      <h2 className="text-lg font-semibold mb-2">Customize dashboard</h2>
      {order.map((id, index) => (
        <div key={id} className="flex items-center gap-2 mb-1">
          <input
            type="checkbox"
            aria-label={WIDGET_REGISTRY[id].label}
            checked={!hidden.has(id)}
            onChange={() => toggleHidden(id)}
          />
          <span>{WIDGET_REGISTRY[id].label}</span>
          <button onClick={() => move(id, -1)} disabled={index === 0} aria-label={`Move ${WIDGET_REGISTRY[id].label} up`}>
            ↑
          </button>
          <button
            onClick={() => move(id, 1)}
            disabled={index === order.length - 1}
            aria-label={`Move ${WIDGET_REGISTRY[id].label} down`}
          >
            ↓
          </button>
        </div>
      ))}
      {error && (
        <p data-testid="customize-error" className="text-sm text-red-600 mt-2">
          {error}
        </p>
      )}
      <div className="mt-2">
        <button onClick={handleSave} className="bg-blue-600 text-white rounded px-3 py-1 mr-2">
          Save
        </button>
        <button onClick={onCancel} className="rounded px-3 py-1 border border-gray-300">
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
  const toasts = useEventToasts();

  useEffect(() => {
    fetchDashboardConfig()
      .then(setConfig)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const visibleOrderedWidgets: WidgetId[] = config
    ? (config.widget_order as WidgetId[])
        .filter((id) => id in WIDGET_REGISTRY)
        .filter((id) => !config.hidden_widgets.includes(id))
    : [];

  return (
    <main className="p-6 max-w-2xl mx-auto">
      <ToastContainer toasts={toasts} />
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Jarvis OS</h1>
        <button
          onClick={() => setCustomizing((prev) => !prev)}
          className="rounded px-3 py-1 border border-gray-300"
        >
          Customize
        </button>
      </div>
      {error && (
        <p data-testid="app-error" className="text-red-600 mb-4">
          {error}
        </p>
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
      <div className="flex flex-col gap-4">
        {visibleOrderedWidgets.map((id) => {
          const Widget = WIDGET_REGISTRY[id].component;
          return <Widget key={id} />;
        })}
      </div>
    </main>
  );
}

export default App;
