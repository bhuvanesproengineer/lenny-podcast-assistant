import React from 'react';
import { cn } from '@/lib/utils';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'tool' | 'success' | 'warning' | 'error' | 'outline';
  size?: 'sm' | 'md';
}

export function Badge({
  children,
  className,
  variant = 'default',
  size = 'sm',
  ...props
}: BadgeProps) {
  const variantStyles = {
    default: 'bg-[#212121] text-[#9CA3AF] border border-[#2A2A2A]',
    tool: 'bg-[#3B82F6]/10 text-[#60A5FA] border border-[#3B82F6]/25 font-mono font-medium',
    success: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
    warning: 'bg-amber-500/10 text-amber-300 border border-amber-500/20',
    error: 'bg-red-500/10 text-red-400 border border-red-500/20',
    outline: 'border border-[#2A2A2A] text-[#9CA3AF] bg-transparent',
  };

  const sizeStyles = {
    sm: 'text-xs px-2 py-0.5 rounded-md gap-1',
    md: 'text-sm px-2.5 py-1 rounded-lg gap-1.5',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center font-medium transition-colors select-none',
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
