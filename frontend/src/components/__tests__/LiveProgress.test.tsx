import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { WsMessage } from '../../hooks/useWebSocket';

const mockUseWebSocket = vi.fn<() => { messages: WsMessage[]; isConnected: boolean; lastEvent: WsMessage | null }>();

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

import LiveProgress from '../LiveProgress';

describe('LiveProgress', () => {
  it('shows "Pipeline Progress" heading', () => {
    mockUseWebSocket.mockReturnValue({
      messages: [],
      isConnected: true,
      lastEvent: null,
    });
    render(<LiveProgress runId="run-1" />);
    expect(screen.getByText('Pipeline Progress')).toBeInTheDocument();
  });

  it('shows "Live" when connected', () => {
    mockUseWebSocket.mockReturnValue({
      messages: [],
      isConnected: true,
      lastEvent: null,
    });
    render(<LiveProgress runId="run-1" />);
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows "Connecting..." when no messages and not connected', () => {
    mockUseWebSocket.mockReturnValue({
      messages: [],
      isConnected: false,
      lastEvent: null,
    });
    render(<LiveProgress runId="run-1" />);
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  it('shows stage entries when messages contain stage events', () => {
    mockUseWebSocket.mockReturnValue({
      messages: [
        { type: 'stage_started', stage: 'Requirements', status: 'running', timestamp: '2026-01-01T00:00:00Z' },
        { type: 'stage_completed', stage: 'Requirements', status: 'completed', timestamp: '2026-01-01T00:01:00Z' },
        { type: 'stage_started', stage: 'TestGen', status: 'running', timestamp: '2026-01-01T00:01:01Z' },
      ],
      isConnected: true,
      lastEvent: { type: 'stage_started', stage: 'TestGen', status: 'running' },
    });
    render(<LiveProgress runId="run-1" />);
    expect(screen.getByText('Requirements')).toBeInTheDocument();
    expect(screen.getByText('TestGen')).toBeInTheDocument();
  });

  it('shows "Pipeline completed successfully" when lastEvent is pipeline_completed', () => {
    mockUseWebSocket.mockReturnValue({
      messages: [
        { type: 'stage_completed', stage: 'Requirements', status: 'completed' },
      ],
      isConnected: false,
      lastEvent: { type: 'pipeline_completed' },
    });
    render(<LiveProgress runId="run-1" />);
    expect(
      screen.getByText('Pipeline completed successfully')
    ).toBeInTheDocument();
  });
});
