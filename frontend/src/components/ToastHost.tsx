import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import { useSyncExternalStore } from "react";

import { getToasts, subscribeToasts, type ToastKind } from "./toast";

const ICONS: Record<ToastKind, typeof CircleCheck> = {
  success: CircleCheck,
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
};

/** 提示宿主，挂在应用根部即可，全局只需一个。 */
export function ToastHost() {
  const visible = useSyncExternalStore(subscribeToasts, getToasts, getToasts);

  if (visible.length === 0) return null;

  return (
    <div className="toast-host">
      {visible.map((item) => {
        const Icon = ICONS[item.kind];
        return (
          <div
            key={item.id}
            className={`toast-item is-${item.kind}`}
            role={item.kind === "error" ? "alert" : "status"}
          >
            <Icon aria-hidden="true" size={16} strokeWidth={2} />
            <span>{item.content}</span>
          </div>
        );
      })}
    </div>
  );
}
