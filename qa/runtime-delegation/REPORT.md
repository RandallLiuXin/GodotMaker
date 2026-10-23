# Runtime Delegation Investigation

## Disposition

- Pi JSON quadratic-growth claim: **not reproduced; stop the RPC migration as a performance fix**.
- Pi production delegation hang: **reproduced**. The one-shot process inherits an open stdin pipe, while Pi waits for stdin EOF before issuing a model request. This is independent of JSON output collection and does not require an RPC migration; closing or ignoring child stdin is sufficient.
- OpenCode pre-tool hook result loss: **reproduced at the adapter boundary**. The current task branch discards the parsed hook result. The already-approved runtime-capability work owns this defect; this investigation does not create another implementation scope.

At the investigation baseline, no production runtime file was changed. After explicit approval on 2026-10-23, the production `runDelegate` spawn was updated to ignore child stdin while preserving piped stdout and stderr. The hang probe remains a bounded reproduction of the pre-fix production spawn shape.

## Fixed environment

| Item | Value |
|---|---|
| Repository baseline | `5e60aeda951841d07c94325fb33eb948d66bb929` |
| Host | Windows 10 Pro 10.0.19045 x64; AMD Ryzen 9 5900X; 64 GiB RAM |
| Node.js | `v24.14.0` |
| Pi | `0.84.2`; `dist/cli.js` SHA-256 `840d1e8e689ed9e4937bcb00b9a810e02a8567d9afb10a47097f11ca93ea1521` |
| OpenCode | `1.18.21`; executable SHA-256 `ea4f4d4bec95cd41baf0fc53adc4e34b31e1c8676dc5b2507c8797ab1884af18` |
| Pi model | `deepseek/deepseek-v4-pro` |
| Reasoning | Pi `off`; OpenCode probe makes no model request |

The production Pi extension and OpenCode plugin at the baseline hash to `2ecb9a29539a52f9c58ece17603285ce076bbcae886c1447d551d73cf2a1f56e` and `bbea9981d8317bb9fd5e72a70d9a490872614eb7a520041dc6f169540c7877c1` respectively.

## Reproduction commands

```powershell
node qa/runtime-delegation/benchmark-pi-json.mjs
node qa/runtime-delegation/probe-pi-stdin-hang.mjs
node qa/runtime-delegation/probe-opencode-injection.mjs
```

The Pi benchmark launches the installed CLI directly, fixes JSON mode, model, reasoning, prompt, and output sizes, and uses the same `stdout += chunk.toString()` accumulation operation as the production extension. It intentionally ignores stdin so it can isolate JSON collection performance; it does not mirror the complete production spawn configuration. Its fixed tool emits 64 KiB JSON event payloads. The collector records elapsed time, output growth at 25/50/75/100%, RSS, exit status, JSONL validity, exact event count, final-response integrity, and SHA-256.

The Pi stdin probe uses the production one-shot flags and exactly mirrors the pre-fix `spawn(command, args, { cwd, shell: false, windowsHide: true })` call, including its default open stdin pipe; provider, model, and reasoning are additionally pinned for repeatability. It runs two bounded 10-second pre-fix attempts, then two controls that change only stdin to `ignore`.

The OpenCode probe invokes the production adapter directly with a fixed temporary hook and fixed task arguments. It verifies that the task pre-hook path discards the parsed hook result. It does not start a model session, pass provider credentials, or claim that `additionalContext` must be injected into a child prompt; host routing semantics remain an integration concern for the owning runtime-capability work.

## Thresholds

- Pi JSON collection: every run must exit `0` within 120 seconds without timeout; every JSONL line must parse; every fixed payload update must be present exactly once; final assistant text must be `GM_DONE`.
- Collector RSS increase must remain below 6 times captured stdout bytes.
- Same-size repeat elapsed spread must be at most `max(5 s, 50% of the faster run)`; peak-RSS spread must be at most `max(64 MiB, 50% of the lower peak)`.
- Pi stdin hang: both pre-fix production-shape runs must time out with zero stdout; both stdin-ignored controls must exit `0` and return `GM_DONE`.
- OpenCode adapter loss: both fixed boundary probes must leave task arguments unchanged and propagate no hook result.

## Pi JSON raw results

| Payload | Repeat | Total elapsed | Payload stream | stdout | Peak RSS | RSS delta | Events | Exit |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 MiB | 1 | 5,641.145 ms | 50.554 ms | 8,425,783 B | 85,078,016 B | 32,669,696 B | 128/128 | 0 |
| 8 MiB | 2 | 4,292.858 ms | 42.819 ms | 8,425,783 B | 85,430,272 B | 32,919,552 B | 128/128 | 0 |
| 32 MiB | 1 | 4,794.680 ms | 111.591 ms | 33,676,855 B | 177,987,584 B | 125,489,152 B | 512/512 | 0 |
| 32 MiB | 2 | 4,540.072 ms | 130.157 ms | 33,676,855 B | 177,975,296 B | 125,407,232 B | 512/512 | 0 |

All stderr streams were empty. Every line parsed, every marker count matched, every final response was intact, and both repeat groups stayed inside the declared tolerance. The maximum RSS-delta/stdout ratio was `3.727`, below the `6` threshold.

Increasing payload by 4x increased the observed payload-stream interval by about 2.2-3.0x and RSS delta by about 3.81-3.84x. This is not the time or memory shape of quadratic growth. The absolute stress-case cost remains visible: collecting and parsing a deliberately generated 33.7 MB JSON stream increased collector RSS by about 125.5 MB.

The installed Pi changelog records that version `0.84.0` removed cumulative `message` and `assistantMessageEvent.partial` fields from JSON/RPC `message_update` events because those fields caused quadratic output growth. The tested `0.84.2` stream contains delta events. The old upstream failure mode therefore does not establish a quadratic-growth defect in the current GodotMaker invocation.

## Pi pre-fix production hang results

At the investigated baseline, the production extension did not specify `stdio`. Node therefore created a writable child stdin pipe and left it open. Pi `0.84.2` calls `readPipedStdin()` in non-RPC modes and waits for that pipe's `end` event before making a model request.

The committed probe reproduces this with the production arguments and pre-fix spawn shape. The expected evidence is two pre-fix timeouts with zero stdout and two stdin-ignored controls that exit successfully with `GM_DONE`; the exact recorded results are in `pi-hang-measurements.json`.

RPC happens to bypass `readPipedStdin`, but RPC is not required to fix this failure. Spawning with stdin ignored supplies the required EOF while retaining one-shot JSON mode; the subsequently approved remediation now uses that option in production.

## OpenCode adapter results

| Layer | Repeat | Task args changed | Hook result propagated | Result |
|---|---:|---:|---:|---|
| Adapter boundary | 1 | no | no | loss reproduced |
| Adapter boundary | 2 | no | no | loss reproduced |

The current plugin parses the Python hook response, but the task branch ignores the returned object and neither returns it to OpenCode nor otherwise propagates it. The defect is reproduced by the adapter-boundary probe and code path. The correct host-visible destination for `additionalContext` is intentionally left to the existing runtime-capability implementation scope; this report no longer treats child-prompt injection as required semantics.

## Investigation risk

One discarded exploratory live run was executed before tool and environment isolation was understood. Its subagent inspected the environment while trying to find the token and sent the current Multica credential value to the configured DeepSeek provider. The credential value is absent from all committed artifacts. Rotate or revoke it if it is reusable beyond that run.

The unsafe live model path has been removed from the committed probe and from the standard reproduction commands. The remaining OpenCode probe is adapter-only, starts no model session, and does not pass the parent environment to a provider process.

## Artifacts

- `pi-measurements.json`: fixed JSON-collection measurements, growth samples, hashes, tolerances, and integrity counts.
- `pi-hang-measurements.json`: direct output from the bounded pre-fix production-spawn hang probe.
- `opencode-measurements.json`: direct output from the repeated adapter-boundary probe.
- `benchmark-pi-json.mjs` and `pi-fixed-payload.ts`: reproducible Pi JSON-collection benchmark.
- `probe-pi-stdin-hang.mjs`: reproducible pre-fix production-spawn stdin hang and stdin-ignored control.
- `probe-opencode-injection.mjs`: model-free OpenCode adapter-boundary reproduction.
