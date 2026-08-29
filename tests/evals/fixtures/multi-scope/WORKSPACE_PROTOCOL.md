# Consumer protocol

`src/alpha.txt` and `src/beta.txt` are independent writer scopes. `src` owns
their shared parent boundary. The evaluator may only create `evaluation-output.json`.
