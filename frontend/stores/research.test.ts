import { afterEach, expect, it } from "vitest";
import { useResearch } from "./research";
afterEach(() => useResearch.setState(useResearch.getInitialState(), true));
it("keeps the relevance choice for new chats and resets it with the session", () => {
  expect(useResearch.getState().relevanceThreshold).toBe(0.5);
  useResearch.getState().update({ relevanceThreshold: 0.75 });
  useResearch.getState().newChat();
  expect(useResearch.getState().relevanceThreshold).toBe(0.75);
  useResearch.setState(useResearch.getInitialState(), true);
  expect(useResearch.getState().relevanceThreshold).toBe(0.5);
});
it("shows a real fallback and changes the chosen model", () => {
  useResearch.getState().receiveEvent({
    type: "model_fallback",
    model: "gemini-next-flash",
    message: "First model unavailable. Switching to another free model.",
  });
  expect(useResearch.getState().selectedModel).toBe("gemini-next-flash");
  expect(useResearch.getState().modelNotice).toContain("unavailable");
  expect(useResearch.getState().events[0].type).toBe("model_fallback");
});
it("marks the failed Gemini model unavailable while retaining alternatives", () => {
  const model = {
    name: "Gemini",
    context_length: 1000000,
    pricing: { prompt: "0", completion: "0" },
    supported_parameters: ["structured_outputs"],
    available: true,
  };
  useResearch.getState().update({
    models: [
      { ...model, id: "gemini-first" },
      { ...model, id: "gemini-next" },
    ],
  });
  useResearch.getState().receiveEvent({
    type: "model_fallback",
    failed_model: "gemini-first",
    model: "gemini-next",
    message: "Quota reached. Switching to the next eligible model.",
  });
  expect(useResearch.getState().models[0].available).toBe(false);
  expect(useResearch.getState().models[1].available).toBe(true);
  expect(useResearch.getState().selectedModel).toBe("gemini-next");
});
it("replaces provisional text after a generation or provider retry", () => {
  useResearch
    .getState()
    .receiveEvent({ type: "token", text: "An unfinished draft" });
  useResearch.getState().receiveEvent({ type: "answer_reset" });
  expect(useResearch.getState().draft).toBe("");
  useResearch
    .getState()
    .receiveEvent({ type: "token", text: "A cited replacement [D1]." });
  expect(useResearch.getState().draft).toBe("A cited replacement [D1].");
});
it("keeps a model selectable after an incomplete response without a provider cooldown", () => {
  useResearch.getState().update({
    models: [
      {
        id: "gemini-first",
        name: "Gemini",
        context_length: 1000,
        pricing: {},
        supported_parameters: [],
        available: true,
      },
    ],
  });
  useResearch.getState().receiveEvent({
    type: "model_fallback",
    failed_model: "gemini-first",
    model: null,
    available: true,
    retry_after_seconds: 0,
    message: "Empty answer. No eligible fallback remains.",
  });
  expect(useResearch.getState().models[0].available).toBe(true);
  expect(useResearch.getState().models[0].retry_at).toBeUndefined();
});
it("clears private data when resetting the signed-in session", () => {
  useResearch.getState().update({
    sessionId: "user_alice",
    messages: [
      {
        id: "private",
        role: "user",
        content: "Private research",
        sources: [],
      },
    ],
    workspaceId: "private-workspace",
  });
  useResearch.setState(useResearch.getInitialState(), true);
  expect(useResearch.getState().messages).toEqual([]);
  expect(useResearch.getState().sessionId).toBe("");
  expect(useResearch.getState().workspaceId).toBe("");
});
