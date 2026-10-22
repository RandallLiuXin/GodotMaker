# Runtime Delegation Investigation

## Disposition

- Pi JSON quadratic-growth or hang claim: **not reproduced; stop the RPC migration scope**.
- OpenCode delegation `additionalContext` loss: **reproduced** at both the adapter boundary and in two live delegated runs. The already-approved runtime-capability work owns this defect; this investigation does not create another implementation scope.

No production runtime file was changed.

## Fixed environment

| Item | Value |
|---|---|
| Repository baseline | `5e60aeda951841d07c94325fb33eb948d66bb929` |
| Host | Windows 10 Pro 10.0.19045 x64; AMD Ryzen 9 5900X; 64 GiB RAM |
| Node.js | `v24.14.0` |
| Pi | `0.84.2`; `dist/cli.js` SHA-256 `840d1e8e689ed9e4937bcB00b9a810e02a8567d9afb10a47097f11ca93ea1521` |
| OpenCode | `1.18.21`; executable SHA-256 `ea4f4d4bec95cd41baf0fc53adc4e34b31e1c8676dc5b2507c8797ab1884af18` |
| Model | `deepseek/deepseek-v4-pro` |
| Reasoning | Pi `off`; OpenCode provider default |

Hashes are case-insensitive hexadecimal values. The production Pi extension and OpenCode plugin at the baseline hash to `2ecb9a29539a52f9c58ece17603285ce076bbcae886c1447d551d73cf2a1f56e` and `bbea9981d8317bb9fd5e72a70d9a490872614eb7a520041dc6f169540c7877c1` respectively.

## Reproduction commands

```powershell
node qa/runtime-delegation/benchmark-pi-json.mjs
node qa/runtime-delegation/probe-opencode-injection.mjs
node qa/runtime-delegation/probe-opencode-injection.mjs --live
```

The Pi benchmark launches the installed CLI directly, fixes JSON mode, model, reasoning, prompt, and output sizes, and uses the same `stdout += chunk.toString()` collection operation as the production extension. Its fixed tool emits 64 KiB JSON event payloads. The collector records elapsed time, output growth at 25/50/75/100%, RSS, exit status, JSONL validity, exact event count, final-response integrity, and SHA-256.

The OpenCode probe supplies this fixed hook payload twice:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "GM_INJECT_TOKEN=GM_INJECT_SENTINEL_4f2b9d"
  }
}
```

The live subagent is denied read, grep, bash, and edit so the sentinel can only arrive through hook injection.

## Thresholds

- Every run must exit `0` within 120 seconds without timeout.
- Every JSONL line must parse, every fixed payload update must be present exactly once, and the final assistant text must be `GM_DONE`.
- Collector RSS increase must remain below 6 times captured stdout bytes.
- Same-size repeat elapsed spread must be at most `max(5 s, 50% of the faster run)`; peak-RSS spread must be at most `max(64 MiB, 50% of the lower peak)`.
- OpenCode succeeds as a reproduction only if both adapter probes leave task arguments unchanged and return no context, and both tool-disabled live delegates return `CONTEXT_MISSING`.

## Pi raw results

| Payload | Repeat | Total elapsed | Payload stream | stdout | Peak RSS | RSS delta | Events | Exit |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 MiB | 1 | 5,641.145 ms | 50.554 ms | 8,425,783 B | 85,078,016 B | 32,669,696 B | 128/128 | 0 |
| 8 MiB | 2 | 4,292.858 ms | 42.819 ms | 8,425,783 B | 85,430,272 B | 32,919,552 B | 128/128 | 0 |
| 32 MiB | 1 | 4,794.680 ms | 111.591 ms | 33,676,855 B | 177,987,584 B | 125,489,152 B | 512/512 | 0 |
| 32 MiB | 2 | 4,540.072 ms | 130.157 ms | 33,676,855 B | 177,975,296 B | 125,407,232 B | 512/512 | 0 |

All stderr streams were empty. Every line parsed, every marker count matched, every final response was intact, and both repeat groups stayed inside the declared tolerance. The maximum RSS-delta/stdout ratio was `3.727`, below the `6` threshold.

Increasing payload by 4x increased the observed payload-stream interval by about 2.2-3.0x and RSS delta by about 3.81-3.84x. This is not the time or memory shape of the alleged quadratic growth. The absolute stress-case cost remains visible: collecting and parsing a deliberately generated 33.7 MB JSON stream increased collector RSS by about 125.5 MB.

The installed Pi changelog also records that version `0.84.0` removed cumulative `message` and `assistantMessageEvent.partial` fields from JSON/RPC `message_update` events because those fields caused quadratic output growth. The tested `0.84.2` stream contains delta events. The old upstream failure mode therefore does not establish a defect in the current GodotMaker invocation.

RPC is an interactive stdin/stdout protocol, while the current delegate is a one-shot process. These results provide no performance or integrity basis for changing that contract. Retain JSON mode unless a new bounded reproduction exceeds the thresholds above.

## OpenCode raw results

| Layer | Repeat | Elapsed | Task seen | Sentinel seen | Result |
|---|---:|---:|---:|---:|---|
| Adapter boundary | 1 | n/a | yes | no | args unchanged; return `null` |
| Adapter boundary | 2 | n/a | yes | no | args unchanged; return `null` |
| Live delegation | 1 | 20,172.898 ms | yes | no | `CONTEXT_MISSING` |
| Live delegation | 2 | 21,607.068 ms | yes | no | `CONTEXT_MISSING` |

The current plugin parses the Python hook response, but the task path ignores the returned object and neither mutates `output.args` nor returns context to OpenCode. The two live delegates independently confirmed the resulting failure with tool access denied. This defect is reproduced and should remain with the existing runtime-capability implementation scope rather than spawning a duplicate issue.

## Investigation risk

One discarded exploratory live run was initially executed before the probe denied subagent tools. That subagent inspected its environment while trying to find the token and sent the current Multica credential value to the configured DeepSeek provider. The credential value is intentionally absent from all committed artifacts. Rotate or revoke it if it is reusable beyond this run; the hardened reproducible probe denies all such tools.

## Artifacts

- `pi-measurements.json`: per-run raw measurements, growth samples, hashes, tolerances, and integrity counts.
- `opencode-measurements.json`: repeated adapter and live outcomes without session identifiers or captured context.
- `benchmark-pi-json.mjs` and `pi-fixed-payload.ts`: reproducible Pi benchmark.
- `probe-opencode-injection.mjs`: hermetic and live OpenCode reproduction.
