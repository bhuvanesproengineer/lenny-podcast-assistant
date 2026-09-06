import React from 'react';
import { useHealth } from '@/hooks/useHealth';
import { Badge } from '@/components/UI/Badge';
import { Button } from '@/components/UI/Button';
import {
  Sparkles,
  PanelLeftClose,
  PanelLeft,
  PanelRightClose,
  PanelRight,
  Plus,
  Cpu,
  Cloud,
  SlidersHorizontal,
  Database,
  RefreshCw,
} from 'lucide-react';

interface HeaderProps {
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
  isArtifactOpen: boolean;
  hasArtifact: boolean;
  onToggleArtifact: () => void;
  onNewChat: () => void;
  activeProvider?: string;
  onOpenModelSettings?: () => void;
}

export function Header({
  isSidebarOpen,
  onToggleSidebar,
  isArtifactOpen,
  hasArtifact,
  onToggleArtifact,
  onNewChat,
  activeProvider = 'ollama',
  onOpenModelSettings,
}: HeaderProps) {
  const { data: health, isLoading: isHealthLoading, isError: isHealthError, refetch } = useHealth();

  const isHealthy = !isHealthError && health?.status === 'healthy';

  return (
    <header className="h-14 border-b border-[#2A2A2A] bg-[#0F0F0F]/95 backdrop-blur-md px-4 flex items-center justify-between shrink-0 z-20">
      {/* Left section: Sidebar toggle & Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121] rounded-lg transition-colors cursor-pointer"
          title={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
          aria-label={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
        >
          {isSidebarOpen ? (
            <PanelLeftClose className="w-4 h-4" />
          ) : (
            <PanelLeft className="w-4 h-4" />
          )}
        </button>

        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-blue-600 to-[#3B82F6] flex items-center justify-center text-white shadow-sm shadow-blue-500/30">
            <Sparkles className="w-3.5 h-3.5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-[#F3F4F6] tracking-tight leading-none flex items-center gap-2">
              Lenny Growth
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[#3B82F6]/10 text-[#60A5FA] font-medium border border-[#3B82F6]/25">
                AI Assistant
              </span>
            </h1>
          </div>
        </div>
      </div>

      {/* Center/Right section: System indicators & Actions */}
      <div className="flex items-center gap-2">
        {/* Model Provider Switcher Badge */}
        <button
          onClick={onOpenModelSettings}
          className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-mono transition-all cursor-pointer ${
            activeProvider === 'cloud'
              ? 'bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20 hover:border-blue-500/50'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/50'
          }`}
          title="Click to configure Dual Model Layer (Local Ollama vs Cloud Groq)"
        >
          {activeProvider === 'cloud' ? (
            <>
              <Cloud className="w-3.5 h-3.5 text-blue-400" />
              <span>Cloud (Groq)</span>
            </>
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Ollama Local</span>
            </>
          )}
          <SlidersHorizontal className="w-3 h-3 text-[#9CA3AF] ml-0.5" />
        </button>

        {/* Health Status Indicator */}
        <div
          className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#212121] border border-[#2A2A2A] text-xs cursor-pointer hover:border-slate-600 transition-colors"
          onClick={() => refetch()}
          title={`Backend status: ${health?.status ?? (isHealthError ? 'Disconnected' : 'Checking...')}. Click to refresh.`}
        >
          <span className="relative flex h-2 w-2">
            {isHealthy && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                isHealthy
                  ? 'bg-emerald-500'
                  : isHealthLoading
                  ? 'bg-amber-400'
                  : 'bg-red-500'
              }`}
            ></span>
          </span>
          <span className="text-[#9CA3AF] text-[11px] font-medium hidden md:inline">
            {isHealthy
              ? `API Online (${health?.database})`
              : isHealthLoading
              ? 'Connecting...'
              : 'Backend Offline'}
          </span>
        </div>

        {/* New Chat Button */}
        <Button
          variant="outline"
          size="sm"
          onClick={onNewChat}
          leftIcon={<Plus className="w-3.5 h-3.5 text-[#3B82F6]" />}
          className="hidden sm:inline-flex text-xs h-8 border-[#2A2A2A] hover:border-[#3B82F6]"
        >
          New Chat
        </Button>

        {/* Artifact Toggle Button */}
        {hasArtifact && (
          <Button
            variant={isArtifactOpen ? 'primary' : 'secondary'}
            size="sm"
            onClick={onToggleArtifact}
            leftIcon={
              isArtifactOpen ? (
                <PanelRightClose className="w-3.5 h-3.5" />
              ) : (
                <PanelRight className="w-3.5 h-3.5" />
              )
            }
            className="text-xs h-8"
          >
            {isArtifactOpen ? 'Hide Artifact' : 'View Artifact'}
          </Button>
        )}
      </div>
    </header>
  );
}
