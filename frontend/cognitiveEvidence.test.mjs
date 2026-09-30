// Render the real evidence card without starting a browser or writing build files.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

process.on("uncaughtException", (error) => {
  console.error(error.message);
  process.exit(1);
});

const bundle = await build({
  stdin: {
    contents: `
      import { EvidenceCard } from './src/CognitivePanels.tsx';
      import { renderToStaticMarkup } from 'react-dom/server';
      export const render = (round) => renderToStaticMarkup(EvidenceCard({ round }));
    `,
    resolveDir: fileURLToPath(new URL(".", import.meta.url)),
  },
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
  jsx: "automatic",
  define: { "import.meta.env": "{}" },
  banner: { js: `import { createRequire } from 'node:module'; const require = createRequire(${JSON.stringify(import.meta.url)});` },
});
let render;
try {
  ({ render } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`));
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
const base = {
  states_correct_conclusion: false,
  conclusion_level: "wrong",
  explains_reason_correctly: false,
  shows_residual_misconception: false,
  conceptual_uncertainty: false,
  parrots_teacher: false,
};
const card = (evidence) => render({ round: 1, state_after: { surface_recall: 0 }, evidence: { ...base, ...evidence } });

const repetition = card({ states_correct_conclusion: true, conclusion_level: "correct", explanation_content_correct: true, parrots_teacher: true });
assert.match(repetition, /复述内容正确，尚需独立解释/);
assert.doesNotMatch(repetition, /能解释原因/);

const missing = card({ slope_claim_status: "insufficient_conditions", conceptual_uncertainty: true, states_correct_conclusion: true, conclusion_level: "partial" });
assert.match(missing, /还缺少 k 的正负或具体数值条件/);
assert.match(missing, /包含部分正确结论/);
assert.doesNotMatch(missing, /得出了正确结论|真实犹豫|仍存在原有错误认知/);

const incorrect = card({ slope_claim_status: "incorrect" });
assert.match(incorrect, /斜率变化判断有误/);
assert.doesNotMatch(incorrect, /仍存在原有错误认知/);
assert.match(card({ explains_reason_correctly: true }), /能解释原因/);
assert.match(card({ parrots_teacher: true }), /可能只是复述教师结论/);
console.log("Cognitive evidence card: 5 scenarios passed.");
