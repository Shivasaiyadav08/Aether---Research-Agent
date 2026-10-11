export const workflowSteps = [
  {
    id: "retrieve",
    title: "Retrieve",
    subtitle: "Your local knowledge",
    x: 230,
    y: 30,
    purpose:
      "Find the document chunks whose meaning is closest to your question.",
    input: "Question, recent user context, workspace ID, retrieval count.",
    output: "Page-aware chunks with D1, D2… identifiers and cosine similarity.",
    code: "async def retrieve(state):\n    results = await asyncio.to_thread(\n        vectors.retrieve, state['workspace_id'],\n        query, state['settings']['retrieval_count']\n    )\n    return {'retrieved': results}",
  },
  {
    id: "grade",
    title: "Grade relevance",
    subtitle: "Gemini · structured output",
    x: 230,
    y: 140,
    purpose:
      "Ask an LLM whether each retrieved chunk helps answer the question. Similarity alone is not enough.",
    input: "Question, each retrieved chunk, and your selected relevance cutoff.",
    output:
      "A Pydantic-validated score from 0 to 1, a reason, and acceptance when the score meets your cutoff (50% by default).",
    code: "result = await structured_call(\n    model, RelevanceGrade, instruction, data\n)\naccepted = result.score >= threshold",
  },
  {
    id: "assess",
    title: "Assess evidence",
    subtitle: "Is there enough to answer?",
    x: 230,
    y: 250,
    purpose:
      "Check whether the accepted chunks cover all important parts of the question. This decision selects the next graph edge.",
    input: "Question, history, and accepted document evidence.",
    output: "EvidenceAssessment: sufficient, reason, and missing information.",
    code: "def evidence_route(state):\n    if state['assessment']['sufficient']:\n        return 'generate'\n    return 'rewrite'",
  },
  {
    id: "rewrite",
    title: "Rewrite query",
    subtitle: "Focus on evidence gaps",
    x: 480,
    y: 370,
    purpose:
      "Turn the question and identified gaps into a focused, standalone web search query.",
    input: "Question, chat context, missing information.",
    output:
      "RewrittenQuery.query, validated with Pydantic. On failure, the original question.",
    code: "result = await structured_call(\n    model, RewrittenQuery, instruction, data\n)\nreturn {'rewritten_query': result.query}",
  },
  {
    id: "web_search",
    title: "Search the web",
    subtitle: "Tavily · external evidence",
    x: 480,
    y: 480,
    purpose:
      "Search the web only when documents are insufficient. URLs are checked and duplicate URLs removed.",
    input: "Rewritten question and backend-only Tavily key.",
    output:
      "Web snippets identified as W1, W2… or a clear warning if search is unavailable.",
    code: "sources = await search_web(\n    state['rewritten_query']\n)\nreturn {'sources': state['sources'] + sources}",
  },
  {
    id: "generate",
    title: "Generate answer",
    subtitle: "Grounded · streaming Markdown",
    x: 230,
    y: 600,
    purpose:
      "Use Gemini to answer using accepted evidence. Real model tokens are sent to the browser while they arrive.",
    input: "Question, bounded history, evidence, and any correction feedback.",
    output:
      "Provisional Markdown answer with exact document and web citation IDs.",
    code: "async for chunk in llm.astream(messages):\n    text = message_text(chunk)\n    emit('token', text=text)\n    parts.append(text)\nreturn {'answer': ''.join(parts)}",
  },
  {
    id: "validate",
    title: "Validate",
    subtitle: "Citations + grounding",
    x: 230,
    y: 710,
    purpose:
      "Check that citation IDs exist and ask Gemini to check claim support. API chats retain both checks. Failed validation retries only within the configured limit.",
    input: "Generated answer and its evidence.",
    output: "Valid flag and correction feedback; retry or finalize.",
    code: "errors = citation_errors(answer, sources)\n# Optional LLM grounding check follows.\nif not valid and attempts <= max_retries:\n    return 'generate'\nreturn 'finalize'",
  },
  {
    id: "finalize",
    title: "Final response",
    subtitle: "Save answer and cited sources",
    x: 230,
    y: 820,
    purpose:
      "Keep the validated answer and only its cited sources. Replace an exhausted invalid draft with a clear abstention.",
    input: "Answer, validation result, sources, warnings.",
    output:
      "Final SSE event; the API saves the assistant message and workflow trace in SQLite.",
    code: "emit('final', answer=answer,\n     sources=cited, warnings=warnings,\n     valid=state['valid'])",
  },
];

export const workflowConnections = [
  ["retrieve", "grade", ""],
  ["grade", "assess", ""],
  ["assess", "generate", "Sufficient"],
  ["assess", "rewrite", "Insufficient"],
  ["rewrite", "web_search", ""],
  ["web_search", "generate", ""],
  ["generate", "validate", ""],
  ["validate", "generate", "Retry within limit"],
  ["validate", "finalize", ""],
];
