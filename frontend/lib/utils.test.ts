import { expect, it } from "vitest";
import { formatModelPrice } from "./utils";

it("does not display a negative router sentinel as a negative charge", () => {
  expect(formatModelPrice("-1", "input")).toBe("Variable pricing");
});

it("does not claim missing or nonnumeric pricing is free", () => {
  expect(formatModelPrice(undefined, "output")).toBe("Variable pricing");
  expect(formatModelPrice("unknown", "input")).toBe("Variable pricing");
});

it("converts real per-token catalog pricing to per-million prices", () => {
  expect(formatModelPrice("0.000002", "input")).toBe("$2.00 / M input");
  expect(formatModelPrice("0", "output")).toBe("$0.00 / M output");
});
