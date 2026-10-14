/** Remove only the stock opening; preserve factual content, citations and saved text. */
export function withoutDocumentIntro(content: string): string {
  const trimmed = content.trimStart();
  const intros = ["provided", "uploaded", "supplied"].map(
    (word) => `based on the ${word} documents`,
  );
  // Suppress an incomplete stock opening while network batches arrive.
  if (
    trimmed &&
    intros.some((intro) => intro.startsWith(trimmed.toLowerCase()))
  )
    return "";
  const clean = content.replace(
    /^\s*(?:\*\*)?Based on (?:the )?(?:provided|uploaded|supplied) documents(?:\*\*)?\s*[,:\u2014\u2013-]\s*/i,
    "",
  );
  return clean === content || !clean
    ? clean
    : clean[0].toUpperCase() + clean.slice(1);
}
