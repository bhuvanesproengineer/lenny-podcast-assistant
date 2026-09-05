import React from 'react';
import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      className,
      variant = 'primary',
      size = 'md',
      isLoading = false,
      disabled,
      leftIcon,
      rightIcon,
      ...props
    },
    ref
  ) => {
    const variantStyles = {
      primary:
        'bg-[#3B82F6] text-[#F3F4F6] font-medium hover:bg-[#60A5FA] active:bg-blue-600 shadow-sm shadow-blue-500/20 disabled:opacity-50 disabled:pointer-events-none',
      secondary:
        'bg-[#212121] text-[#F3F4F6] hover:bg-[#2A2A2A] border border-[#2A2A2A] hover:border-slate-600/60 disabled:opacity-50 disabled:pointer-events-none',
      ghost:
        'text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121] disabled:opacity-50 disabled:pointer-events-none',
      outline:
        'border border-[#2A2A2A] text-[#F3F4F6] hover:border-[#3B82F6] hover:bg-[#212121] disabled:opacity-50 disabled:pointer-events-none',
      danger:
        'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 hover:border-red-500/40 disabled:opacity-50 disabled:pointer-events-none',
    };

    const sizeStyles = {
      sm: 'text-xs px-2.5 py-1.5 rounded-md gap-1.5',
      md: 'text-sm px-3 py-2 rounded-lg gap-2',
      lg: 'text-base px-4 py-2.5 rounded-xl gap-2.5',
      icon: 'p-2 rounded-lg',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(
          'inline-flex items-center justify-center transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6]/50 cursor-pointer disabled:cursor-not-allowed',
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin text-current" />
        ) : (
          leftIcon
        )}
        {children}
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = 'Button';
