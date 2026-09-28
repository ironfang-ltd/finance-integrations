// IRONFANG_API_KEY=... node validate-v2.mjs invoice.pdf [family]
// An invoice XML, or a ZUGFeRD / Factur-X PDF, through V2.
import { readFile } from 'node:fs/promises';
import { IronfangFinance, IronfangFinanceError } from '@ironfang/finance';

try {
  const options = process.argv[3] ? { family: process.argv[3] } : {};
  const result = await new IronfangFinance({ apiKey: process.env.IRONFANG_API_KEY ?? '' })
    .validateV2(await readFile(process.argv[2]), options);
  // Print only status, identity and check groups; findings may quote the invoice.
  console.log(JSON.stringify({
    outcome: result.outcome,
    ruleset: result.ruleset.id,
    scope: result.ruleset.scope,
    sha256: result.input.sha256,
    groups: Object.fromEntries(result.groups.map(group => [group.group, group.status])),
  }));
  process.exitCode = result.outcome === 'valid' ? 0 : 1;
} catch (error) {
  console.error(error instanceof IronfangFinanceError ? error.message : 'Ironfang Finance: input unavailable');
  process.exitCode = 2;
}
