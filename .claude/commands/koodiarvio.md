Spawn a background agent to review all Python source files in this project. The agent should:

1. Read every .py and .js file in the project root and subdirectories (skip .venv, __pycache__, .git, node_modules)
2. For each file, look for:
   - Security issues (injection, credential exposure, SSRF, unvalidated input at system boundaries)
   - Bugs or edge cases that could cause incorrect behaviour
   - Missing error handling where external calls can fail
   - Anything surprising or non-obvious that a reviewer should flag
3. Write all findings to SUGGESTIONS_CODE.md in the project root using this format:

```
## filename.py

- line N — description of issue or suggestion
- line N — description of issue or suggestion
```

Only include genuine findings. Skip style preferences and trivial nits.

After spawning the agent, tell the user it is running in the background and that they can ask you to check SUGGESTIONS_CODE.md when ready.
