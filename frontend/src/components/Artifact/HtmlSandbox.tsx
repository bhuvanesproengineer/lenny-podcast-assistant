import React, { useMemo } from 'react';

interface HtmlSandboxProps {
  htmlContent: string;
  className?: string;
}

export function HtmlSandbox({ htmlContent, className }: HtmlSandboxProps) {
  // Wrap raw HTML in a safe styling template if not already a full document
  const safeDoc = useMemo(() => {
    if (htmlContent.includes('<html') || htmlContent.includes('<!DOCTYPE')) {
      return htmlContent;
    }

    return `
      <!DOCTYPE html>
      <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <style>
            :root {
              color-scheme: dark;
            }
            body {
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
              background-color: #0f172a;
              color: #f1f5f9;
              padding: 2rem;
              margin: 0;
              line-height: 1.6;
            }
            h1, h2, h3, h4, h5, h6 {
              color: #ffffff;
              margin-top: 1.5rem;
              margin-bottom: 0.5rem;
              font-weight: 700;
            }
            h1 { font-size: 1.8rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }
            h2 { font-size: 1.4rem; color: #f59e0b; }
            h3 { font-size: 1.2rem; }
            p { margin: 0.8rem 0; color: #cbd5e1; }
            a { color: #f59e0b; text-decoration: underline; }
            blockquote {
              border-left: 4px solid #f59e0b;
              margin: 1.5rem 0;
              padding: 0.5rem 1rem;
              background: #1e293b;
              font-style: italic;
              color: #94a3b8;
            }
            code {
              font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
              background: #1e293b;
              padding: 0.2rem 0.4rem;
              border-radius: 4px;
              font-size: 0.875rem;
              color: #fbbf24;
            }
            pre {
              background: #090d16;
              padding: 1rem;
              border-radius: 8px;
              overflow-x: auto;
              border: 1px solid #334155;
            }
            ul, ol { padding-left: 1.5rem; color: #cbd5e1; }
            li { margin-bottom: 0.4rem; }
          </style>
        </head>
        <body>
          ${htmlContent}
        </body>
      </html>
    `;
  }, [htmlContent]);

  return (
    <div className={`w-full h-full min-h-[400px] flex flex-col ${className || ''}`}>
      {/* 
        Sandboxed iframe strictly disallows scripts!
        sandbox="allow-same-origin" only allows rendering without running script execution.
      */}
      <iframe
        srcDoc={safeDoc}
        sandbox="allow-same-origin"
        title="Artifact HTML Sandbox"
        className="w-full flex-1 border-0 rounded-b-lg bg-surface-card"
      />
    </div>
  );
}
