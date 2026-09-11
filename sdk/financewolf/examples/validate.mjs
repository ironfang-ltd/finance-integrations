// FINANCEWOLF_API_KEY=... node validate.mjs invoice.xml fwrs_...
import { readFile } from 'node:fs/promises';
import { Financewolf, FinancewolfError } from '@ironfang/financewolf';

try {
  const result = await new Financewolf({ apiKey: process.env.FINANCEWOLF_API_KEY ?? '' })
    .validate(await readFile(process.argv[2]), { ruleset: process.argv[3] });
  console.log(JSON.stringify({ outcome: result.outcome, ruleset: result.ruleset.id, sha256: result.input.sha256 }));
  process.exitCode = result.outcome === 'valid' ? 0 : 1;
} catch (error) {
  console.error(error instanceof FinancewolfError ? error.message : 'Financewolf: input unavailable');
  process.exitCode = 2;
}
