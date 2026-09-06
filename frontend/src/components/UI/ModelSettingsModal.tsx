'use client';

import React, { useState, useEffect } from 'react';
import {
  Cpu,
  Cloud,
  CheckCircle2,
  AlertCircle,
  X,
  RefreshCw,
  ShieldCheck,
  Zap,
  ExternalLink,
} from 'lucide-react';
import { api } from '@/lib/api';
import { ProviderSettingsResponse } from '@/types/api';
import { Button } from './Button';

interface ModelSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeProvider: string;
  onProviderChanged: (newProvider: string) => void;
}

export function ModelSettingsModal({
  isOpen,
  onClose,
  activeProvider,
  onProviderChanged,
}: ModelSettingsModalProps) {
  const [settings, setSettings] = useState<ProviderSettingsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const data = await api.getProviderSettings();
      setSettings(data);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to load model settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchSettings();
      setErrorMsg(null);
      setSuccessMsg(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelectProvider = async (target: 'ollama' | 'cloud') => {
    if (target === settings?.active_provider) return;
    try {
      setSwitching(target);
      setErrorMsg(null);
      setSuccessMsg(null);
      const updated = await api.setProviderSettings(target);
      setSettings(updated);
      onProviderChanged(updated.active_provider);
      setSuccessMsg(
        target === 'cloud'
          ? 'Switched to Cloud Model (Claude Sonnet via OpenRouter).'
          : 'Switched to Local Model (Ollama llama3.2:3b).'
      );
    } catch (err: any) {
      setErrorMsg(err?.message || `Failed to switch to ${target} provider`);
    } finally {
      setSwitching(null);
    }
  };

  const currentActive = settings?.active_provider || activeProvider || 'ollama';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl bg-[#171717] border border-[#2A2A2A] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#2A2A2A] bg-[#1A1A1A]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-[#3B82F6]">
              <Cpu className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-[#F3F4F6]">
                Dual Model Layer Settings
              </h2>
              <p className="text-xs text-[#9CA3AF]">
                Switch seamlessly between Local LLM and Cloud LLM with zero code changes
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121] rounded-lg transition-colors cursor-pointer"
            aria-label="Close settings"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-4">
          {errorMsg && (
            <div className="flex items-start gap-2.5 p-3.5 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="flex items-start gap-2.5 p-3.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400 text-xs">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{successMsg}</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {/* Local LLM Option */}
            <div
              onClick={() => handleSelectProvider('ollama')}
              className={`relative cursor-pointer p-4 rounded-xl border transition-all ${
                currentActive === 'ollama'
                  ? 'bg-emerald-500/5 border-emerald-500/40 shadow-sm shadow-emerald-500/10'
                  : 'bg-[#212121]/60 border-[#2A2A2A] hover:border-[#3B82F6]/40 hover:bg-[#212121]'
              }`}
            >
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                    <Cpu className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-[#F3F4F6]">Local LLM</h3>
                    <span className="text-[10px] text-emerald-400 font-mono">Mandatory Demo</span>
                  </div>
                </div>
                {currentActive === 'ollama' && (
                  <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3" /> Active
                  </span>
                )}
              </div>

              <div className="space-y-1.5 text-xs text-[#9CA3AF] mt-3">
                <div className="flex justify-between font-mono text-[11px]">
                  <span>Engine:</span>
                  <span className="text-[#F3F4F6]">Ollama</span>
                </div>
                <div className="flex justify-between font-mono text-[11px]">
                  <span>Model:</span>
                  <span className="text-emerald-300 font-semibold">
                    {settings?.local?.model || 'llama3.2:3b'}
                  </span>
                </div>
                <div className="flex justify-between font-mono text-[11px]">
                  <span>Host:</span>
                  <span className="truncate max-w-[140px]" title={settings?.local?.base_url}>
                    {settings?.local?.base_url || 'http://localhost:11434'}
                  </span>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-[#2A2A2A]/80 flex justify-between items-center">
                <span className="text-[11px] text-emerald-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  Privacy / On-device
                </span>
                <Button
                  size="sm"
                  variant={currentActive === 'ollama' ? 'secondary' : 'primary'}
                  disabled={currentActive === 'ollama' || switching === 'ollama'}
                  className="text-xs h-7 px-2.5"
                >
                  {switching === 'ollama'
                    ? 'Switching...'
                    : currentActive === 'ollama'
                    ? 'Selected'
                    : 'Select'}
                </Button>
              </div>
            </div>

            {/* Cloud LLM Option */}
            <div
              onClick={() => handleSelectProvider('cloud')}
              className={`relative cursor-pointer p-4 rounded-xl border transition-all ${
                currentActive === 'cloud'
                  ? 'bg-blue-500/5 border-[#3B82F6]/50 shadow-sm shadow-blue-500/10'
                  : 'bg-[#212121]/60 border-[#2A2A2A] hover:border-[#3B82F6]/40 hover:bg-[#212121]'
              }`}
            >
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-[#3B82F6]">
                    <Cloud className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-[#F3F4F6]">Cloud LLM</h3>
                    <span className="text-[10px] text-blue-400 font-mono">Groq Cloud</span>
                  </div>
                </div>
                {currentActive === 'cloud' && (
                  <span className="flex items-center gap-1 text-[11px] font-medium text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3" /> Active
                  </span>
                )}
              </div>

              <div className="space-y-1.5 text-xs text-[#9CA3AF] mt-3">
                <div className="flex justify-between font-mono text-[11px]">
                  <span>Gateway:</span>
                  <span className="text-[#F3F4F6]">Groq API</span>
                </div>
                <div className="flex justify-between font-mono text-[11px]">
                  <span>Model:</span>
                  <span className="text-blue-300 font-semibold truncate max-w-[140px]" title={settings?.cloud?.model}>
                    {settings?.cloud?.model || 'openai/gpt-oss-20b'}
                  </span>
                </div>
                <div className="flex justify-between font-mono text-[11px]">
                  <span>API Key:</span>
                  <span className={settings?.cloud?.available ? 'text-emerald-400 font-medium' : 'text-amber-400'}>
                    {settings?.cloud?.available ? 'Configured' : 'Not Detected'}
                  </span>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-[#2A2A2A]/80 flex justify-between items-center">
                <span className="text-[11px] text-blue-400 flex items-center gap-1">
                  <Zap className="w-3 h-3" />
                  High Reasoning
                </span>
                <Button
                  size="sm"
                  variant={currentActive === 'cloud' ? 'secondary' : 'primary'}
                  disabled={currentActive === 'cloud' || switching === 'cloud'}
                  className="text-xs h-7 px-2.5"
                >
                  {switching === 'cloud'
                    ? 'Switching...'
                    : currentActive === 'cloud'
                    ? 'Selected'
                    : 'Select'}
                </Button>
              </div>
            </div>
          </div>

          {/* Automatic Fallback Behavior Card */}
          <div className="p-4 rounded-xl bg-[#212121]/40 border border-[#2A2A2A] space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#F3F4F6]">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Automatic Local Fallback Guarantee</span>
              <span className="ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                ACTIVE
              </span>
            </div>
            <p className="text-[12px] text-[#9CA3AF] leading-relaxed">
              If the Cloud LLM experiences rate limits, network outages, or API key errors,
              the backend gracefully logs the warning and automatically redirects the prompt to
              the local <strong>Ollama (llama3.2:3b)</strong> instance without breaking your workflow.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3.5 border-t border-[#2A2A2A] bg-[#1A1A1A]">
          <span className="text-xs text-[#9CA3AF]">
            Configured via <code className="font-mono text-[11px] text-slate-300">LLM_PROVIDER</code> in <code className="font-mono text-[11px] text-slate-300">.env</code>
          </span>
          <Button variant="secondary" size="sm" onClick={onClose} className="text-xs h-8">
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
