import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeViewerProps {
  code: string;
  language?: string;
  className?: string;
}

export function CodeViewer({ code, language = 'markdown', className }: CodeViewerProps) {
  const [copied, setCopied] = useState(false);
  const lines = code.split('\n');

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`relative flex flex-col h-full bg-surface-base font-mono text-xs ${className || ''}`}>
      {/* Code Header Bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface-card border-b border-surface-border text-slate-400">
        <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-300">
          {language} ({lines.length} lines)
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface-elevated hover:bg-slate-700 text-xs text-slate-200 transition-colors cursor-pointer border border-surface-border"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-medium">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copy Raw</span>
            </>
          )}
        </button>
      </div>

      {/* Code Area with Line Numbers */}
      <div className="flex-1 overflow-auto p-4 flex">
        {/* Line Numbers */}
        <div className="select-none text-right pr-4 text-slate-600 font-mono text-xs leading-6 border-r border-slate-800 shrink-0">
          {lines.map((_, i) => (
            <div key={i}>{i + 1}</div>
          ))}
        </div>

        {/* Code Content */}
        <pre className="pl-4 m-0 font-mono text-xs text-slate-300 leading-6 overflow-x-auto flex-1">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}
