export function sanitizeText(input: string, max = 100): string {
  const stripped = input.replace(/[<>\\{}$]/g, '').trim();
  return stripped.slice(0, max);
}
