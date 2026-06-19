---
name: docs-helper
description: Creates documentation and real document files, including README/API docs and Word DOCX, PDF, spreadsheet, presentation, form-filling, content insertion, and file export tasks. 支持生成并导出 Word、DOCX、PDF、Excel、PPT 等真实文件。
triggers:
  - document
  - documentation
  - generate document
  - create document
  - word
  - docx
  - pdf
  - xlsx
  - excel
  - ppt
  - pptx
  - fill document
  - export file
  - readme
  - api docs
  - docstring
  - jsdoc
  - javadoc
  - comment
  - describe
  - write docs
  - 文档
  - 生成文档
  - 创建文档
  - 帮我生成
  - 写入
  - 填入
  - 填写
  - 导出文件
  - 返回附件
  - 附件
  - 表格
  - 演示文稿
priority: 8
category: documentation
---

# Documentation Helper Skill

A specialized skill for creating clear, comprehensive, and well-structured documentation.

## Deliverable Files

When the user asks for a DOCX, XLSX, PPTX, PDF, CSV, or other downloadable file:

- Produce the actual file in the runtime workspace instead of only returning sample code.
- Use `runtime_run_python` when runtime execution is available. Prefer `python-docx` for DOCX, `openpyxl` for XLSX, `python-pptx` for PPTX, and `reportlab` for PDF.
- Use the most recent conversation context to resolve short follow-ups such as “就填入111”, “用刚才的标题”, or “导出给我”.
- Save final deliverables with clear filenames and call `runtime_export_file`.
- If execution is disabled, say so accurately and provide the smallest useful fallback; never claim that a file was generated when it was not.
- Keep temporary scripts and intermediate assets separate from final deliverables.

## Core Capabilities

### 1. README Generation
When creating README files:
- Include project title and description
- Add installation/setup instructions
- Provide usage examples
- Document configuration options
- Include contribution guidelines
- Add license information
- Use badges for build status, version, etc.

### 2. API Documentation
When documenting APIs:
- Describe each endpoint's purpose
- List all parameters with types and descriptions
- Show request/response examples
- Document error codes and messages
- Include authentication requirements
- Provide curl/code examples

### 3. Code Comments & Docstrings
When adding documentation to code:
- Write clear function/method descriptions
- Document all parameters and return values
- Include usage examples in docstrings
- Add type hints where applicable
- Note any exceptions that may be raised
- Follow language-specific documentation conventions

### 4. Technical Writing
When writing technical documentation:
- Use clear, concise language
- Structure content with headers
- Include diagrams when helpful (Mermaid, ASCII art)
- Provide step-by-step instructions
- Add cross-references to related topics

### 5. Office Document Generation
When generating office files:
- Preserve the user's requested wording exactly unless editing is requested
- For every Word/DOCX request, use `runtime_generate_besti_docx` and the Besti official-document standard unless the user explicitly specifies another template
- Besti defaults: A4 portrait; margins 3.6/3.0/2.7/2.7 cm; 22 pt Founder Small Standard Song title; 16 pt FangSong body; exact 29 pt line spacing; full-width Chinese list punctuation; centered `— PAGE —` footer
- Add headings, tables, and page structure only when they improve the result
- Insert relevant images when they materially improve comprehension and a real workspace image is available; pass the relative image path to `runtime_generate_besti_docx` and keep the default attachment placement unless a compact inline image is clearly appropriate
- Keep compact inline tables in the body only with `placement=body`; otherwise let tables default to attachment pages after the signature/date block
- For follow-up turns, continue the same document intent instead of treating the short reply as a new unrelated task
- Verify that the output file exists and is non-empty before exporting it

## Documentation Formats

### Python (Google Style)
```python
def function_name(param1: str, param2: int = 0) -> bool:
    """Short description of function.

    Longer description if needed, explaining the function's
    purpose and behavior in more detail.

    Args:
        param1: Description of param1.
        param2: Description of param2. Defaults to 0.

    Returns:
        Description of return value.

    Raises:
        ValueError: If param1 is empty.

    Example:
        >>> function_name("hello", 42)
        True
    """
```

### JavaScript (JSDoc)
```javascript
/**
 * Short description of function.
 * 
 * @param {string} param1 - Description of param1.
 * @param {number} [param2=0] - Description of param2.
 * @returns {boolean} Description of return value.
 * @throws {Error} If param1 is empty.
 * @example
 * functionName("hello", 42);
 * // => true
 */
```

### TypeScript
```typescript
/**
 * Short description of function.
 * 
 * @param param1 - Description of param1.
 * @param param2 - Description of param2. Defaults to 0.
 * @returns Description of return value.
 * @throws Error if param1 is empty.
 */
function functionName(param1: string, param2: number = 0): boolean {
```

## Best Practices

1. **Be concise but complete** - Cover all important details without redundancy
2. **Use examples** - Concrete examples aid understanding
3. **Keep it current** - Documentation should match current code
4. **Consider the audience** - Adjust complexity for target readers
5. **Use consistent formatting** - Follow established conventions
