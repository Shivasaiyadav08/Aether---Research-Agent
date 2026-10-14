import { create } from "zustand";
import {
  advanceModelCooldowns,
  setModelCooldowns,
} from "../lib/model-availability";
import type {
  Conversation,
  Health,
  Model,
  Message,
  Source,
  View,
  WorkflowEvent,
  Workspace,
} from "@/types";

type ResearchState = {
  view: View;
  sidebarCollapsed: boolean;
  intelligenceOpen: boolean;
  workspaces: Workspace[];
  workspaceId: string;
  conversations: Conversation[];
  conversationId: string | null;
  messages: Message[];
  events: WorkflowEvent[];
  streaming: boolean;
  uploading: boolean;
  draft: string;
  health: Health | null;
  sessionId: string;
  models: Model[];
  selectedModel: string;
  actualModel: string;
  automaticFallback: boolean;
  runId: string | null;
  relevanceThreshold: number;
  modelNotice: string;
  error: string;
  warnings: string[];
  selectedSource: Source | null;
  elapsedMs: number;
  update: (
    patch: Partial<Omit<ResearchState, "update" | "receiveEvent" | "newChat">>,
  ) => void;
  newChat: () => void;
  receiveEvent: (event: WorkflowEvent) => void;
  tickModelCooldowns: () => void;
};

export const useResearch = create<ResearchState>((set) => ({
  view: "research",
  sidebarCollapsed: false,
  intelligenceOpen: true,
  workspaces: [],
  workspaceId: "",
  conversations: [],
  conversationId: null,
  messages: [],
  events: [],
  streaming: false,
  uploading: false,
  draft: "",
  health: null,
  sessionId: "",
  models: [],
  selectedModel: "",
  actualModel: "",
  automaticFallback: true,
  runId: null,
  relevanceThreshold: 0.5,
  modelNotice: "",
  error: "",
  warnings: [],
  selectedSource: null,
  elapsedMs: 0,
  update: (patch) =>
    set(
      patch.models
        ? { ...patch, models: setModelCooldowns(patch.models) }
        : patch,
    ),
  tickModelCooldowns: () =>
    set((state) => ({ models: advanceModelCooldowns(state.models) })),
  newChat: () =>
    set({
      view: "research",
      conversationId: null,
      runId: null,
      actualModel: "",
      messages: [],
      events: [],
      draft: "",
      error: "",
      warnings: [],
      elapsedMs: 0,
    }),
  receiveEvent: (event) =>
    set((state) => {
      const patch: Partial<ResearchState> = {
        elapsedMs: event.elapsed_ms ?? state.elapsedMs,
      };
      if (event.type === "model_fallback")
        patch.modelNotice = String(event.message);
      if (event.type === "model_fallback" && event.failed_model)
        patch.models = state.models.map((model) =>
          model.id === event.failed_model
            ? setModelCooldowns([
                {
                  ...model,
                  available: event.available ?? false,
                  retry_after_seconds: event.retry_after_seconds ?? 60,
                },
              ])[0]
            : model,
        );
      if (
        (event.type === "model_selected" || event.type === "model_fallback") &&
        event.model
      )
        patch.actualModel = event.model;
      if (event.type !== "token") patch.events = [...state.events, event];
      if (event.type === "start") {
        patch.conversationId = event.conversation_id!;
        patch.runId = event.run_id ?? null;
        patch.error = "";
        patch.draft = "";
      }
      if (event.type === "answer_reset") patch.draft = "";
      if (event.type === "token") patch.draft = state.draft + event.text;
      if (event.type === "final") {
        patch.draft = "";
        patch.warnings = event.warnings ?? [];
        if (event.message && typeof event.message !== "string")
          patch.messages = [
            ...state.messages.filter(
              (message) => message.id !== (event.message as Message).id,
            ),
            event.message,
          ];
      }
      if (event.type === "error") {
        patch.error = String(event.message);
        patch.draft = "";
      }
      if (event.type === "done")
        patch.elapsedMs = event.duration_ms ?? state.elapsedMs;
      return patch;
    }),
}));
