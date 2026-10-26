# EXT-04: public context-component and persistence contracts

The reference component implements the pinned public `registerContextEngine` interface and accepted-turn declaration. It uses generic whole-user-turn bounded assembly and writes only an owned JSON commit index, capped at 512 KiB. The fixture is serial and single-Gateway; its fsync/rename idempotency implementation is not asserted to provide a distributed storage transaction. It does not patch native transcripts, choose oracle-specific facts, manufacture summaries or inject hidden answers.

Four frozen scenarios run after whole-family native calibration, with three independent units each:

- S01 compares fresh built-in legacy and reference-component arms under the same native provider/tool task contract. Actual reference assemble and accepted-turn commit callbacks must occur; successful tasks and original native public transcript records are independently checked.
- S02 supplies eight public 16 KiB varied-text turns, crossing the reference's conservative UTF-8 JSON bytes/4 estimate against the actual host-supplied context budget. The component must assemble whole turns under that supplied budget, while the core's original accepted user/tool transcript remains accessible. This is a context-contract and supplied-budget exercise, not a real-model tokenizer maximum or a summarization-quality benchmark. Real-model context and native LLM compaction are measured separately in PERF-10.
- S03 restarts the actual native Gateway with the same state, requires the reference checkpoint keys to survive and advance, and independently checks that the next actual model input contains pre-restart native history.
- S04 disables and reenables the component through the native public CLI while retaining its selected slot ID. The disabled component must neither assemble nor mutate its checkpoint; native fallback must execute the task and retain original state. Reenabling must restore the selected component.

A callback that never ran, an unexercised budget condition or a failed component fixture remains incomplete. Native core persistence, permission checks, session identity and admission ownership are not replaced by the reference component. All execution and the at most 128 MiB temporary native state remain on disposable GitHub workers; no paid model is called and no extra local runtime is installed.

Contracts: [pinned context-engine lifecycle](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/docs/concepts/context-engine.md) and [durable admitted-turn plugin contract](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/docs/plugins/sdk-overview/memory-and-context.md).
