import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "node_modules*",
      "dist",
      "coverage",
      "src/api/schema.d.ts",
      "playwright-report",
      "test-results",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{js,mjs}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Focusing the first field when a dialog (or the sign-in page) opens is deliberate. The rule
      // still guards plain DOM elements, where autoFocus would steal focus on page load.
      "jsx-a11y/no-autofocus": ["error", { ignoreNonDOM: true }],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // Text that came from users is only ever rendered as text, never as markup.
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "Never render data as HTML. Render it as text.",
        },
      ],
      "no-restricted-properties": [
        "error",
        { property: "innerHTML", message: "Never write HTML from data." },
        { property: "outerHTML", message: "Never write HTML from data." },
        { property: "insertAdjacentHTML", message: "Never write HTML from data." },
      ],
    },
  },
);
