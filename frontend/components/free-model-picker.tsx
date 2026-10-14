"use client";
import { useEffect, useState } from "react";
import { RefreshCw, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useResearch } from "@/stores/research";
import type { Model } from "@/types";
import { modelAllowed } from "@/lib/model-policy";

export function FreeModelPicker() {
  const {
    models,
    selectedModel,
    actualModel,
    automaticFallback,
    streaming,
    modelNotice,
    update,
  } = useResearch();
  const [loading, setLoading] = useState(false);
  const eligibleModels = models.filter((model) => modelAllowed(model.id));
  useEffect(() => {
    if (selectedModel && !modelAllowed(selectedModel)) {
      update({
        selectedModel:
          models.find(
            (model) => modelAllowed(model.id) && model.available !== false,
          )?.id || "auto",
        modelNotice:
          "The previously selected model was removed. Choose a remaining free model.",
      });
    }
  }, [models, selectedModel, update]);
  const hasCooldowns = models.some((model) => model.available === false);
  useEffect(() => {
    if (!hasCooldowns) return;
    const timer = window.setInterval(
      () => useResearch.getState().tickModelCooldowns(),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [hasCooldowns]);
  async function refresh() {
    const sessionId = useResearch.getState().sessionId;
    setLoading(true);
    try {
      const models = (await api<Model[]>("/models?refresh=true")).filter(
        (model) => modelAllowed(model.id),
      );
      if (useResearch.getState().sessionId !== sessionId) return;
      update({
        models,
        selectedModel:
          selectedModel === "auto"
            ? "auto"
            : models.some(
                  (model) =>
                    model.id === selectedModel && model.available !== false,
                )
              ? selectedModel
              : models.find((model) => model.available !== false)?.id || "",
        modelNotice: "",
      });
    } catch (error) {
      if (useResearch.getState().sessionId !== sessionId) return;
      update({
        modelNotice:
          error instanceof Error
            ? error.message
            : "Could not load free-tier Gemini models.",
      });
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="free-model-picker">
      <Sparkles size={13} aria-hidden="true" />
      <select
        aria-label="Free-tier Gemini research model"
        title="Models eligible for Google's free tier. Actual quota is checked on use; your Google project's billing tier controls charges."
        value={selectedModel}
        disabled={streaming || loading || !eligibleModels.length}
        onChange={(event) =>
          update({
            selectedModel: event.target.value,
            automaticFallback: event.target.value === "auto",
            modelNotice: "",
          })
        }
      >
        <option value="auto">Automatic selection</option>
        {!selectedModel && (
          <option value="">No eligible Gemini model ready</option>
        )}
        {selectedModel &&
          modelAllowed(selectedModel) &&
          !models.some((model) => model.id === selectedModel) && (
            <option value={selectedModel}>
              {selectedModel} · Gemini fallback
            </option>
          )}
        {eligibleModels.map((model) => (
          <option
            key={model.id}
            value={model.id}
            disabled={model.available === false}
          >
            {model.name} ·{" "}
            {model.available === false
              ? `Cooldown · retry in ${model.retry_after_seconds ?? 60}s`
              : "Free tier"}
          </option>
        ))}
      </select>
      <label
        className="model-fallback-control"
        title="Allow another verified free-tier model when the selected model fails"
      >
        <input
          type="checkbox"
          checked={automaticFallback}
          disabled={streaming || selectedModel === "auto"}
          onChange={(event) =>
            update({ automaticFallback: event.target.checked })
          }
        />
        <span>Auto fallback</span>
      </label>
      {actualModel && actualModel !== selectedModel && (
        <span
          className="actual-model-status"
          role="status"
          title={`Actual model: ${actualModel}`}
        >
          Using {actualModel}
        </span>
      )}
      <button
        type="button"
        aria-label="Refresh free models"
        title="Refresh free models"
        disabled={streaming || loading}
        onClick={() => void refresh()}
      >
        <RefreshCw size={12} className={loading ? "spin" : ""} />
      </button>
      {modelNotice && (
        <span className="model-notice" role="status">
          {modelNotice}
        </span>
      )}
    </div>
  );
}
