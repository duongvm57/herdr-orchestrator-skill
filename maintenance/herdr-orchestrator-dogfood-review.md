# Dogfood Review — `herdr-orchestrator` khi chạy task `dexport`

## Phạm vi review

Tài liệu này **chỉ tập trung review dogfood của `herdr-orchestrator`**, không review chất lượng implementation của repo `dexport`.

Nguồn quan sát là toàn bộ các Codex session sinh ra trong lần chạy task, gồm Launcher, Lead, Supervisor, Architect, Engineer và Reviewer v1→v7.

Run kéo dài khoảng **3 giờ 26 phút ở Lead**, tạo **11 child agents**, trong đó có **7 fresh Reviewer xhigh**. Riêng Lead thực hiện khoảng **448 tool calls**, với **60 lần `herdr agent wait` timeout**.

---

# Kết luận tổng quan

| Severity | Dogfood issue | Kết luận |
|---|---|---|
| **HIGH** | Lead bị drift sang runtime identity `peer` nhưng vẫn tiếp tục spawn Reviewer | **Bug thật, role boundary chưa được enforce** |
| **HIGH** | Reviewer outcome contract tự mâu thuẫn `FINDINGS/APPROVE` vs `REOPEN_REQUEST/COMPLETE` | **Bug thật, đã gây validation failure** |
| **HIGH** | Config có `engineer-pi` nhưng Engineer thực tế chạy Codex | **Routing/config contract không đủ mạnh** |
| **HIGH/MED** | Supervisor attach xong chỉ hoạt động khoảng 1.6 phút rồi biến thành one-shot observer | **Chưa đạt continuous supervision** |
| **MED** | Fresh-review loop không có convergence/cost guard → 7 Reviewer xhigh | **Thiếu budget/escalation policy** |
| **MED** | `service_tier=priority` được dùng hàng loạt mà không có cost gate trước launch | **UX/policy gap** |
| **MED** | Lead biến Herdr lifecycle thành polling loop, 60 timeout | **Sai tinh thần bounded lifecycle observation** |
| **MED** | `freeze-candidate` / `inspect-candidate` từng chạy song song → inspect candidate cũ | **Stateful operation chưa được serialize/enforce** |
| **MED** | Immutable candidate object store gây friction lớn cho Reviewer | **Reviewer-facing contract chưa ergonomic** |
| **LOW/MED** | Không cleanup agent/pane sau review | 7 reviewer vẫn idle |
| **LOW/MED** | Setup thiếu `.orchestration/prompts/` | Render Assignment đầu tiên fail |
| **LOW** | Python helper tạo `__pycache__` trong skill checkout | Workspace pollution |
| **LOW/MED** | Preflight dump schema lớn vào context | Context/cost waste |

Hai vấn đề nên sửa đầu tiên là:

1. **Role/authority enforcement**
2. **Handback outcome contract**

---

# 1. HIGH — Role boundary thực tế đã bị drift

Đây là finding nghiêm trọng nhất.

Lead session ban đầu thao tác đúng với runtime binding của Lead:

```text
HERDR_ORCHESTRATOR_PANE_ID=w0:p2
HERDR_ORCHESTRATOR_ROLE=lead
...
start-peer ... architect_dexport
```

Engineer cũng được spawn khi Lead vẫn đang dùng:

```text
HERDR_ORCHESTRATOR_ROLE=lead
start-peer ... engineer_dexport
```

Reviewer v1 và v2 cũng tương tự:

```text
HERDR_ORCHESTRATOR_ROLE=lead
start-peer ... reviewer_dexport
start-peer ... reviewer_dexport_v2
```

Nhưng từ Reviewer v3 trở đi, chính session Lead bắt đầu chạy với:

```text
HERDR_ORCHESTRATOR_PANE_ID=w0:p8
HERDR_ORCHESTRATOR_ROLE=peer
...
herdr_orchestrator.py start-peer ... reviewer_dexport_v3
```

Sau đó tiếp tục:

```text
ROLE=peer ... start-peer reviewer_dexport_v4
ROLE=peer ... start-peer reviewer_dexport_v5
ROLE=peer ... start-peer reviewer_dexport_v6
ROLE=peer ... start-peer reviewer_dexport_v7
```

Session này còn dùng Peer binding để thực hiện:

```text
agent wait
agent read
submit-prompt
start-peer
```

Trong khi Peer profile quy định rõ:

> `Orchestrate no Lead, Peer, or Supervisor.`

và:

> `Agent orchestration remains with the Lead.`

## Root cause

Đây là **runtime-binding contamination**:

- Lead đọc/compose runtime binding dành cho child.
- Sau nhiều vòng context dài, Lead bắt đầu dùng binding của child như binding của chính nó.
- Helper không enforce caller role.

`start-peer` hiện đi thẳng tới:

```python
herdr_argv = [
    "herdr", "agent", "start", ...
]
```

mà không verify:

```text
HERDR_ORCHESTRATOR_ROLE == lead
```

Do đó:

```text
ROLE=peer start-peer ...
```

vẫn chạy thành công.

## Vấn đề kiến trúc

`HERDR_ORCHESTRATOR_ROLE` hiện chủ yếu là **semantic marker trong prompt**, chưa phải capability boundary thực sự.

Trong một orchestration system, đây là loại invariant không nên phụ thuộc vào việc model “nhớ đúng” sau vài giờ context.

## Đề xuất sửa

`start-peer` phải fail closed:

```text
start-peer:
    require HERDR_ORCHESTRATOR_ROLE == "lead"
```

Nên có capability matrix machine-enforced:

```text
Launcher:
  - start Lead
  - attach Supervisor
  - prompt Lead/Supervisor

Lead:
  - start Peer
  - prompt/wait/read Peer
  - freeze/inspect/accept candidate

Supervisor:
  - read orchestration state
  - prompt Lead với governance observation

Peer:
  - không được start/prompt agent khác
```

Đồng thời phải thêm rule rõ:

```md
A child runtime-binding projection is prompt payload for that child only.

The Lead MUST NOT execute commands from a child binding.

All Lead-side Herdr/helper operations MUST continue to use the Lead's
original runtime binding for the entire Lead lifetime.
```

**Kết luận:** re-entry guard hiện tại chưa đủ để chống runtime role drift trong session dài.

---

# 2. HIGH — Reviewer outcome contract tự mâu thuẫn

Peer profile nói handback phải trả một trong:

```text
COMPLETE
REOPEN_REQUEST
DEPENDENCY_REQUEST
BLOCKED
```

Nhưng Reviewer protocol lại nói:

```text
Nếu có finding, trả FINDINGS.
Nếu toàn bộ coverage đủ thì APPROVE.
```

Assignment Reviewer cũng yêu cầu:

```text
handback phải phân loại APPROVE hoặc FINDINGS
```

Reviewer vì vậy trả:

```json
{
  "outcome": "FINDINGS"
}
```

Sau đó Lead chạy:

```text
validate-handback
```

và validation fail.

Lead phải tự dịch:

```text
FINDINGS -> REOPEN_REQUEST
```

rồi ghi lại handback.

## Đây không phải lỗi Reviewer

Reviewer làm đúng instruction gần nhất. Prompt contract thực sự có hai ontology khác nhau cho cùng một field.

Trong lifecycle docs cũng tồn tại đồng thời:

```text
APPROVE / FINDINGS
```

và:

```text
COMPLETE / REOPEN_REQUEST / DEPENDENCY_REQUEST / BLOCKED
```

## Đề xuất sửa

Field `outcome` chỉ được phép dùng một vocabulary:

```text
COMPLETE
REOPEN_REQUEST
DEPENDENCY_REQUEST
BLOCKED
```

Với Reviewer:

```text
COMPLETE
= coverage đủ và không còn finding blocking

REOPEN_REQUEST
= có finding cần correction
```

Nếu vẫn muốn giữ reviewer-specific verdict, cho nó vào `evidence` hoặc field khác:

```json
{
  "outcome": "REOPEN_REQUEST",
  "review_verdict": "FINDINGS",
  "evidence": "..."
}
```

Hoặc đơn giản hơn, bỏ hẳn `APPROVE/FINDINGS`.

**Không nên có hai ontology cạnh tranh cho cùng một field.**

---

# 3. HIGH — `engineer-pi` có trong config nhưng Engineer thực tế chạy Codex

Config được Lead nhìn thấy có:

```text
engineer-pi
kind = pi
model = b-ai/glm-5.3-flash
thinking = high
```

Workspace Protocol còn nói:

```text
chọn Pi Engineer khi cần writer chuyên trách với flash model
```

Task này rõ ràng có dedicated writer.

Nhưng Lead tạo Assignment:

```json
{
  "disposition": "Engineer",
  "recipe": "codex-peer-high"
}
```

và gọi:

```text
start-peer
  --recipe codex-peer-high
  --name engineer_dexport
```

Engineer vì vậy chạy Codex, không phải Pi.

## Ý nghĩa

Herdr không tự “biến Pi thành Codex”.

Vấn đề là skill chưa có binding machine-readable kiểu:

```text
Engineer -> engineer-pi
```

Nó chỉ cung cấp một danh sách recipe và để Lead tự chọn recipe “phù hợp”.

Tên `engineer-pi` vì vậy không đồng nghĩa với:

```text
default Engineer recipe
```

## Đề xuất sửa

Thêm routing contract:

```toml
[routing.engineer]
default_recipe = "engineer-pi"
allowed_recipes = ["engineer-pi"]

[routing.architect]
default_recipe = "codex-peer-xhigh"

[routing.reviewer]
default_recipe = "codex-peer-xhigh"
```

Hoặc linh hoạt hơn:

```toml
[routing.engineer]
preferred = "engineer-pi"
fallback = ["codex-peer-high"]
fallback_requires = "dependency_request"
```

`validate-assignment` phải kiểm:

```text
disposition=Engineer
recipe=codex-peer-high
```

và reject nếu recipe không thuộc allowed routing hoặc không có explicit override.

Hiện validator mới kiểm:

```text
recipe có tồn tại hay không
```

chưa kiểm:

```text
recipe có đúng role/disposition intent hay không
```

Đây là lý do config có `engineer-pi` nhưng task vẫn chạy Engineer bằng Codex.

---

# 4. HIGH/MED — Supervisor hiện là one-shot advisor, chưa phải continuous Supervisor

Supervisor session chỉ tồn tại khoảng **1.6 phút**.

Nó:

1. đọc orchestration state;
2. quan sát Architect;
3. chờ một khoảng ngắn;
4. gửi một governance question cho Lead;
5. final;
6. idle.

Trong khi task tiếp tục hơn 3 giờ qua:

```text
Engineer
Reviewer
correction
Reviewer v2
correction
...
Reviewer v7
acceptance
```

Supervisor không quan sát các vòng sau.

## Cần phân biệt hai vấn đề

### Việc Supervisor không auto-create từ đầu

Điều này **không phải bug** nếu thiết kế hiện tại quy định task-launch chỉ tạo Lead và Supervisor có attach flow riêng.

### Supervisor đã attach nhưng chỉ chạy một turn

Đây mới là vấn đề.

Nếu Supervisor có nhiệm vụ:

- theo dõi attention;
- phát hiện loop;
- phát hiện cost/topology drift;
- phát hiện repeated failure;
- phát hiện authority drift;
- chất vấn Lead trước acceptance;

thì một Supervisor chạy 1.6 phút không đủ.

## Đề xuất sửa

Không nhất thiết cần một LLM turn sống liên tục.

Nên có event-driven supervision:

```text
observe when:
- Lead creates/replaces candidate
- Peer returns REOPEN_REQUEST
- Peer returns BLOCKED
- same mechanism fails twice
- active-agent count crosses threshold
- review cycle crosses threshold
- Lead announces acceptance
- role/caller mismatch occurs
```

Supervisor được wake/re-prompt khi event xuất hiện.

**Kết luận:** attach Supervisor hiện mới tạo “advisor một lần”, chưa operationalize continuous supervision.

---

# 5. MED — Fresh-review loop thiếu convergence và cost guard

Có 7 Reviewer:

```text
reviewer_dexport
reviewer_dexport_v2
reviewer_dexport_v3
reviewer_dexport_v4
reviewer_dexport_v5
reviewer_dexport_v6
reviewer_dexport_v7
```

Sáu Reviewer đầu đều tìm được defect thật, ví dụ:

- v1: 204 react, discovery partial, origin/revalidation, schema;
- v2: send/reply 204, double guild resolution;
- v3: `before + after`;
- v4: validation chỉ ở CLI/shared boundary chưa đủ;
- v5: pagination direction;
- v6: `request.headers()` vs `request.allHeaders()`;
- v7: approve.

Vì vậy **7 reviewer không đồng nghĩa reviewer bị loạn**. Falsification có giá trị thật.

## Vấn đề nằm ở orchestration policy

Rule hiện tại gần như:

```text
Correctable finding
→ same Engineer fixes
→ new candidate
→ fresh Reviewer
```

Điều này bảo vệ independence, nhưng thiếu điểm dừng về cost/convergence.

Trong run này:

- 7 Reviewer đều `xhigh`;
- đều là Codex;
- tất cả Codex recipe chạy `service_tier=priority`;
- riêng reviewers tiêu tốn rất nhiều runtime/tool calls.

## Đề xuất sửa

Thêm review convergence policy:

```text
review_cycle == 1:
    fresh reviewer normally

review_cycle == 2:
    fresh reviewer + root-cause check

review_cycle >= 3:
    stop automatic fresh-review loop
    Lead performs convergence assessment:
      - findings có cùng mechanism không?
      - specification có thiếu không?
      - review scope có quá incremental không?
      - Engineer có sai recipe/model không?
      - cần Architect quay lại không?
      - cần Supervisor intervention không?
      - cần Human cost approval không?
```

Điều này không có nghĩa cycle 3 phải terminate project.

Nó chỉ ngăn:

```text
fresh xhigh reviewer
→ finding
→ fix
→ fresh xhigh reviewer
→ finding
→ ...
```

chạy vô hạn mà không có meta-level diagnosis.

---

# 6. MED — `service_tier=priority` được dùng mà không có Human cost gate trước launch

Project config truyền:

```text
--config service_tier=priority
```

cho:

- Lead;
- Supervisor;
- các Codex Peer recipes.

Do đó UI hiện fast/priority.

## Đây không phải Herdr tự ý bật

Recipe/config đã chứa flag này.

Nhưng dogfood cho thấy Launcher/preflight chưa surface cost-sensitive launch plan đủ sớm.

Human chỉ phát hiện khi run đã chạy.

Trong khi SLP model nói material cost là Human-owned.

## Đề xuất sửa

Preflight nên hiển thị tối thiểu:

```text
Lead:
  codex / luna / xhigh / priority

Potential Architect:
  codex / luna / xhigh / priority

Potential Engineer:
  pi / glm-5.3-flash / high

Potential Reviewer:
  codex / luna / xhigh / priority

Cost-sensitive flags:
  service_tier=priority
```

Nếu recipe có:

```text
priority
max
expensive model
xhigh
```

thì nên có explicit Human gate hoặc config policy:

```toml
[cost]
allow_priority = false
require_human_approval_for_priority = true
```

Skill không nên để material cost semantics chỉ nằm ẩn trong recipe.

---

# 7. MED — Lifecycle collection đã biến thành polling loop

Lead có khoảng **60 `herdr agent wait` timeout**.

Pattern lặp lại:

```text
agent wait reviewer --until idle --timeout 60000
→ timeout

agent wait reviewer --until idle --timeout 60000
→ timeout

agent wait reviewer --until idle --timeout 60000
→ timeout
```

Trong khi skill mô tả wait/recovery là bounded lifecycle observation, không phải prompt-wait subsystem.

## Vấn đề

Lead đã biến thành polling controller:

- tốn context;
- tốn tool calls;
- tạo hàng loạt failed command giả;
- làm khó quan sát failure thực;
- kéo dài session Lead.

## Đề xuất sửa

Lifecycle observation nên là:

```text
one wait
→ timeout
→ get/read once
→ return control hoặc wait for event
```

Không nên là:

```text
wait → timeout → wait → timeout → wait...
```

Nếu Herdr có event/notification/automation thì lifecycle nên event-driven.

Nếu chưa có, helper ít nhất cần enforce retry budget.

---

# 8. MED — Candidate state có race vì stateful operations từng chạy song song

Có đoạn Lead xác nhận:

> freeze/inspect vừa rồi bị chạy đồng thời nên inspect đã đọc candidate cũ.

Sau đó phải chạy lại tuần tự.

## Root cause

Model có xu hướng parallelize tool calls để tối ưu thời gian.

Nhưng:

```text
freeze-candidate
inspect-candidate
```

là dependency chain có mutable pointer/state.

Docs nói “freeze rồi inspect” chưa đủ để chống accidental parallelization.

## Đề xuất sửa

Thêm optimistic state binding:

```text
inspect-candidate --expected-tree <tree>
```

hoặc:

```text
inspect-candidate --candidate-document-sha256 <digest>
```

Nếu `current-candidate.json` không còn khớp thì fail.

Đồng thời ghi explicit invariant:

```md
freeze-candidate and inspect-candidate MUST be sequential.

Never execute candidate mutation and candidate inspection concurrently.
```

Quan trọng hơn: nên enforce bằng helper, không chỉ bằng prose.

---

# 9. MED — Immutable candidate object store đúng về integrity nhưng reviewer-facing UX quá khó

Candidate được freeze bằng private Git object store là hướng tốt về immutability.

Nhưng reviewers gặp nhiều friction:

- tree không nằm trong normal `.git/objects`;
- phải set `GIT_OBJECT_DIRECTORY`;
- phải set `GIT_ALTERNATE_OBJECT_DIRECTORIES`;
- phải manual `git archive`;
- phải manual verify hash blob/tree;
- `git apply --check` có lúc phụ thuộc mutable working tree;
- helper/parser tree object fail;
- OCR/other skill không hiểu candidate layout.

Lead nhiều lần phải giải thích rằng lỗi nằm ở cách Reviewer đọc candidate, không phải candidate hỏng.

## Vấn đề abstraction

Reviewer không nên cần biết candidate implementation dùng loose Git object store như thế nào.

Immutable candidate nên là **opaque artifact abstraction**.

## Đề xuất sửa

Thêm canonical read-only interface:

```text
herdr_orchestrator.py materialize-candidate   --project-root ...   --output /tmp/review-...
```

trả:

```json
{
  "candidate": "...",
  "readonly_path": "...",
  "verified": true
}
```

Hoặc cung cấp helper:

```text
candidate-files
candidate-diff
candidate-exec
candidate-show
```

Reviewer chỉ dùng interface chính thức.

Không nên để mỗi fresh Reviewer tự phát minh lại cách mount/read Git object store.

---

# 10. LOW/MED — Fresh Reviewer đang đồng nghĩa với fresh pane tồn tại vĩnh viễn

Sau task vẫn còn:

```text
architect_dexport
engineer_dexport
reviewer_dexport
reviewer_dexport_v2
...
reviewer_dexport_v7
```

ở trạng thái idle.

Fresh judgment không nhất thiết đồng nghĩa:

```text
new session + new pane + giữ pane mãi
```

## Đề xuất sửa

Sau validated handback:

```text
stop child process
retain transcript/session/evidence
```

Hoặc recycle execution slot nhưng luôn tạo fresh LLM session.

Sau final acceptance:

```text
cleanup task-owned idle panes
```

nếu policy cho phép.

Hiện topology chỉ tăng mà không co.

---

# 11. LOW/MED — Setup contract thiếu `.orchestration/prompts/`

Assignment đầu tiên fail vì:

```text
error: output parent is not a directory:
.orchestration/prompts
```

Lead phải tự tạo directory rồi chạy lại.

## Đề xuất sửa

Một trong hai:

```text
setup/init
→ luôn tạo .orchestration/prompts/
```

hoặc:

```text
render-assignment
→ tự mkdir parent safely
```

First task không nên là nơi discovery filesystem prerequisite.

---

# 12. LOW — Python helper tạo `__pycache__` trong skill checkout

Các session ghi nhận:

```text
?? .agents/skills/herdr-orchestrator/scripts/herdr_harnesses/__pycache__/
```

Đây là side effect từ helper orchestration.

Với skill nhấn mạnh preserve workspace/candidate cleanliness thì điều này không nên xảy ra.

## Đề xuất sửa

Chạy helper với:

```text
PYTHONDONTWRITEBYTECODE=1
```

hoặc redirect cache ra ngoài repo.

---

# 13. LOW/MED — Preflight/schema dump quá lớn làm tăng context và cost

Một số bước preflight/tool discovery đưa lượng schema/tool description lớn vào session.

Với Lead chạy nhiều giờ, context inflation này làm tăng nguy cơ:

- attention drift;
- role-binding contamination;
- instruction competition;
- chi phí;
- khó tìm invariant quan trọng.

## Đề xuất sửa

- Chỉ load schema cần cho command hiện tại.
- Tách Human/setup docs khỏi agent-operation docs.
- Giảm duplicated prose giữa profile/protocol/lifecycle.
- Chuyển invariant quan trọng thành validator/helper thay vì lặp lại bằng Markdown.
- Dùng compact runtime binding cho Lead, không inject child-facing details không cần thiết.

---

# Pattern kiến trúc quan trọng nhất rút ra từ dogfood

Run này cho thấy một pattern rất rõ:

## Những gì được encode thành executable invariant thì hoạt động khá tốt

Ví dụ:

```text
candidate immutable
assignment schema
one-writer map
review candidate binding
acceptance document
```

## Những gì mới chỉ tồn tại dưới dạng prose thì dễ drift

Ví dụ:

```text
Engineer nên dùng Pi
Lead phải luôn là Lead
Supervisor phải supervise lâu dài
bounded wait không được thành polling
material cost phải Human-owned
```

Kết luận kiến trúc:

> **Các invariant quan trọng hiện được mô tả tốt bằng Markdown nhưng chưa được biến thành executable contract đủ nhiều.**

Dogfood bắt đầu lệch đúng ở các boundary chỉ được bảo vệ bằng prose.

---

# Những phần dogfood cho thấy skill đang làm tốt

Không nên kết luận toàn bộ orchestration thất bại chỉ vì có 7 Reviewer.

Một số phần hoạt động tốt:

- Launcher/Lead/Peer authority separation về mặt design khá rõ.
- Human gate trước architecture decision thực sự chặn implementation.
- Một writer duy nhất được giữ xuyên suốt.
- Findings quay lại đúng Engineer cũ.
- Candidate được freeze lại sau mỗi mutation.
- Evidence cũ bị invalidate khi candidate thay đổi.
- Reviewer thực sự độc lập và tìm được defect thật.
- Lead không dùng `idle` hoặc passing tests làm acceptance.
- Final acceptance bind đúng candidate và Reviewer cuối.
- Không có writer overlap.
- Human task được giữ xuyên qua launch.
- Reviewer cuối thực sự falsify candidate mới thay vì chỉ kiểm “fix có tồn tại”.

Nền tảng **SLP semantic layer + Herdr runtime** vì vậy vẫn có giá trị.

Các vấn đề chính nằm ở:

```text
enforcement
routing
lifecycle
cost control
convergence
runtime ergonomics
```

---

# Thứ tự ưu tiên refactor

## P0 — phải sửa trước dogfood tiếp

### 1. Enforce caller role/capability trong helper

Đặc biệt:

```text
start-peer
submit-prompt
accept-candidate
```

phải check role/capability.

Child binding không được executable bởi Lead.

### 2. Unify handback outcome vocabulary

Chỉ dùng:

```text
COMPLETE
REOPEN_REQUEST
DEPENDENCY_REQUEST
BLOCKED
```

Bỏ `APPROVE/FINDINGS` khỏi `outcome`.

### 3. Role/disposition → recipe routing contract

Ví dụ:

```text
Engineer → engineer-pi
Reviewer → codex-peer-xhigh
Architect → codex-peer-xhigh
```

Validator phải enforce routing hoặc explicit override.

---

## P1 — nên sửa ngay sau P0

### 4. Continuous/event-driven Supervisor

Supervisor phải wake theo orchestration events, không phải chạy một turn rồi biến mất.

### 5. Review convergence + cost budget gate

Sau N reopen cycles phải chạy meta-level convergence assessment.

### 6. Cost-sensitive preflight

Human phải thấy và approve các flag như:

```text
service_tier=priority
xhigh
max
expensive recipe
```

trước launch.

### 7. Loại polling loop

Wait phải bounded và event-oriented.

---

## P2 — robustness/ergonomics

### 8. Serialize/bind candidate operations

`freeze` → `inspect` phải có state version/hash check.

### 9. Canonical candidate materialization

Reviewer không phải tự mount Git object store.

### 10. Cleanup lifecycle

Stop/recycle idle Peer execution slots sau validated handback hoặc acceptance.

### 11. Setup completeness

Tự tạo:

```text
.orchestration/prompts/
```

### 12. Không tạo `__pycache__` trong repo

### 13. Giảm schema/context dump

---

# Finding quan trọng nhất

Nếu chỉ chọn **một finding quan trọng nhất** từ toàn bộ dogfood:

> **Lead session bắt đầu gọi `start-peer` với `HERDR_ORCHESTRATOR_ROLE=peer` từ Reviewer v3 trở đi.**

Điều này chứng minh role/authority hiện vẫn phụ thuộc quá nhiều vào model giữ đúng prose trong một context dài.

Đây chính xác là loại lỗi mà orchestration layer nên ngăn bằng **mechanical capability enforcement**, không nên giao cho model tự nhớ.

---

# Kết luận cuối

Dogfood này không cho thấy ý tưởng SLP + Herdr sai.

Ngược lại, nó cho thấy phần semantic model khá mạnh, nhưng implementation hiện còn một khoảng cách rõ giữa:

```text
policy described in Markdown
```

và:

```text
policy mechanically enforced at runtime
```

Ưu tiên refactor nên là biến các rule liên quan tới:

- role authority;
- recipe routing;
- reviewer outcome;
- cost ownership;
- convergence;
- supervisor lifecycle;
- candidate state;

thành **executable contracts**.

Khi các boundary này được enforce bằng helper/validator/runtime thay vì chỉ bằng prompt prose, skill sẽ ổn định hơn đáng kể khi chạy task dài, nhiều Peer và nhiều review cycle.
