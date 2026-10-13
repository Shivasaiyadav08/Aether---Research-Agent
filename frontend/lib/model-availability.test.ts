import { expect, it } from "vitest";
import { advanceModelCooldowns, setModelCooldowns } from "./model-availability";

const model = {
  id: "gemini-test",
  name: "Gemini Test",
  context_length: 1000,
  pricing: { prompt: "0", completion: "0" },
  supported_parameters: [],
};

it("counts down a cooldown and makes the model selectable when it expires", () => {
  const models = setModelCooldowns(
    [{ ...model, available: false, retry_after_seconds: 30 }],
    1000,
  );
  expect(advanceModelCooldowns(models, 11000)[0].retry_after_seconds).toBe(20);
  expect(advanceModelCooldowns(models, 30999)[0].available).toBe(false);
  expect(advanceModelCooldowns(models, 31000)[0]).toMatchObject({
    available: true,
    retry_after_seconds: 0,
    retry_at: undefined,
  });
});

it("does not disable models that had a request failure without a cooldown", () => {
  const models = setModelCooldowns(
    [{ ...model, available: true, retry_after_seconds: 0 }],
    1000,
  );
  expect(advanceModelCooldowns(models, 2000)[0].available).toBe(true);
});
