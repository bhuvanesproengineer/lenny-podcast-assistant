import React from 'react';
import { cn } from '@/lib/utils';

export interface TabItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  count?: number;
}

interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (tabId: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className }: TabsProps) {
  return (
    <div
      className={cn(
        'flex items-center space-x-1 p-1 bg-[#171717] border border-[#2A2A2A] rounded-lg',
        className
      )}
      role="tablist"
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 select-none cursor-pointer',
              isActive
                ? 'bg-[#212121] text-[#F3F4F6] shadow-sm border border-[#2A2A2A] font-medium'
                : 'text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121]/50'
            )}
          >
            {tab.icon && <span className="w-3.5 h-3.5">{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span
                className={cn(
                  'ml-1 px-1.5 py-0.2 rounded-full text-[10px]',
                  isActive
                    ? 'bg-[#3B82F6]/20 text-[#60A5FA]'
                    : 'bg-[#212121] text-[#9CA3AF]'
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
