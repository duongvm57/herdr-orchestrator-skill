# Consumer protocol

Candidate review must bind the exact committed candidate, never the mutable
worktree. For the bounded OCR evaluation, the evaluator may create
`candidate-change.txt`, `evaluation-evidence.json`, and files under `evidence/`.
