import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { countWords } from '@/lib/utils';
import { Clock, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MarkdownPreviewProps {
  content: string;
  className?: string;
}

export function MarkdownPreview({ content, className }: MarkdownPreviewProps) {
  const words = countWords(content);
  const readTime = Math.max(1, Math.ceil(words / 225));

  return (
    <div className={cn('p-6 md:p-10 max-w-3xl mx-auto space-y-6', className)}>
      {/* Stats bar */}
      <div className="flex items-center gap-2.5 text-xs text-[#9CA3AF] pb-4 border-b border-[#2A2A2A]">
        <span className="flex items-center gap-1.5 bg-[#212121] px-2.5 py-1 rounded-lg border border-[#2A2A2A]">
          <FileText className="w-3.5 h-3.5 text-[#3B82F6]" />
          <strong className="text-[#F3F4F6] font-mono">{words.toLocaleString()}</strong> words
        </span>
        <span className="flex items-center gap-1.5 bg-[#212121] px-2.5 py-1 rounded-lg border border-[#2A2A2A]">
          <Clock className="w-3.5 h-3.5 text-[#3B82F6]" />
          <strong className="text-[#F3F4F6] font-mono">~{readTime}</strong> min read
        </span>
      </div>

      {/* Rendered Essay */}
      <article className="prose prose-invert max-w-none text-[#F3F4F6]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            h1: ({ children }) => (
              <h1 className="text-2xl md:text-3xl font-bold text-[#F3F4F6] tracking-tight mt-6 mb-4 pb-3 border-b border-[#2A2A2A] leading-snug">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-xl md:text-2xl font-bold text-[#F3F4F6] tracking-tight mt-8 mb-3 pb-1 border-b border-[#2A2A2A]/60 leading-snug">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-base md:text-lg font-semibold text-[#60A5FA] mt-6 mb-2">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="text-sm md:text-base text-[#F3F4F6]/90 leading-relaxed my-3.5 font-normal">
                {children}
              </p>
            ),
            blockquote: ({ children }) => (
              <blockquote className="border-l-3 border-[#3B82F6] bg-[#212121]/60 px-4 py-3 my-5 rounded-r-xl italic text-[#9CA3AF] text-sm">
                {children}
              </blockquote>
            ),
            ul: ({ children }) => (
              <ul className="list-disc pl-6 space-y-2 my-4 text-sm md:text-base text-[#F3F4F6]/90">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="list-decimal pl-6 space-y-2 my-4 text-sm md:text-base text-[#F3F4F6]/90">
                {children}
              </ol>
            ),
            li: ({ children }) => (
              <li className="leading-relaxed">{children}</li>
            ),
            hr: () => <hr className="border-[#2A2A2A] my-8" />,
            code: ({ className, children, ...props }) => {
              const match = /language-(\w+)/.exec(className || '');
              return match ? (
                <code
                  className={cn(
                    'block p-4 rounded-xl bg-[#0F0F0F] font-mono text-xs overflow-x-auto border border-[#2A2A2A] text-blue-200 my-4 shadow-sm',
                    className
                  )}
                  {...props}
                >
                  {children}
                </code>
              ) : (
                <code
                  className="px-1.5 py-0.5 rounded bg-[#212121] font-mono text-xs text-[#60A5FA] border border-[#2A2A2A]"
                  {...props}
                >
                  {children}
                </code>
              );
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </article>
    </div>
  );
}
