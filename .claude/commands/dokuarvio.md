Spawn a background agent to review all documentation files in this project: README.md, PODE.md, USECASES.md, POLICY.example.md, and any other .md files in the project root.

The agent should check for:
1. Inconsistencies between files — does README say something that contradicts PODE.md or POLICY.example.md?
2. Claims that are no longer accurate given the current codebase
3. Sections that are unclear, incomplete, or assume knowledge the reader may not have
4. Anything missing that a first-time reader would need to understand the project

Return all findings as the final response in this format:

```
## filename.md

- Section name — specific suggestion or inconsistency
```

Only include genuine findings. Do not write any files.

After spawning the agent, tell the user it is running in the background. When the agent completes, present its findings directly to the user — do not ask the user to check a file.
