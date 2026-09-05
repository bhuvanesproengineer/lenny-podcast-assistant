import React, { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';
import type { ToastMessage } from '@/types/chat';

interface ToastProps {
  toast: ToastMessage | null;
  onDismiss: () => void;
}

export function Toast({ toast, onDismiss }: ToastProps) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => {
      onDismiss();
    }, toast.duration || 3000);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  if (!toast) return null;

  const icons = {
    success: <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />,
    error: <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />,
    info: <Info className="w-4 h-4 text-[#3B82F6] shrink-0" />,
  };

  const borderStyles = {
    success: 'border-emerald-500/30 bg-[#212121] text-emerald-100',
    error: 'border-red-500/30 bg-[#212121] text-red-100',
    info: 'border-[#2A2A2A] bg-[#212121] text-[#F3F4F6]',
  };

  return (
    <div
      role="alert"
      className={cn(
        'fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl border shadow-xl backdrop-blur-md transition-all animate-in fade-in slide-in-from-bottom-3 duration-200',
        borderStyles[toast.type]
      )}
    >
      {icons[toast.type]}
      <span className="text-sm font-medium">{toast.message}</span>
      <button
        onClick={onDismiss}
        className="ml-2 text-slate-400 hover:text-slate-100 p-0.5 rounded cursor-pointer"
        aria-label="Dismiss toast"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
