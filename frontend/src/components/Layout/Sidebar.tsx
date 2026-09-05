'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useSessions } from '@/hooks/useSessions';
import { Button } from '@/components/UI/Button';
import { formatRelativeTime } from '@/lib/utils';
import {
  Plus,
  MessageSquare,
  Loader2,
  RefreshCw,
  Search,
  Pencil,
  Trash2,
  Check,
  X,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface SidebarProps {
  isOpen: boolean;
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  isCreatingSession: boolean;
}

export function Sidebar({
  isOpen,
  activeSessionId,
  onSelectSession,
  onNewChat,
  isCreatingSession,
}: SidebarProps) {
  const {
    sessions,
    isLoading,
    isError,
    refetchSessions,
    renameSession,
    deleteSession,
    isRenaming,
    isDeleting,
  } = useSessions();

  const [searchQuery, setSearchQuery] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement | null>(null);

  // Auto-focus input when starting inline edit
  useEffect(() => {
    if (editingSessionId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingSessionId]);

  const filteredSessions = sessions.filter((s) =>
    (s.title || `Chat ${s.id.slice(0, 8)}`)
      .toLowerCase()
      .includes(searchQuery.toLowerCase().trim())
  );

  const handleStartRename = (e: React.MouseEvent, id: string, currentTitle: string) => {
    e.stopPropagation();
    setEditingSessionId(id);
    setEditTitle(currentTitle);
    setDeletingSessionId(null);
  };

  const handleSaveRename = async (e?: React.FormEvent | React.MouseEvent) => {
    e?.stopPropagation();
    if (!editingSessionId) return;
    const trimmed = editTitle.trim();
    if (trimmed) {
      try {
        await renameSession({ id: editingSessionId, title: trimmed });
      } catch (err) {
        console.error('Failed to rename session:', err);
      }
    }
    setEditingSessionId(null);
    setEditTitle('');
  };

  const handleCancelRename = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setEditingSessionId(null);
    setEditTitle('');
  };

  const handleStartDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setDeletingSessionId(id);
    setEditingSessionId(null);
  };

  const handleConfirmDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await deleteSession(id);
      if (activeSessionId === id) {
        const remaining = sessions.filter((s) => s.id !== id);
        if (remaining.length > 0) {
          onSelectSession(remaining[0].id);
        } else {
          onNewChat();
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingSessionId(null);
  };

  if (!isOpen) return null;

  return (
    <aside
      className={cn(
        'w-64 md:w-72 bg-[#171717] border-r border-[#2A2A2A] flex flex-col h-full shrink-0 select-none z-10 transition-all duration-200'
      )}
    >
      {/* Top action: New Chat Button */}
      <div className="p-3 border-b border-[#2A2A2A] flex flex-col gap-2.5">
        <Button
          variant="primary"
          size="md"
          className="w-full justify-center shadow-md font-medium text-xs py-2 bg-[#3B82F6] hover:bg-[#60A5FA] text-[#F3F4F6] rounded-lg transition-all"
          onClick={onNewChat}
          isLoading={isCreatingSession}
          leftIcon={<Plus className="w-4 h-4" />}
        >
          New Chat
        </Button>

        {/* Real-time Search Input */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9CA3AF]" />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-7 py-1.5 text-xs bg-[#212121] text-[#F3F4F6] placeholder-[#9CA3AF]/60 rounded-lg border border-[#2A2A2A] focus:outline-none focus:border-[#3B82F6] transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9CA3AF] hover:text-[#F3F4F6] p-0.5 cursor-pointer"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <div className="flex items-center justify-between px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[#9CA3AF]">
          <span>Chat History</span>
          {searchQuery && (
            <span className="text-[10px] text-[#9CA3AF]/80 lowercase font-normal">
              {filteredSessions.length} found
            </span>
          )}
        </div>

        {isLoading && (
          <div className="flex flex-col items-center justify-center py-12 text-[#9CA3AF] gap-2">
            <Loader2 className="w-5 h-5 animate-spin text-[#3B82F6]" />
            <span className="text-xs">Loading chats...</span>
          </div>
        )}

        {isError && (
          <div className="p-3 rounded-lg bg-red-950/20 border border-red-900/30 text-center space-y-2">
            <p className="text-xs text-red-300">Failed to load chats</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetchSessions()}
              leftIcon={<RefreshCw className="w-3 h-3" />}
              className="text-xs py-1 h-auto w-full"
            >
              Retry
            </Button>
          </div>
        )}

        {!isLoading && !isError && filteredSessions.length === 0 && (
          <div className="text-center py-10 px-4">
            <MessageSquare className="w-7 h-7 text-[#9CA3AF]/40 mx-auto mb-2" />
            <p className="text-xs text-[#9CA3AF] font-medium">
              {searchQuery ? 'No matching chats' : 'No chats yet'}
            </p>
            <p className="text-[11px] text-[#9CA3AF]/60 mt-1">
              {searchQuery
                ? 'Try a different search keyword.'
                : 'Start a new conversation to ask product strategy.'}
            </p>
          </div>
        )}

        {!isLoading &&
          filteredSessions.map((session) => {
            const isActive = activeSessionId === session.id;
            const displayTitle = session.title || `Chat ${session.id.slice(0, 8)}`;
            const relativeTime = formatRelativeTime(session.updated_at);
            const isEditing = editingSessionId === session.id;
            const isDeletingThis = deletingSessionId === session.id;

            if (isEditing) {
              return (
                <div
                  key={session.id}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-[#212121] border border-[#3B82F6] flex items-center gap-1.5 shadow-sm"
                >
                  <input
                    ref={editInputRef}
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveRename();
                      if (e.key === 'Escape') handleCancelRename();
                    }}
                    className="flex-1 bg-transparent text-xs text-[#F3F4F6] focus:outline-none"
                    placeholder="Enter chat title..."
                  />
                  <button
                    onClick={handleSaveRename}
                    disabled={isRenaming}
                    className="p-1 text-emerald-400 hover:text-emerald-300 rounded hover:bg-[#2A2A2A] transition-colors cursor-pointer"
                    title="Save (Enter)"
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={handleCancelRename}
                    className="p-1 text-[#9CA3AF] hover:text-[#F3F4F6] rounded hover:bg-[#2A2A2A] transition-colors cursor-pointer"
                    title="Cancel (Esc)"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            }

            if (isDeletingThis) {
              return (
                <div
                  key={session.id}
                  className="w-full px-2.5 py-2 rounded-lg bg-red-950/40 border border-red-900/60 flex items-center justify-between gap-1 text-xs"
                >
                  <span className="text-red-300 font-medium truncate">Delete chat?</span>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={(e) => handleConfirmDelete(e, session.id)}
                      disabled={isDeleting}
                      className="px-2 py-0.5 rounded bg-red-600 hover:bg-red-500 text-white font-medium text-[11px] transition-colors cursor-pointer"
                    >
                      Delete
                    </button>
                    <button
                      onClick={handleCancelDelete}
                      className="px-1.5 py-0.5 rounded bg-[#212121] hover:bg-[#2A2A2A] text-[#9CA3AF] text-[11px] transition-colors cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              );
            }

            return (
              <div
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className={cn(
                  'group relative w-full text-left px-2.5 py-2 rounded-lg text-xs transition-all duration-150 flex items-center gap-2 cursor-pointer border',
                  isActive
                    ? 'bg-[#212121] text-[#F3F4F6] border-[#2A2A2A] font-medium shadow-sm'
                    : 'text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121]/50 border-transparent'
                )}
              >
                {/* Active Indicator Bar */}
                {isActive && (
                  <div className="absolute left-0 top-1.5 bottom-1.5 w-0.5 bg-[#3B82F6] rounded-r" />
                )}

                <MessageSquare
                  className={cn(
                    'w-3.5 h-3.5 shrink-0 transition-colors',
                    isActive ? 'text-[#3B82F6]' : 'text-[#9CA3AF] group-hover:text-[#F3F4F6]'
                  )}
                />

                <div className="flex-1 min-w-0 pr-1">
                  <div className="truncate font-medium text-[#F3F4F6]">
                    {displayTitle}
                  </div>
                  <div className="text-[10px] text-[#9CA3AF]/70 mt-0.5">
                    {relativeTime}
                  </div>
                </div>

                {/* Hover Action Buttons (Rename & Delete) */}
                <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 shrink-0 transition-opacity">
                  <button
                    onClick={(e) => handleStartRename(e, session.id, displayTitle)}
                    className="p-1 rounded text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#2A2A2A] transition-colors cursor-pointer"
                    title="Rename chat"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                  <button
                    onClick={(e) => handleStartDelete(e, session.id)}
                    className="p-1 rounded text-[#9CA3AF] hover:text-red-400 hover:bg-[#2A2A2A] transition-colors cursor-pointer"
                    title="Delete chat"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            );
          })}
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-[#2A2A2A] text-[11px] text-[#9CA3AF] flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-[#3B82F6]" />
          <span>Lenny Growth</span>
        </div>
        <span className="font-mono text-[10px] text-[#9CA3AF]/60">AI SaaS</span>
      </div>
    </aside>
  );
}

