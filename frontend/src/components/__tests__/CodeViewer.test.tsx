import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-syntax-highlighter', () => ({
  Prism: ({ children }: { children: string }) => (
    <pre data-testid="code-block">{children}</pre>
  ),
}));
vi.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({
  oneDark: {},
}));

import CodeViewer from '../CodeViewer';

describe('CodeViewer', () => {
  const sampleCode = 'const x = 42;\nconsole.log(x);';

  it('renders the code content', () => {
    render(<CodeViewer code={sampleCode} language="javascript" />);
    expect(screen.getByTestId('code-block')).toHaveTextContent(sampleCode);
  });

  it('shows filename in the header when provided', () => {
    render(
      <CodeViewer code={sampleCode} language="javascript" filename="app.js" />
    );
    expect(screen.getByText('app.js')).toBeInTheDocument();
  });

  it('shows language when no filename is provided', () => {
    render(<CodeViewer code={sampleCode} language="javascript" />);
    expect(screen.getByText('javascript')).toBeInTheDocument();
  });

  it('renders a copy button', () => {
    render(<CodeViewer code={sampleCode} language="javascript" />);
    expect(
      screen.getByRole('button', { name: /copy to clipboard/i })
    ).toBeInTheDocument();
  });

  it('calls navigator.clipboard.writeText when copy is clicked', async () => {
    render(<CodeViewer code={sampleCode} language="javascript" />);
    const copyBtn = screen.getByRole('button', { name: /copy to clipboard/i });
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(sampleCode);
    });
  });

  it('shows "Copied" text after clicking copy', async () => {
    render(<CodeViewer code={sampleCode} language="javascript" />);
    const copyBtn = screen.getByRole('button', { name: /copy to clipboard/i });
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(screen.getByText('Copied')).toBeInTheDocument();
    });
  });
});
