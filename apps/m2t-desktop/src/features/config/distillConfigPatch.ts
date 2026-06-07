/** Strip masked Tavily key before PATCH /api/config. */
export function tavilyApiKeyForPatch(value: string | null | undefined): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed || trimmed === '***') {
    return undefined;
  }
  return trimmed;
}
