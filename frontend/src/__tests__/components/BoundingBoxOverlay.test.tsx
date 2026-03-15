import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import BoundingBoxOverlay from '@/components/BoundingBoxOverlay';

describe('BoundingBoxOverlay', () => {
  it('renders SVG rects for each box', () => {
    const boxes = [
      { x: 10, y: 20, w: 30, h: 40, conf: 0.92 },
      { x: 50, y: 60, w: 30, h: 40, conf: 0.85 },
    ];
    const { container } = render(
      <BoundingBoxOverlay
        boxes={boxes}
        naturalWidth={640}
        naturalHeight={480}
        displayWidth={320}
        displayHeight={240}
      />,
    );
    const rects = container.querySelectorAll('rect');
    expect(rects).toHaveLength(2);
    const texts = container.querySelectorAll('text');
    expect(texts).toHaveLength(2);
    expect(texts[0].textContent).toBe('92%');
    expect(texts[1].textContent).toBe('85%');
  });

  it('renders nothing when dimensions are zero', () => {
    const { container } = render(
      <BoundingBoxOverlay
        boxes={[{ x: 10, y: 20, w: 30, h: 40, conf: 0.9 }]}
        naturalWidth={0}
        naturalHeight={0}
        displayWidth={0}
        displayHeight={0}
      />,
    );
    expect(container.querySelector('svg')).toBeNull();
  });
});
