import type { Toast } from "./useEventToasts";

export function ToastContainer({ toasts }: { toasts: Toast[] }) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          data-testid="toast"
          className="flex animate-rise items-center gap-2.5 rounded-md border border-edge bg-surface-2 px-4 py-2.5 text-sm shadow-lg"
        >
          <span
            aria-hidden="true"
            className={
              toast.kind === "success"
                ? "h-2 w-2 shrink-0 rounded-full bg-ok"
                : "h-2 w-2 shrink-0 rounded-full bg-danger"
            }
          />
          {toast.message}
        </div>
      ))}
    </div>
  );
}
