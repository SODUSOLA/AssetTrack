# Accessibility

The target is WCAG 2.2 AA. What is checked by machine, and what only a person can check.

## Checked automatically (every run)

- **axe-core in a real browser**, on every page, in light and dark, at 360, 390, 768, 1024, 1280 and
  1440 pixels wide (`frontend/e2e/responsive.spec.ts`): colour contrast, names, roles, labels,
  landmarks, target size.
- **axe on every screen in the unit tests**, and the **contrast of every text pair** in both
  themes (`frontend/src/styles/tokens.test.ts`).
- **No sideways scrolling** at any of those sizes.
- **Keyboard** (`frontend/e2e/keyboard.spec.ts`): the skip link lands in the content; moving to
  another page puts focus on its title; a dialog keeps focus inside, locks the page behind it, closes
  on Escape and gives focus back to the button that opened it; menus open and move with the arrows;
  a form error is attached to its field; every control has a name; the phone drawer behaves the same.
- Colour is never the only signal: statuses, priorities and acknowledgements carry words and icons.
- `prefers-reduced-motion` and `prefers-color-scheme` are respected in the styles (zooming the text to 200% and 400% still needs a person, below).

## Needs a person (not done yet)

Automated tools find roughly a third of real problems. Before go-live, someone should do this once,
with a screen reader (VoiceOver on a Mac; NVDA on Windows) and then with the keyboard alone:

1. **Sign in** with the keyboard. Is the error read out when the password is wrong?
2. **Move around**: Tab through the menu and a page. Is the order sensible? Is the focus always
   visible? Does the skip link work?
3. **Open and close** "Register a device", "Log an event" and "Raise a complaint". Is the dialog's
   title read out? Do you return to the button?
4. **Fill a form wrongly** and submit. Is each error read out and findable?
5. **Read a table** (devices, complaints, a report): are the column names read with each cell?
6. **Confirm and dispute** an acknowledgement. Is the result announced (the notice at the bottom)?
7. **Reports**: read a report's summary and one table; print it.
8. **Phone**: open the menu drawer; use a form with the on-screen keyboard.
9. Zoom the browser to 200% and 400%: is anything cut off or hidden?

Write down anything awkward, even if it is "not a failure". Fix, and add a test where a machine can
catch it again.

## How the screens are built, for the next developer

- Dialogs, menus and tabs use Radix primitives; `Dialog` returns focus to the last control used
  (Radix cannot, because the buttons are not its triggers).
- Every field is a `TextField`, `SelectField` or `TextareaField`: label, hint and error are wired
  together. Do not add a bare `<input>`.
- Page titles are `PageHeader` (an `h1` that receives focus on navigation). One `h1` per page.
- Tables are `DataTable` (a real table, or labelled cards when narrow); never lay out data with divs.
- Change a colour only in `tokens.css`; the contrast test must still pass.
