import { describe, expect, it } from "vitest";
import { actions, getState } from "@/lib/im/store";

describe("resume privacy", () => {
  it("keeps uploaded resume text out of browser storage", () => {
    actions.updateSetup({ highlights: "Private resume project details" });
    expect(getState().setup.highlights).toBe("Private resume project details");
    expect(window.localStorage.getItem("interviewmirror:v1")).not.toContain(
      "Private resume project details",
    );
    actions.updateSetup({ highlights: "" });
  });
});
