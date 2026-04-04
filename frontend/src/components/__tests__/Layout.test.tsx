import type React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Layout from '../Layout';

function renderLayout(children: React.ReactNode = <div>Page Content</div>) {
  return render(
    <MemoryRouter>
      <Layout>{children}</Layout>
    </MemoryRouter>,
  );
}

describe('Layout', () => {
  it('renders sidebar with "STLC Platform" text', () => {
    renderLayout();
    expect(screen.getByText('STLC Platform')).toBeInTheDocument();
  });

  it('renders 9 navigation links', () => {
    renderLayout();
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(9);
  });

  it('Dashboard link exists and points to "/"', () => {
    renderLayout();
    const link = screen.getByRole('link', { name: /dashboard/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/');
  });

  it('Requirements link exists and points to "/requirements"', () => {
    renderLayout();
    const link = screen.getByRole('link', { name: /requirements/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/requirements');
  });

  it('renders children in the main content area', () => {
    renderLayout(<div data-testid="test-child">Hello World</div>);
    expect(screen.getByTestId('test-child')).toBeInTheDocument();
    expect(screen.getByText('Hello World')).toBeInTheDocument();
  });

  it('has version text "v0.1.0"', () => {
    renderLayout();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
  });
});
