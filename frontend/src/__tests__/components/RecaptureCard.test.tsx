import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RecaptureCard from '@/components/RecaptureCard';

afterEach(() => cleanup());

describe('RecaptureCard', () => {
  it('shows the retake instruction prominently', () => {
    render(
      <RecaptureCard
        scanId="scan-1"
        instruction="Tilt the phone to remove the glare on the top-left corner."
        attempt={1}
        onRetake={vi.fn()}
      />
    );
    expect(screen.getByRole('region', { name: 'Please take the photo again' })).toBeInTheDocument();
    expect(
      screen.getByText('Tilt the phone to remove the glare on the top-left corner.')
    ).toBeInTheDocument();
    expect(screen.getByText(/attempt 1/)).toBeInTheDocument();
  });

  it('passes the scan id as the re-shot parent when Retake photo is clicked', async () => {
    const onRetake = vi.fn();
    const user = userEvent.setup();
    render(<RecaptureCard scanId="scan-42" instruction="Move closer." onRetake={onRetake} />);

    await user.click(screen.getByRole('button', { name: 'Retake photo' }));
    expect(onRetake).toHaveBeenCalledWith('scan-42');
  });

  it('shows an evidence thumbnail when evidence is available', () => {
    render(
      <RecaptureCard
        scanId="scan-1"
        instruction="Move closer."
        evidenceSrc="/api/v1/images/object/evidence/x.jpg"
        onRetake={vi.fn()}
      />
    );
    expect(
      screen.getByRole('button', { name: /view full size: why a retake is needed/i })
    ).toBeInTheDocument();
  });
});
