# Role runtime binding

A role runtime binding is the bounded native context for one already-selected
harness role. It carries runtime facts only: the exact Herdr executable,
socket endpoint, pane identity, canonical helper, project root, and SLP role.
It does not select a harness, change a recipe, confer Assignment authority,
infer topology, or retain lifecycle state.

The Launcher builds one fresh JSON document for itself before a guarded helper
call and for each launched role from active native session facts. Read each pane ID from
native Herdr JSON; do not guess paths, socket endpoints, pane IDs, or home
directories, and do not persist this document in the consumer project. Its
exact version-2 shape is:

```json
{
  "schema_version": 2,
  "role": "lead",
  "herdr_executable": "/absolute/path/to/herdr",
  "herdr_socket_endpoint": "/absolute/path/to/herdr.sock",
  "herdr_pane_id": "w1:p1",
  "helper": "/absolute/path/to/herdr_orchestrator.py",
  "project_root": "/absolute/path/to/project"
}
```

The helper rejects unknown fields, noncanonical paths, missing
executable/helper/project, invalid pane IDs, and unknown roles. A runtime
binding never carries a harness profile, HOME, credential, authentication, or
provider setup. Normal production launch uses the user's selected harness
environment and authenticated profile.

After the configured recipe has already selected its harness, render that
adapter's projection into a temporary prompt fragment:

```text
python3 <canonical-helper> render-runtime-binding --binding <binding.json> \
  --kind <configured-kind> --output <runtime-projection.md>
```

Include the returned fragment in the initial role prompt and use its exact
helper command form for every guarded helper call. That form supplies the
binding's `HERDR_ORCHESTRATOR_PANE_ID`; the helper compares it to native
`HERDR_PANE_ID`. The pane-start environment is not this binding and must not
invent a child pane ID. A kind with no verified projection fails closed; do not
borrow another harness's configuration, command syntax, or environment
assumptions.

For a Peer or Reviewer pane, render a separate launch projection from the
bound Lead binding before native pane creation:

```text
python3 <canonical-helper> render-runtime-binding-pane --binding <binding.json> \
  --kind <configured-kind> --role peer --output <pane-binding.json>
```

Use `source_pane_id` from that output as the literal native split target and
every `pane_environment` entry as one literal `--env NAME=VALUE` argument,
without filling values from the ambient shell or another adapter. The generic
projection supplies only project, helper, and target-role context; an adapter
may add only verified process-start facts. It must not supply Herdr-managed
environment values such as the socket, pane, tab, or workspace identity. After
Herdr returns the new pane ID, derive the fresh Peer binding with that returned
exact ID before rendering its role prompt.
