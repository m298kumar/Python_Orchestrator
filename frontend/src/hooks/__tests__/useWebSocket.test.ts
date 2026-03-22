import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { UseWebSocketReturn } from '../useWebSocket';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  send = vi.fn();
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
}

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  async function importHook() {
    // Re-import to pick up the mock WebSocket
    const mod = await import('../useWebSocket');
    return mod.useWebSocket;
  }

  it('returns initial state with not connected and no messages', async () => {
    const useWebSocket = await importHook();
    const { result } = renderHook(() => useWebSocket(null));
    expect(result.current.isConnected).toBe(false);
    expect(result.current.messages).toEqual([]);
  });

  it('returns null lastEvent initially', async () => {
    const useWebSocket = await importHook();
    const { result } = renderHook(() => useWebSocket(null));
    expect(result.current.lastEvent).toBeNull();
  });

  it('does not create WebSocket when runId is null', async () => {
    const useWebSocket = await importHook();
    renderHook(() => useWebSocket(null));
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it('creates WebSocket when runId is provided', async () => {
    const useWebSocket = await importHook();
    renderHook(() => useWebSocket('run-123'));
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1);
    expect(MockWebSocket.instances[0].url).toContain('run-123');
  });

  it('cleans up WebSocket on unmount by calling close', async () => {
    const useWebSocket = await importHook();
    const { unmount } = renderHook(() => useWebSocket('run-456'));
    const ws = MockWebSocket.instances[0];
    unmount();
    expect(ws.close).toHaveBeenCalled();
  });
});
