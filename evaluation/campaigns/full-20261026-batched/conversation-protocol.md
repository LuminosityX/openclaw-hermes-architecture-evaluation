# PERF-10: actual long conversations, compaction and continuation

Five scenarios each execute six independent real `deepseek-flash` units through the native Gateway. Every answer must independently match released configuration values and a unique setup anchor, retain correct JSON types, preserve immutable inputs and complete its final task within 180 seconds. The anchor is absent from the final user prompt. Failed tasks remain in the denominator.

| Scenario | Native condition |
| --- | --- |
| S01 | Short control; released source includes its setup anchor. |
| S02 | Six actual native user/model exchanges, each carrying 16 KiB of synthetic background text, precede the final task. Only the first exchange provides the setup anchor; the source does not repeat it. |
| S03 | Four 8 KiB native exchanges precede actual `openclaw sessions compact <key> --json`. `compacted=true` must establish native LLM summarization; transcript truncation and handcrafted summaries are forbidden. The final task still needs the original anchor. |
| S04 | The required values and anchor appear after 64 KiB of irrelevant source text in a real native tool result. The public file tool permits the entire bounded source, so evaluator truncation cannot manufacture product loss. |
| S05 | The six-exchange long conversation is followed by a clean actual Gateway process restart using the same owned state and the same native session key. The final task requires its original setup anchor. |

The registered model context window is 131,072 tokens; these bounded histories are not a maximum-context benchmark. Automatic compaction and memory flush are disabled to distinguish accumulated history from the explicit compaction intervention. S03 retains one recent turn and 512 recent tokens, disables compaction quality retries, and permits 120 seconds for the native summarizer. Effective config hashes, actual CLI output, phase timings, process IDs, endpoint status, provider counters and resources are retained. No shared dependency installation or entire state environment is copied.

The host-only provider relay records whether each real native input contains the original anchor and the end-of-source marker, plus actual request bytes. It retains no full prompt, reasoning or provider response. Before paid runs, all five conditions must pass golden native calibration; a golden answer alone cannot conceal missing native context. Golden compaction text is development wiring input only. Formal compaction, priming and final answers all use the real provider and count toward actual usage.

The final task has a 180-second deadline; each primer has a 60-second endpoint deadline, and the whole native unit is bounded to 900 seconds, 32 model requests and 4,096 output tokens per request. After restart, only a fresh explicit native database-admission HTTP 500 can be polled for at most 30 seconds, and only when independent bridge and task-tool counters prove no dispatch. Ambiguous or admitted work is never replayed by the evaluator.

Cases run in parallel on disposable GitHub machines, with one shared pinned installation per job. Each job validates the complete family before executing the selected pending scenario's formal units. Bounded raw evidence and provider ledgers stay on GitHub; accepted compact records are losslessly compressed and still obey the local 4 MiB campaign evidence limit. Unified source-backed architectural interpretation remains deferred.
