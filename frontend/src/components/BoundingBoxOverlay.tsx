import { Box } from '@/types';

type Props = {
  boxes: Box[];
  naturalWidth: number;
  naturalHeight: number;
  displayWidth: number;
  displayHeight: number;
};

export default function BoundingBoxOverlay({ boxes, naturalWidth, naturalHeight, displayWidth, displayHeight }: Props) {
  if (!naturalWidth || !naturalHeight || !displayWidth || !displayHeight) return null;
  const scaleX = displayWidth / naturalWidth;
  const scaleY = displayHeight / naturalHeight;

  return (
    <svg className="absolute left-0 top-0" width={displayWidth} height={displayHeight}>
      {boxes.map((box, index) => (
        <g key={`${box.x}-${box.y}-${index}`}>
          <rect
            x={box.x * scaleX}
            y={box.y * scaleY}
            width={box.w * scaleX}
            height={box.h * scaleY}
            fill="transparent"
            stroke="#10b981"
            strokeWidth="2"
            rx="4"
          />
          <text x={box.x * scaleX + 4} y={box.y * scaleY + 14} fill="#10b981" fontSize="12" fontWeight="bold">
            {Math.round(box.conf * 100)}%
          </text>
        </g>
      ))}
    </svg>
  );
}
