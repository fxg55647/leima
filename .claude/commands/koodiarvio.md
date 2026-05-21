Spawn a background agent to review all Python and JavaScript source files in this project. The agent should:

1. Read every .py and .js file in the project root and subdirectories (skip .venv, __pycache__, .git, node_modules)
2. For each file, look for:
   - Security issues (injection, credential exposure, SSRF, unvalidated input at system boundaries)
   - Bugs or edge cases that could cause incorrect behaviour
   - Missing error handling where external calls can fail
   - Anything surprising or non-obvious that a reviewer should flag
3. Return all findings as the final response in this format:

```
## filename.py

- line N — description of issue or suggestion
- line N — description of issue or suggestion
```

Only include genuine findings. Skip style preferences and trivial nits. Do not write any files.

After spawning the agent, tell the user it is running in the background. When the agent completes, present its findings directly to the user — do not ask the user to check a file.
