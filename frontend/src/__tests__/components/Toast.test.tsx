import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Toast from '@/components/Toast';

describe('Toast', () => {
  it('renders message when show is true', () => {
    render(<Toast message="Saved!" show={true} />);
    expect(screen.getByText('Saved!')).toBeInTheDocument();
  });

  it('renders nothing when show is false', () => {
    const { container } = render(<Toast message="Saved!" show={false} />);
    expect(container.firstChild).toBeNull();
  });
});
