import { X } from "lucide-react";

export function Modal({ open, onClose, title, eyebrow, hint, children, testid = "modal", wide = false }) {
  if (!open) return null;
  return <div className="modal-backdrop" onClick={onClose} data-testid={`${testid}-backdrop`}>
    <div className={`modal ${wide ? "wide" : ""}`} onClick={e => e.stopPropagation()} data-testid={testid}>
      <div className="drawer-head"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2>{hint && <span className="muted">{hint}</span>}</div><button className="icon-btn" onClick={onClose} data-testid={`${testid}-close`}><X size={18} /></button></div>
      {children}
    </div>
  </div>;
}
