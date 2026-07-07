import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToastContainer } from "./ToastContainer";

describe("ToastContainer", () => {
  it("renders nothing when there are no toasts", () => {
    const { container } = render(<ToastContainer toasts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders each toast's message", () => {
    render(
      <ToastContainer
        toasts={[
          { id: "1", message: "Automation completed.", kind: "success" },
          { id: "2", message: "Task failed.", kind: "error" },
        ]}
      />
    );

    expect(screen.getByText("Automation completed.")).toBeInTheDocument();
    expect(screen.getByText("Task failed.")).toBeInTheDocument();
  });
});
