export const generatedModelIds = ['uniad-tiny', 'uniad-base', 'vad', 'tcp', 'admlp'] as const;
export function supportsGeneratedScene(id: string): boolean {
  return generatedModelIds.some(value => value === id);
}
