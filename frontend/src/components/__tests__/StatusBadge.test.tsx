import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from '../StatusBadge';

describe('StatusBadge', () => {
  it('renders "completed" status with green styling', () => {
    const { container } = render(<StatusBadge status="completed" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('bg-green-100');
    expect(badge.className).toContain('text-green-700');
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('renders "running" status with blue styling and pulse animation', () => {
    const { container } = render(<StatusBadge status="running" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('bg-blue-100');
    expect(badge.className).toContain('text-blue-700');
    // The dot element should have animate-pulse
    const dot = badge.querySelector('span span') as HTMLElement;
    expect(dot.className).toContain('animate-pulse');
  });

  it('renders "failed" status with red styling', () => {
    const { container } = render(<StatusBadge status="failed" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('bg-red-100');
    expect(badge.className).toContain('text-red-700');
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('renders "pending" status with blue styling and pulse animation', () => {
    const { container } = render(<StatusBadge status="pending" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('bg-blue-100');
    const dot = badge.querySelector('span span') as HTMLElement;
    expect(dot.className).toContain('animate-pulse');
  });

  it('renders "skipped" status with gray styling', () => {
    const { container } = render(<StatusBadge status="skipped" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('bg-gray-100');
    expect(badge.className).toContain('text-gray-600');
  });

  it('renders "generated" status with yellow styling', () => {
    const { container } = render(<StatusBadge status="generated" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('bg-yellow-100');
    expect(badge.className).toContain('text-yellow-700');
  });

  it('renders unknown status with gray fallback', () => {
    const { container } = render(<StatusBadge status="unknown_xyz" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('bg-gray-100');
    expect(badge.className).toContain('text-gray-600');
  });

  it('renders smaller text with size="sm"', () => {
    const { container } = render(<StatusBadge status="completed" size="sm" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain('text-xs');
    expect(badge.className).toContain('px-2');
    expect(badge.className).toContain('py-0.5');
  });

  it('capitalizes the first letter of the status text', () => {
    render(<StatusBadge status="running" />);
    expect(screen.getByText('Running')).toBeInTheDocument();
  });

  it('renders the dot element inside the badge', () => {
    const { container } = render(<StatusBadge status="completed" />);
    const badge = container.firstElementChild as HTMLElement;
    const dot = badge.querySelector('span span') as HTMLElement;
    expect(dot).toBeInTheDocument();
    expect(dot.className).toContain('rounded-full');
    expect(dot.className).toContain('bg-green-500');
  });
});
