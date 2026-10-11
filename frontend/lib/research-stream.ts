"use client";

import { API_URL, api, readSSE } from "./api";
import { useResearch } from "../stores/research";
import type { Conversation, Message } from "../types";

// Owned by the signed-in browser session, independent of mounted views/pages.
let activeRun: { controller: AbortController; sequence: number } | null = null;
let sequence = 0;

useResearch.subscribe((state, previous) => {
  if (state.sessionId === previous.sessionId) return;
  sequence += 1;
  activeRun?.controller.abort();
  activeRun = null;
});

export function setResearchSession(sessionId: string) {
  if (useResearch.getState().sessionId === sessionId) return;
  useResearch.setState({ ...useResearch.getInitialState(), sessionId }, true);
}

export function stopResearch() {
  activeRun?.controller.abort();
}

export async function sendResearch(question: string, regenerate = false) {
  const state = useResearch.getState();
  if (
    activeRun ||
    state.streaming ||
    !state.sessionId ||
    !state.workspaceId ||
    !state.selectedModel ||
    !question.trim()
  )
    return;
  const oldMessages = state.messages;
  const lastUser = oldMessages.findLastIndex(
    (message) => message.role === "user",
  );
  const visible = regenerate
    ? oldMessages.slice(0, lastUser + 1)
    : [
        ...oldMessages,
        {
          id: crypto.randomUUID(),
          role: "user" as const,
          content: question.trim(),
          sources: [],
        },
      ];
  state.update({
    streaming: true,
    draft: "",
    error: "",
    events: [],
    warnings: [],
    messages: visible,
    elapsedMs: 0,
    modelNotice: "",
  });
  const run = { controller: new AbortController(), sequence: ++sequence };
  activeRun = run;
  const isCurrent = () =>
    sequence === run.sequence &&
    useResearch.getState().sessionId === state.sessionId;
  let receivedStart = false;
  let receivedFinal = false;
  try {
    const response = await fetch(`${API_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: run.controller.signal,
      body: JSON.stringify({
        workspace_id: state.workspaceId,
        conversation_id: state.conversationId,
        question: question.trim(),
        regenerate,
        model: state.selectedModel,
        relevance_threshold: state.relevanceThreshold,
      }),
    });
    if (!response.ok) {
      const body = await response.json();
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : `Request failed (${response.status}).`,
      );
    }
    await readSSE(response, (event) => {
      if (!isCurrent()) return;
      if (event.type === "start") receivedStart = true;
      if (event.type === "final") receivedFinal = true;
      useResearch.getState().receiveEvent(event);
    });
  } catch (error) {
    if (!isCurrent()) return;
    const stopped = error instanceof Error && error.name === "AbortError";
    useResearch.getState().update({
      error: stopped
        ? "Research stopped. The unfinished answer was not saved."
        : error instanceof Error
          ? error.message
          : "Could not complete the request.",
      draft: "",
      ...(!receivedStart || (regenerate && !receivedFinal)
        ? { messages: oldMessages }
        : {}),
    });
  } finally {
    if (activeRun === run) activeRun = null;
    if (isCurrent()) {
      const completedConversationId = useResearch.getState().conversationId;
      useResearch.getState().update({ streaming: false });
      if (receivedStart) {
        try {
          const conversations = await api<Conversation[]>(
            `/workspaces/${state.workspaceId}/conversations`,
          );
          if (isCurrent()) {
            const chat = await api<{ messages: Message[] }>(
              `/workspaces/${state.workspaceId}/conversations/${completedConversationId}`,
            );
            const current = useResearch.getState();
            if (isCurrent() && current.workspaceId === state.workspaceId) {
              current.update({ conversations });
              if (current.conversationId === completedConversationId)
                current.update({ messages: chat.messages });
            }
          }
        } catch {
          /* Keep already received text if a follow-up refresh fails. */
        }
      }
    }
  }
}
