import { Type } from "typebox";

const chunkBytes = Number.parseInt(process.env.GM_BENCH_CHUNK_BYTES ?? "65536", 10);
const chunkCount = Number.parseInt(process.env.GM_BENCH_CHUNK_COUNT ?? "128", 10);

if (!Number.isSafeInteger(chunkBytes) || chunkBytes < 64) {
  throw new Error("GM_BENCH_CHUNK_BYTES must be an integer >= 64");
}
if (!Number.isSafeInteger(chunkCount) || chunkCount < 1) {
  throw new Error("GM_BENCH_CHUNK_COUNT must be a positive integer");
}

export default function (pi: any) {
  pi.registerTool({
    name: "fixed_payload",
    label: "Fixed payload benchmark",
    description: "Emit the fixed runtime-delegation benchmark payload.",
    parameters: Type.Object({}),
    async execute(_id: string, _params: unknown, _signal: AbortSignal | undefined, onUpdate?: (value: unknown) => void) {
      const bodyBytes = chunkBytes - 32;
      const body = "x".repeat(bodyBytes);
      for (let index = 0; index < chunkCount; index += 1) {
        if (_signal?.aborted) throw new Error("benchmark aborted");
        onUpdate?.({
          content: [{ type: "text", text: `GM_CHUNK:${index}:${body}:GM_END` }],
          details: { index, chunkBytes, chunkCount },
        });
        if ((index + 1) % 32 === 0) {
          await new Promise<void>((resolve) => setImmediate(resolve));
        }
      }
      return {
        content: [{ type: "text", text: "GM_TOOL_DONE" }],
        details: { chunkBytes, chunkCount },
      };
    },
  });
}
