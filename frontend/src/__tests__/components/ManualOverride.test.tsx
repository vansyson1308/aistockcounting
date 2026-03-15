import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ManualOverride from '@/components/ManualOverride';

afterEach(() => cleanup());

describe('ManualOverride', () => {
  function makeProps() {
    return {
      manualCount: 5 as number | '',
      setManualCount: vi.fn(),
      isAICorrect: null as boolean | null,
      setIsAICorrect: vi.fn(),
      notes: '',
      setNotes: vi.fn(),
    };
  }

  it('renders all inputs and labels', () => {
    render(<ManualOverride {...makeProps()} />);
    expect(screen.getByPlaceholderText('Nhập số lượng thực tế')).toBeInTheDocument();
    expect(screen.getByText('Đúng')).toBeInTheDocument();
    expect(screen.getByText('Sai')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Ví dụ: món ở góc bị che')).toBeInTheDocument();
  });

  it('calls setIsAICorrect when buttons are clicked', async () => {
    const props = makeProps();
    const user = userEvent.setup();
    render(<ManualOverride {...props} />);

    await user.click(screen.getByText('Đúng'));
    expect(props.setIsAICorrect).toHaveBeenCalledWith(true);

    await user.click(screen.getByText('Sai'));
    expect(props.setIsAICorrect).toHaveBeenCalledWith(false);
  });
});
