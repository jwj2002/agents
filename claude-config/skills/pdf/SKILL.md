---
name: pdf
version: 1.0
description: Convert a markdown file to PDF using md-to-pdf
argument-hint: <filepath.md>
---

# Markdown to PDF Converter

Convert a markdown file to a PDF in the same directory.

## Instructions

1. If no filepath argument was provided, ask the user which markdown file to convert using AskUserQuestion.

2. Resolve the filepath to an absolute path. If relative, resolve from the current working directory.

3. Verify the file exists and is a `.md` file using the Read tool (read just the first few lines).

4. Run the conversion:
   ```
   md-to-pdf "<absolute-path-to-file>"
   ```

5. The output PDF will be created in the same directory with the same name but `.pdf` extension.

6. Confirm to the user:
   - Input file path
   - Output PDF path
   - Whether it succeeded or failed

## Error Handling

- If `md-to-pdf` is not installed, tell the user to run: `npm i -g md-to-pdf`
- If the file doesn't exist, tell the user
- If the file is not a `.md` file, tell the user
