import type { Model } from "../types";

export function setModelCooldowns(models: Model[], now = Date.now()): Model[] {
  return models.map((model) => ({
    ...model,
    retry_at:
      model.available === false
        ? now + Math.max(1, model.retry_after_seconds ?? 60) * 1000
        : undefined,
  }));
}

export function advanceModelCooldowns(
  models: Model[],
  now = Date.now(),
): Model[] {
  return models.map((model) => {
    if (model.available !== false || model.retry_at === undefined) return model;
    const seconds = Math.max(0, Math.ceil((model.retry_at - now) / 1000));
    return {
      ...model,
      available: seconds === 0,
      retry_after_seconds: seconds,
      retry_at: seconds === 0 ? undefined : model.retry_at,
    };
  });
}
