'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Header } from '@/components/Layout/Header';
import { Sidebar } from '@/components/Layout/Sidebar';
import { ChatPanel } from '@/components/Chat/ChatPanel';
import { ArtifactViewer } from '@/components/Artifact/ArtifactViewer';
import { Toast } from '@/components/UI/Toast';
import { ModelSettingsModal } from '@/components/UI/ModelSettingsModal';
import { useSessions } from '@/hooks/useSessions';
import { useChat } from '@/hooks/useChat';
import { api } from '@/lib/api';
import type { ArtifactData, ToastMessage } from '@/types/chat';

export default function Home() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isArtifactOpen, setIsArtifactOpen] = useState(false);
  const [currentArtifact, setCurrentArtifact] = useState<ArtifactData | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [isModelSettingsOpen, setIsModelSettingsOpen] = useState(false);
  const [activeProvider, setActiveProvider] = useState<string>('ollama');

  const {
    sessions,
    createSession,
    isCreating: isCreatingSession,
  } = useSessions();

  // Triggered when an assistant response is identified as an essay/artifact
  const handleArtifactDetected = useCallback((artifact: ArtifactData) => {
    setCurrentArtifact(artifact);
    setIsArtifactOpen(true);
    setToast({
      id: String(Date.now()),
      type: 'info',
      message: 'New Ship30 Essay artifact opened in side panel',
    });
  }, []);

  const {
    messages,
    isLoadingHistory,
    isSending,
    sendError,
    sessionTitle,
    sendMessage,
  } = useChat({
    sessionId: activeSessionId,
    onArtifactDetected: handleArtifactDetected,
  });

  // Automatically select the most recent session if none selected and sessions exist
  useEffect(() => {
    if (!activeSessionId && sessions.length > 0) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

  // Fetch initial active model provider from backend
  useEffect(() => {
    api
      .getProviderSettings()
      .then((data) => {
        if (data?.active_provider) {
          setActiveProvider(data.active_provider);
        }
      })
      .catch(() => {});
  }, []);

  // Handler to start a new chat session
  const handleNewChat = async () => {
    try {
      const newSession = await createSession(undefined);
      setActiveSessionId(newSession.session_id);
      setIsArtifactOpen(false);
      setCurrentArtifact(null);
    } catch (err: any) {
      setToast({
        id: String(Date.now()),
        type: 'error',
        message: err.message || 'Failed to create new chat session',
      });
    }
  };

  // Handler to send message (creates session first if none active)
  const handleSendMessage = async (text: string) => {
    try {
      let targetSessionId = activeSessionId;
      if (!targetSessionId) {
        // Create session on-the-fly with initial snippet as title
        const defaultTitle = text.slice(0, 30) + (text.length > 30 ? '...' : '');
        const created = await createSession(defaultTitle);
        targetSessionId = created.session_id;
        setActiveSessionId(created.session_id);
      }
      await sendMessage(text, targetSessionId ?? undefined);
    } catch (err: any) {
      setToast({
        id: String(Date.now()),
        type: 'error',
        message: err.message || 'Failed to send message',
      });
    }
  };

  // Handler when clicking "Open in Artifact Viewer" from a message
  const handleOpenArtifact = (artifact: ArtifactData) => {
    setCurrentArtifact(artifact);
    setIsArtifactOpen(true);
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#0F0F0F] text-[#F3F4F6] select-none">
      {/* Top Header */}
      <Header
        isSidebarOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        isArtifactOpen={isArtifactOpen}
        hasArtifact={!!currentArtifact}
        onToggleArtifact={() => setIsArtifactOpen((prev) => !prev)}
        onNewChat={handleNewChat}
        activeProvider={activeProvider}
        onOpenModelSettings={() => setIsModelSettingsOpen(true)}
      />

      {/* Main 3-Panel Content Area */}
      <div className="flex flex-1 min-h-0 relative overflow-hidden">
        {/* Panel 1: Left Sidebar */}
        <Sidebar
          isOpen={isSidebarOpen}
          activeSessionId={activeSessionId}
          onSelectSession={(id) => {
            setActiveSessionId(id);
          }}
          onNewChat={handleNewChat}
          isCreatingSession={isCreatingSession}
        />

        {/* Panel 2: Center Chat Panel */}
        <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
          <ChatPanel
            messages={messages}
            isLoadingHistory={isLoadingHistory}
            isSending={isSending}
            sendError={sendError}
            sessionTitle={sessionTitle || undefined}
            onSendMessage={handleSendMessage}
            onOpenArtifact={handleOpenArtifact}
            onCopyText={() =>
              setToast({
                id: String(Date.now()),
                type: 'success',
                message: 'Copied to clipboard!',
              })
            }
          />
        </main>

        {/* Panel 3: Right Artifact Viewer */}
        {isArtifactOpen && currentArtifact && (
          <ArtifactViewer
            artifact={currentArtifact}
            isOpen={isArtifactOpen}
            onClose={() => setIsArtifactOpen(false)}
          />
        )}
      </div>

      {/* Global Toast */}
      <Toast toast={toast} onDismiss={() => setToast(null)} />

      {/* Dual Model Layer Settings Modal */}
      <ModelSettingsModal
        isOpen={isModelSettingsOpen}
        onClose={() => setIsModelSettingsOpen(false)}
        activeProvider={activeProvider}
        onProviderChanged={(newProvider) => setActiveProvider(newProvider)}
      />
    </div>
  );
}
