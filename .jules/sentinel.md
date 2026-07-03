## 2024-07-03 - HTML Injection in PyQt5 QTextEdit
**Vulnerability:**
HTML Injection in PyQt5 UI: The `gui.py` application appended unescaped file names to a `QTextEdit` component via the `append()` method. By default, `QTextEdit.append()` interprets its input as rich text (HTML). If a malicious file name with HTML tags like `<h1>` or `<img>` was loaded, the application parsed and rendered it, which could be abused for UI spoofing or potentially XSS-style injection in the context of the desktop application.

**Learning:**
1. Desktop applications using UI frameworks like PyQt5 that support rich text formatting can be vulnerable to HTML injection if user-provided input (like file names) is rendered without escaping.
2. Directly calling `html.escape()` without wrapping the output in an HTML tag can cause Qt to misinterpret the string as plain text, leading to UI regressions where normal characters like `&` and quotes are incorrectly displayed as HTML entities (`&amp;`).

**Prevention:**
Always escape user input before rendering it in UI components that support rich text. In PyQt5, after using `html.escape()`, wrap the sanitized string in a basic HTML tag (e.g., `<span>`) to ensure Qt parses it correctly as rich text and displays entities properly. I've updated the `log` function in `gui.py` to use `html.escape()` and wrapped the output in a `<span>` tag.
