import type { Toast } from "./useEventToasts";

export function ToastContainer({ toasts }: { toasts: Toast[] }) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          data-testid="toast"
          className={
            toast.kind === "success"
              ? "bg-green-600 text-white rounded px-4 py-2 shadow"
              : "bg-red-600 text-white rounded px-4 py-2 shadow"
          }
        >
          {toast.message}
        </div>
      ))}
    </div>
  );
}
