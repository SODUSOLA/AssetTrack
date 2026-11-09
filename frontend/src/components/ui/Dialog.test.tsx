import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Dialog } from "./Dialog";

function Page({
  removeOpener = false,
  autoFocusField = false,
}: {
  removeOpener?: boolean;
  autoFocusField?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(true);
  return (
    <>
      <h1 id="page-title" tabIndex={-1}>
        Title
      </h1>
      {shown && <button onClick={() => setOpen(true)}>Open it</button>}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next && removeOpener) setShown(false);
        }}
        title="A dialog"
      >
        {autoFocusField ? (
          // The app's own forms focus their first field; the dialog must still hand focus back.
          // eslint-disable-next-line jsx-a11y/no-autofocus
          <input aria-label="A field" autoFocus />
        ) : (
          <button>Inside</button>
        )}
      </Dialog>
    </>
  );
}

describe("dialog focus", () => {
  it("returns to the button that opened it when it closes", async () => {
    render(<Page />);
    const opener = screen.getByRole("button", { name: "Open it" });
    await userEvent.click(opener);
    expect(await screen.findByRole("dialog")).toBeVisible();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("still returns to the opener when a field inside took focus first", async () => {
    render(<Page autoFocusField />);
    const opener = screen.getByRole("button", { name: "Open it" });
    await userEvent.click(opener);
    expect(await screen.findByLabelText("A field")).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(opener).toHaveFocus();
  });

  it("goes to the top of the page when the opener is gone", async () => {
    render(<Page removeOpener />);
    await userEvent.click(screen.getByRole("button", { name: "Open it" }));
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("heading", { name: "Title" })).toHaveFocus();
  });
});
