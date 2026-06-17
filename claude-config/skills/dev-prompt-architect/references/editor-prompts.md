# Editor Prompts

Use these patterns for local editor assistants where the best prompt is shorter and scoped to the current file, selection, or symbol.

## Cursor

Cursor prompts should name the local edit target, desired behavior, and boundaries. Avoid long process instructions unless the change spans multiple files.

```text
In <file/component/function>, change <current behavior> so that <desired behavior>.

Constraints:
- Keep the existing public API unless necessary.
- Match the surrounding style.
- Update nearby tests or add focused coverage if this behavior is tested here.
- Do not refactor unrelated code.

Check:
- <local test/lint/build command if known>
```

For multi-file Cursor work:

```text
Inspect the related call sites before editing. Make the smallest coherent change across the affected files, then list what changed and what still needs verification.
```

## GitHub Copilot

Copilot prompts work best as code-local comments or concise chat instructions.

Inline comment shape:

```text
// Implement <behavior>. Handle <edge cases>. Preserve <existing contract>.
```

Chat shape:

```text
Update this function to <goal>. Keep the signature unchanged, follow the existing error-handling pattern, and add/update the nearest tests for <cases>.
```

Avoid asking Copilot to own broad workflows such as branch management, PR shipping, or cross-repo architecture unless it is operating in an agent mode with repository tools.
