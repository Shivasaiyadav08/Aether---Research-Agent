"use client";

import { sendResearch, stopResearch } from "../lib/research-stream";

export function useChat() {
  return { send: sendResearch, stop: stopResearch };
}
