export function modelAllowed(id: string): boolean {
  return !/^gemini-3\.(6|8)-flash(?:$|-)/.test(id.replace(/^models\//, ""));
}
