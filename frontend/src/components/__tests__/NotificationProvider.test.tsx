import type React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NotificationProvider, { useNotification } from '../NotificationProvider';

function TestConsumer({
  message = 'Hello',
  type = 'success',
}: {
  message?: string;
  type?: 'success' | 'error' | 'info' | 'warning';
}) {
  const { notify } = useNotification();
  return <button onClick={() => notify(message, type)}>Trigger</button>;
}

function renderWithProvider(ui: React.ReactElement) {
  return render(<NotificationProvider>{ui}</NotificationProvider>);
}

describe('NotificationProvider', () => {
  it('renders children', () => {
    renderWithProvider(<div data-testid="child">Content</div>);
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('useNotification hook returns a notify function', () => {
    let notifyFn: any;
    function Probe() {
      const { notify } = useNotification();
      notifyFn = notify;
      return null;
    }
    renderWithProvider(<Probe />);
    expect(typeof notifyFn).toBe('function');
  });

  it('calling notify adds a toast to the DOM', async () => {
    renderWithProvider(<TestConsumer message="Test toast" />);
    fireEvent.click(screen.getByText('Trigger'));
    await waitFor(() => {
      expect(screen.getByText('Test toast')).toBeInTheDocument();
    });
  });

  it('toast shows the correct message text', async () => {
    renderWithProvider(<TestConsumer message="Something happened" />);
    fireEvent.click(screen.getByText('Trigger'));
    await waitFor(() => {
      expect(screen.getByText('Something happened')).toBeInTheDocument();
    });
  });

  it('each notification type has a different background class', async () => {
    const types = ['success', 'error', 'info', 'warning'] as const;
    const bgClasses = ['bg-green-50', 'bg-red-50', 'bg-blue-50', 'bg-yellow-50'];

    for (let i = 0; i < types.length; i++) {
      const { unmount } = renderWithProvider(
        <TestConsumer message={`msg-${types[i]}`} type={types[i]} />,
      );
      fireEvent.click(screen.getByText('Trigger'));
      await waitFor(() => {
        const toast = screen.getByText(`msg-${types[i]}`).closest('div');
        expect(toast?.className).toContain(bgClasses[i]);
      });
      unmount();
    }
  });

  it('dismiss button removes the toast', async () => {
    renderWithProvider(<TestConsumer message="Dismiss me" />);
    fireEvent.click(screen.getByText('Trigger'));

    await waitFor(() => {
      expect(screen.getByText('Dismiss me')).toBeInTheDocument();
    });

    // The dismiss button is the X button inside the toast
    const toast = screen.getByText('Dismiss me').closest('div') as HTMLElement;
    const dismissBtn = toast.querySelector('button') as HTMLElement;
    fireEvent.click(dismissBtn);

    // After dismiss animation (300ms), the toast should be removed
    await waitFor(
      () => {
        expect(screen.queryByText('Dismiss me')).not.toBeInTheDocument();
      },
      { timeout: 1000 },
    );
  });
});
