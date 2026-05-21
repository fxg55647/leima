Spawn an agent to review all documentation files in this project: README.md, PODE.md, USECASES.md, POLICY.md, and any other .md files in the project root.

The agent should check for:
1. Inconsistencies between files — does README say something that contradicts PODE.md or POLICY.md?
2. Claims that are no longer accurate given the current codebase
3. Sections that are unclear, incomplete, or assume knowledge the reader may not have
4. Anything missing that a first-time reader would need to understand the project

Write findings to SUGGESTIONS_DOCS.md using this format:

```
## filename.md

- Section name — specific suggestion or inconsistency
```

After the agent completes, read SUGGESTIONS_DOCS.md and present the key findings directly to the user as a short list of concrete change suggestions.
